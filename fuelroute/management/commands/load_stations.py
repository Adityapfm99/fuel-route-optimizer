import csv
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from fuelroute.models import FuelStation
from fuelroute.services import station_index


class Command(BaseCommand):
    help = "Load geocoded fuel stations (data/fuel_stations.csv) into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default=str(Path(settings.DATA_DIR) / "fuel_stations.csv"),
            help="CSV produced by scripts/geocode_stations.py",
        )

    def handle(self, *args, **options):
        # The source file lists some truck stops more than once (different
        # names / prices for the same OPIS id); keep the cheapest price.
        stations: dict[int, FuelStation] = {}
        with open(options["path"], newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                opis_id = int(row["opis_id"])
                price = Decimal(row["price"])
                existing = stations.get(opis_id)
                if existing and existing.price <= price:
                    continue
                stations[opis_id] = FuelStation(
                    opis_id=opis_id,
                    name=row["name"],
                    address=row["address"],
                    city=row["city"],
                    state=row["state"],
                    rack_id=int(row["rack_id"]) if row["rack_id"] else None,
                    price=price,
                    latitude=float(row["lat"]),
                    longitude=float(row["lng"]),
                )

        with transaction.atomic():
            FuelStation.objects.all().delete()
            FuelStation.objects.bulk_create(stations.values(), batch_size=1000)
        station_index.clear_cache()

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(stations)} fuel stations."))
