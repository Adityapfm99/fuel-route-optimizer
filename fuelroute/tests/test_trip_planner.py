import numpy as np

from fuelroute.services import trip_planner
from fuelroute.services.trip_planner import _simplify

from .conftest import FINISH, START


def test_simplify_drops_points_on_a_straight_line():
    line = np.column_stack((np.linspace(30, 40, 500), np.full(500, -95.0)))

    assert _simplify(line, tolerance=0.0005).tolist() == [0, 499]


def test_simplify_keeps_corners():
    # North, then east: an L shape with many points on each leg.
    north = np.column_stack((np.linspace(30, 31, 50), np.full(50, -95.0)))
    east = np.column_stack((np.full(50, 31.0), np.linspace(-95, -94, 50)))
    kept = _simplify(np.vstack((north, east)), tolerance=0.0005)

    assert kept.tolist() == [0, 49, 99]


def test_simplify_short_lines_unchanged():
    assert _simplify(np.array([[30.0, -95.0], [31.0, -95.0]]), tolerance=0.0005).tolist() == [0, 1]


def test_plan_is_cached_regardless_of_case_and_spaces(make_station, mocked_route):
    make_station(1, 30.05, -95.0)  # at the start
    make_station(2, 35.0, -95.0)  # ~345 mi
    make_station(3, 40.0, -95.0)  # ~690 mi

    first = trip_planner.plan_trip(START, FINISH)
    second = trip_planner.plan_trip(f"  {START} ", FINISH.upper())

    assert first["meta"]["cached"] is False
    assert second["meta"]["cached"] is True
    assert second["meta"]["external_api_calls"] == 0
    assert second["total_fuel_cost"] == first["total_fuel_cost"]
    mocked_route.assert_called_once()
