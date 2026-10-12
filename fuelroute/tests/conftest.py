"""Shared fixtures: a clean cache per test, a station factory and a fake OSRM route."""

from unittest import mock

import numpy as np
import pytest
from django.core.cache import cache

from fuelroute.models import FuelStation
from fuelroute.services import station_index
from fuelroute.services.geo import cumulative_miles
from fuelroute.services.osrm import Route

# A straight road due north along longitude -95, about 1,035 miles long.
START = "30.0,-95.0"
FINISH = "45.0,-95.0"


def straight_route(*_args) -> Route:
    coords = np.column_stack((np.linspace(30.0, 45.0, 400), np.full(400, -95.0)))
    miles = cumulative_miles(coords)
    return Route(distance_miles=float(miles[-1]), duration_seconds=miles[-1] / 60 * 3600, coords=coords)


@pytest.fixture(autouse=True)
def clean_state():
    """Plans and the in-memory station index must not leak between tests."""
    cache.clear()
    station_index.clear_cache()
    yield
    cache.clear()
    station_index.clear_cache()


@pytest.fixture
def make_station(db):
    def create(opis_id: int, lat: float, lng: float, price: str = "3.00") -> FuelStation:
        return FuelStation.objects.create(
            opis_id=opis_id,
            name=f"Station {opis_id}",
            address="I-35",
            city="Town",
            state="TX",
            price=price,
            latitude=lat,
            longitude=lng,
        )

    return create


@pytest.fixture
def mocked_route():
    with mock.patch("fuelroute.services.osrm.fetch_route", side_effect=straight_route) as fetch:
        yield fetch
