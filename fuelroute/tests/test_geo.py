import numpy as np
import pytest

from fuelroute.services.geo import cumulative_miles, haversine_miles, in_usa


@pytest.mark.parametrize(
    ("lat", "lng", "expected"),
    [
        (41.88, -87.63, True),  # Chicago
        (61.22, -149.90, True),  # Anchorage
        (21.31, -157.86, True),  # Honolulu
        (48.86, 2.35, False),  # Paris
        (19.43, -99.13, False),  # Mexico City
    ],
)
def test_in_usa(lat, lng, expected):
    assert in_usa(lat, lng) is expected


def test_haversine_new_york_to_los_angeles():
    assert haversine_miles(40.7128, -74.0060, 34.0522, -118.2437) == pytest.approx(2445, abs=5)


def test_cumulative_miles_starts_at_zero_and_adds_up():
    coords = np.array([[30.0, -95.0], [31.0, -95.0], [32.0, -95.0]])

    miles = cumulative_miles(coords)

    assert miles[0] == 0
    assert miles[1] == pytest.approx(69.1, abs=0.2)  # one degree of latitude
    assert miles[2] == pytest.approx(2 * miles[1])


def test_cumulative_miles_of_a_single_point():
    assert cumulative_miles(np.array([[30.0, -95.0]])).tolist() == [0.0]
