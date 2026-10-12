from dataclasses import dataclass

import numpy as np

EARTH_RADIUS_MILES = 3958.8
MILES_PER_DEGREE_LAT = 69.0

# Generous bounding boxes: contiguous US, Alaska, Hawaii.
US_BOUNDS = (
    (24.0, 50.0, -125.5, -66.5),
    (51.0, 71.5, -180.0, -129.5),
    (18.5, 22.5, -161.0, -154.5),
)


@dataclass(frozen=True)
class Location:
    query: str
    name: str
    lat: float
    lng: float

    def as_dict(self) -> dict:
        return {"query": self.query, "name": self.name, "lat": self.lat, "lng": self.lng}


def in_usa(lat: float, lng: float) -> bool:
    return any(lo_lat <= lat <= hi_lat and lo_lng <= lng <= hi_lng for lo_lat, hi_lat, lo_lng, hi_lng in US_BOUNDS)


def haversine_miles(lat1, lng1, lat2, lng2):
    """Vectorised great-circle distance in miles."""
    lat1, lng1, lat2, lng2 = map(np.radians, (lat1, lng1, lat2, lng2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))


def cumulative_miles(coords: np.ndarray) -> np.ndarray:
    """Cumulative distance along a polyline of (lat, lng) rows, starting at 0."""
    if len(coords) < 2:
        return np.zeros(len(coords))
    seg = haversine_miles(coords[:-1, 0], coords[:-1, 1], coords[1:, 0], coords[1:, 1])
    return np.concatenate(([0.0], np.cumsum(seg)))
