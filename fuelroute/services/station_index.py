"""In-memory, numpy-backed view of all fuel stations, used to find the ones along a route.

Loaded from the database once per process; ~7k rows fit comfortably in memory
and make the "which stations are near this polyline" query a few milliseconds.
"""

from dataclasses import dataclass
from functools import cache

import numpy as np

from fuelroute.models import FuelStation

from .geo import MILES_PER_DEGREE_LAT

# Route vertices are resampled to roughly this spacing before measuring
# station distances; plenty for a 10-mile detour tolerance.
SAMPLE_SPACING_MILES = 1.0
CHUNK_SIZE = 512


@dataclass
class StationArrays:
    stations: list[FuelStation]
    lat: np.ndarray
    lng: np.ndarray
    price: np.ndarray


@dataclass
class Candidate:
    station: FuelStation
    price: float
    mile: float  # position along the route
    detour_miles: float  # straight-line distance from the route


@cache
def load() -> StationArrays:
    stations = list(FuelStation.objects.all())
    return StationArrays(
        stations=stations,
        lat=np.array([s.latitude for s in stations], dtype=float),
        lng=np.array([s.longitude for s in stations], dtype=float),
        price=np.array([float(s.price) for s in stations], dtype=float),
    )


def clear_cache() -> None:
    load.cache_clear()


def stations_along_route(
    route_coords: np.ndarray, route_miles: np.ndarray, max_detour_miles: float
) -> list[Candidate]:
    """Stations within ``max_detour_miles`` of the route, sorted by route position."""
    index = load()
    if not index.stations or len(route_coords) == 0:
        return []

    # Resample the polyline to ~1 point per mile.
    targets = np.arange(0.0, route_miles[-1] + SAMPLE_SPACING_MILES, SAMPLE_SPACING_MILES)
    sample_idx = np.unique(np.clip(np.searchsorted(route_miles, targets), 0, len(route_miles) - 1))
    sample_lat = route_coords[sample_idx, 0]
    sample_lng = route_coords[sample_idx, 1]
    sample_miles = route_miles[sample_idx]

    # Cheap bounding-box prefilter.
    pad_lat = max_detour_miles / MILES_PER_DEGREE_LAT
    pad_lng = pad_lat / max(np.cos(np.radians(np.abs(sample_lat).max())), 0.1)
    in_box = np.flatnonzero(
        (index.lat >= sample_lat.min() - pad_lat)
        & (index.lat <= sample_lat.max() + pad_lat)
        & (index.lng >= sample_lng.min() - pad_lng)
        & (index.lng <= sample_lng.max() + pad_lng)
    )

    candidates: list[Candidate] = []
    for start in range(0, len(in_box), CHUNK_SIZE):
        chunk = in_box[start : start + CHUNK_SIZE]
        lat = index.lat[chunk][:, None]
        lng = index.lng[chunk][:, None]
        # Equirectangular approximation — accurate to well under 1% at these scales.
        dy = (lat - sample_lat[None, :]) * MILES_PER_DEGREE_LAT
        dx = (lng - sample_lng[None, :]) * MILES_PER_DEGREE_LAT * np.cos(np.radians(lat))
        dist = np.hypot(dx, dy)
        nearest = dist.argmin(axis=1)
        nearest_dist = dist[np.arange(len(chunk)), nearest]
        for station_idx, sample, detour in zip(chunk, nearest, nearest_dist):
            if detour <= max_detour_miles:
                candidates.append(
                    Candidate(
                        station=index.stations[station_idx],
                        price=float(index.price[station_idx]),
                        mile=float(sample_miles[sample]),
                        detour_miles=float(detour),
                    )
                )

    candidates.sort(key=lambda c: (c.mile, c.price))
    return candidates
