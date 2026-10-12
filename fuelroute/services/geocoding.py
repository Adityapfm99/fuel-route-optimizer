"""Resolve a user-supplied location into coordinates.

Accepted inputs, in the order they are tried:

1. ``"lat,lng"`` — used as-is, no lookup.
2. ``"City, ST"`` — looked up in the bundled US cities index (no network).
3. Anything else — one call to the free Nominatim (OpenStreetMap) geocoder.

So a request with two ``City, ST`` inputs makes zero geocoding calls and the
whole trip costs exactly one external call (the route).
"""

import csv
import hashlib
import re
from functools import cache
from pathlib import Path

import requests
from django.conf import settings
from django.core.cache import cache as django_cache

from .exceptions import LocationNotFound, LocationOutsideUSA, RoutingUnavailable
from .geo import Location, in_usa

LAT_LNG_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
CITY_STATE_RE = re.compile(r"^\s*(.+?)\s*,\s*([A-Za-z]{2})\s*(?:,\s*(?:USA?|United States))?\s*$", re.I)


def normalize_city(name: str) -> str:
    return " ".join(name.lower().replace(".", "").split())


@cache
def city_index() -> dict[tuple[str, str], tuple[float, float]]:
    path = Path(settings.DATA_DIR) / "us_cities.csv"
    with open(path, newline="", encoding="utf-8") as f:
        return {
            (normalize_city(row["city"]), row["state"]): (float(row["lat"]), float(row["lng"]))
            for row in csv.DictReader(f)
        }


def resolve(query: str) -> tuple[Location, bool]:
    """Return the location and whether an external API call was made."""
    query = (query or "").strip()
    if not query:
        raise LocationNotFound("Location must not be empty.")

    if match := LAT_LNG_RE.match(query):
        location = Location(query, query, float(match[1]), float(match[2]))
        _ensure_in_usa(location)
        return location, False

    if match := CITY_STATE_RE.match(query):
        key = (normalize_city(match[1]), match[2].upper())
        if coords := city_index().get(key):
            return Location(query, f"{match[1].strip().title()}, {key[1]}", *coords), False

    location, called_api = _nominatim(query)
    _ensure_in_usa(location)
    return location, called_api


def _ensure_in_usa(location: Location) -> None:
    if not in_usa(location.lat, location.lng):
        raise LocationOutsideUSA(f"'{location.query}' is outside the USA.")


def _nominatim(query: str) -> tuple[Location, bool]:
    cache_key = "geocode:" + hashlib.sha256(query.lower().encode()).hexdigest()
    if cached := django_cache.get(cache_key):
        return cached, False

    conf = settings.FUELROUTE
    try:
        response = requests.get(
            f"{conf['NOMINATIM_URL']}/search",
            params={"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "us"},
            headers={"User-Agent": conf["USER_AGENT"]},
            timeout=conf["HTTP_TIMEOUT_SECONDS"],
        )
        response.raise_for_status()
        results = response.json()
    except requests.RequestException as exc:
        raise RoutingUnavailable(f"Geocoding service unavailable: {exc}") from exc

    if not results:
        raise LocationNotFound(f"Could not find a US location matching '{query}'.")

    hit = results[0]
    location = Location(query, hit.get("display_name", query), float(hit["lat"]), float(hit["lon"]))
    django_cache.set(cache_key, location)
    return location, True
