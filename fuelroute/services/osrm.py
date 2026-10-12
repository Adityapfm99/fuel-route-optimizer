"""The single call to the free routing API (OSRM public server, OpenStreetMap data)."""

from dataclasses import dataclass

import numpy as np
import requests
from django.conf import settings

from .exceptions import NoRouteFound, RoutingUnavailable
from .geo import Location

METERS_PER_MILE = 1609.344


@dataclass
class Route:
    distance_miles: float
    duration_seconds: float
    coords: np.ndarray  # (N, 2) rows of (lat, lng)


def fetch_route(start: Location, finish: Location) -> Route:
    conf = settings.FUELROUTE
    url = (
        f"{conf['OSRM_URL']}/route/v1/driving/"
        f"{start.lng},{start.lat};{finish.lng},{finish.lat}"
    )
    try:
        response = requests.get(
            url,
            params={"overview": "full", "geometries": "geojson", "steps": "false"},
            headers={"User-Agent": conf["USER_AGENT"]},
            timeout=conf["HTTP_TIMEOUT_SECONDS"],
        )
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RoutingUnavailable(f"Routing service unavailable: {exc}") from exc

    if payload.get("code") != "Ok" or not payload.get("routes"):
        raise NoRouteFound(payload.get("message") or "No drivable route between these locations.")

    route = payload["routes"][0]
    lng_lat = np.asarray(route["geometry"]["coordinates"], dtype=float)
    return Route(
        distance_miles=route["distance"] / METERS_PER_MILE,
        duration_seconds=route["duration"],
        coords=lng_lat[:, ::-1].copy(),
    )
