"""One-off: attach coordinates to every truck stop in the fuel price CSV.

The price file only has city + state, so each station is placed at its city's
centroid using the public-domain US cities database
(https://github.com/kelvins/US-Cities-Database). Running this offline means the
API never has to geocode thousands of stations at request time.

Usage:
    python scripts/geocode_stations.py <us_cities.csv> data/fuel_prices.csv data/fuel_stations.csv
"""

import csv
import re
import sys
from collections import defaultdict

ABBREVIATIONS = {
    "st": "saint",
    "ste": "sainte",
    "ft": "fort",
    "mt": "mount",
    "pt": "port",
}


def normalize_city(name: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    return " ".join(ABBREVIATIONS.get(w, w) for w in words)


def load_cities(path: str) -> dict[tuple[str, str], tuple[float, float]]:
    # Several rows can share a (city, state) key; average them.
    points: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (normalize_city(row["CITY"]), row["STATE_CODE"].strip().upper())
            points[key].append((float(row["LATITUDE"]), float(row["LONGITUDE"])))
    return {
        key: (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        for key, pts in points.items()
    }


def main(cities_path: str, prices_path: str, out_path: str) -> None:
    cities = load_cities(cities_path)
    matched = missed = 0
    with open(prices_path, newline="", encoding="utf-8") as src, open(
        out_path, "w", newline="", encoding="utf-8"
    ) as dst:
        writer = csv.writer(dst)
        writer.writerow(
            ["opis_id", "name", "address", "city", "state", "rack_id", "price", "lat", "lng"]
        )
        for row in csv.DictReader(src):
            key = (normalize_city(row["City"]), row["State"].strip().upper())
            coords = cities.get(key)
            if coords is None:
                missed += 1
                continue
            matched += 1
            writer.writerow(
                [
                    row["OPIS Truckstop ID"].strip(),
                    row["Truckstop Name"].strip(),
                    row["Address"].strip(),
                    row["City"].strip(),
                    row["State"].strip().upper(),
                    row["Rack ID"].strip(),
                    row["Retail Price"].strip(),
                    f"{coords[0]:.6f}",
                    f"{coords[1]:.6f}",
                ]
            )
    print(f"geocoded {matched} stations, skipped {missed} (city not found)")


if __name__ == "__main__":
    main(*sys.argv[1:4])
