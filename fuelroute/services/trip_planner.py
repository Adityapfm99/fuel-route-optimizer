"""Orchestrates one trip plan: geocode -> route (1 external call) -> stations -> fuel plan."""

import hashlib

import numpy as np
from django.conf import settings
from django.core.cache import cache

from . import geocoding, osrm, station_index
from .fuel_planner import plan_fuel_stops
from .geo import cumulative_miles

SIMPLIFY_TOLERANCE_DEGREES = 0.0005  # ~50 m


def plan_trip(start_query: str, finish_query: str) -> dict:
    """Return the trip plan as a JSON-ready dict. Results are cached per (start, finish)."""
    key = "trip:" + hashlib.sha256(
        f"{start_query.strip().lower()}|{finish_query.strip().lower()}".encode()
    ).hexdigest()
    if cached := cache.get(key):
        return {**cached, "meta": {**cached["meta"], "cached": True, "external_api_calls": 0}}

    plan = _build_plan(start_query, finish_query)
    cache.set(key, plan)
    return plan


def _build_plan(start_query: str, finish_query: str) -> dict:
    conf = settings.FUELROUTE
    start, start_called = geocoding.resolve(start_query)
    finish, finish_called = geocoding.resolve(finish_query)
    route = osrm.fetch_route(start, finish)

    # Scale our polyline length to OSRM's distance so mile markers line up.
    miles = cumulative_miles(route.coords)
    if miles[-1] > 0:
        miles *= route.distance_miles / miles[-1]

    candidates = station_index.stations_along_route(route.coords, miles, conf["MAX_DETOUR_MILES"])
    fuel_plan = plan_fuel_stops(
        candidates,
        total_miles=route.distance_miles,
        max_range_miles=conf["MAX_RANGE_MILES"],
        mpg=conf["MILES_PER_GALLON"],
        origin_radius_miles=conf["ORIGIN_RADIUS_MILES"],
        stop_penalty=conf["STOP_PENALTY_USD"],
    )

    return {
        "start": start.as_dict(),
        "finish": finish.as_dict(),
        "vehicle": {
            "max_range_miles": conf["MAX_RANGE_MILES"],
            "miles_per_gallon": conf["MILES_PER_GALLON"],
        },
        "route": {
            "distance_miles": round(route.distance_miles, 1),
            "duration_hours": round(route.duration_seconds / 3600, 2),
            "geometry": _geometry(route.coords, miles),
        },
        "fuel_stops": [
            {
                "stop_number": n,
                "opis_id": s.candidate.station.opis_id,
                "name": s.candidate.station.name,
                "address": s.candidate.station.address,
                "city": s.candidate.station.city,
                "state": s.candidate.station.state,
                "lat": s.candidate.station.latitude,
                "lng": s.candidate.station.longitude,
                "price_per_gallon": round(s.candidate.price, 3),
                "route_mile": round(s.candidate.mile, 1),
                "detour_miles": round(s.candidate.detour_miles, 1),
                "gallons": round(s.gallons, 2),
                "cost": round(s.cost, 2),
            }
            for n, s in enumerate(fuel_plan.stops, start=1)
        ],
        "total_gallons": round(fuel_plan.total_gallons, 2),
        "total_fuel_cost": round(fuel_plan.total_cost, 2),
        "meta": {
            "stations_considered": len(candidates),
            "external_api_calls": 1 + int(start_called) + int(finish_called),
            "cached": False,
        },
    }


def _geometry(coords: np.ndarray, miles: np.ndarray) -> dict:
    """GeoJSON LineString simplified with Douglas-Peucker (~50 m tolerance).

    OSRM's full-resolution geometry has thousands of vertices; most lie on a
    straight stretch and can go without changing how the line looks on a map.
    """
    keep = _simplify(coords, SIMPLIFY_TOLERANCE_DEGREES)
    return {
        "type": "LineString",
        "coordinates": [[round(lng, 5), round(lat, 5)] for lat, lng in coords[keep]],
    }


def _simplify(coords: np.ndarray, tolerance: float) -> np.ndarray:
    """Indices of the vertices kept by Douglas-Peucker (iterative, vectorised per segment)."""
    if len(coords) < 3:
        return np.arange(len(coords))
    # Work in a locally equal-area plane: shrink longitude by cos(latitude).
    xy = np.column_stack((coords[:, 1] * np.cos(np.radians(coords[:, 0].mean())), coords[:, 0]))
    keep = np.zeros(len(xy), dtype=bool)
    keep[[0, -1]] = True
    stack = [(0, len(xy) - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        a, b = xy[first], xy[last]
        points = xy[first + 1 : last]
        ab = b - a
        length = np.hypot(*ab)
        if length == 0:
            dist = np.hypot(*(points - a).T)
        else:
            dist = np.abs(ab[0] * (points[:, 1] - a[1]) - ab[1] * (points[:, 0] - a[0])) / length
        farthest = int(dist.argmax())
        if dist[farthest] > tolerance:
            split = first + 1 + farthest
            keep[split] = True
            stack.extend(((first, split), (split, last)))
    return np.flatnonzero(keep)
