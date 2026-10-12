from types import SimpleNamespace

import pytest

from fuelroute.services.exceptions import FuelPlanInfeasible
from fuelroute.services.fuel_planner import plan_fuel_stops
from fuelroute.services.station_index import Candidate

RANGE = 500.0
MPG = 10.0
ORIGIN_RADIUS = 30.0


def station(mile: float, price: float, pk: int | None = None) -> Candidate:
    pk = pk if pk is not None else int(mile * 100)
    return Candidate(
        station=SimpleNamespace(pk=pk, opis_id=pk, name=f"S{pk}"),
        price=price,
        mile=mile,
        detour_miles=0.0,
    )


def plan(candidates, total_miles, stop_penalty=0.0):
    return plan_fuel_stops(
        candidates,
        total_miles=total_miles,
        max_range_miles=RANGE,
        mpg=MPG,
        origin_radius_miles=ORIGIN_RADIUS,
        stop_penalty=stop_penalty,
    )


def summary(fuel_plan):
    return [(s.candidate.mile, round(s.gallons, 6)) for s in fuel_plan.stops]


def test_buys_only_enough_to_reach_a_cheaper_station_ahead():
    result = plan([station(0, 4.00), station(200, 3.00)], total_miles=600)

    assert summary(result) == [(0, 20.0), (200, 40.0)]
    assert result.total_cost == pytest.approx(20 * 4.00 + 40 * 3.00)


def test_fills_up_when_the_next_station_is_more_expensive():
    result = plan([station(0, 3.00), station(300, 4.00)], total_miles=700)

    # Full tank (50 gal) at the cheap station, then only the 20 gal still missing.
    assert summary(result) == [(0, 50.0), (300, 20.0)]
    assert result.total_cost == pytest.approx(50 * 3.00 + 20 * 4.00)


def test_single_stop_when_destination_is_within_range():
    result = plan([station(5, 3.50), station(100, 3.40)], total_miles=300, stop_penalty=10)

    assert summary(result) == [(5, 30.0)]
    assert result.total_cost == pytest.approx(30 * 3.50)


def test_skips_tiny_stops_that_save_less_than_the_penalty():
    candidates = [station(0, 3.50), station(450, 3.20), station(460, 2.99)]

    cheapest = plan(candidates, total_miles=900, stop_penalty=0)
    practical = plan(candidates, total_miles=900, stop_penalty=10)

    # Cost-optimal: a 1-gallon stop at mile 450 just to reach the 1-cent-cheaper station.
    assert summary(cheapest) == [(0, 45.0), (450, 1.0), (460, 44.0)]
    assert cheapest.total_cost == pytest.approx(45 * 3.50 + 1 * 3.20 + 44 * 2.99)
    # With a per-stop penalty that stop disappears; it costs only $0.30 more.
    assert summary(practical) == [(0, 46.0), (460, 44.0)]
    assert practical.total_cost == pytest.approx(46 * 3.50 + 44 * 2.99)


def test_reported_cost_excludes_the_stop_penalty():
    result = plan([station(0, 3.00)], total_miles=250, stop_penalty=1000)

    assert result.total_cost == pytest.approx(25 * 3.00)


def test_total_gallons_cover_exactly_the_whole_trip():
    candidates = [station(m, 3.0 + (m % 7) / 10) for m in range(0, 2400, 37)]

    for penalty in (0, 10, 50):
        result = plan(candidates, total_miles=2400, stop_penalty=penalty)
        assert result.total_gallons == pytest.approx(2400 / MPG)
        assert result.total_cost == pytest.approx(sum(s.gallons * s.candidate.price for s in result.stops))
        gaps = [b.candidate.mile - a.candidate.mile for a, b in zip(result.stops, result.stops[1:])]
        assert all(g <= RANGE for g in gaps)


def test_penalty_zero_matches_brute_force_optimum_on_small_instance():
    # Cheap station mid-way should be used to its full potential.
    candidates = [station(0, 3.50), station(250, 2.50), station(600, 3.20)]
    result = plan(candidates, total_miles=1000, stop_penalty=0)

    # 250 mi at 3.50, fill 500 at 2.50 (reach mile 750), last 250 at 3.20.
    assert result.total_cost == pytest.approx(25 * 3.50 + 50 * 2.50 + 25 * 3.20)


def test_stations_near_the_origin_count_as_mile_zero():
    result = plan([station(20, 3.00)], total_miles=300)

    assert summary(result) == [(20, 30.0)]


def test_keeps_the_cheapest_of_stations_at_the_same_position():
    result = plan([station(0, 3.90, pk=1), station(0, 3.10, pk=2)], total_miles=100)

    assert [s.candidate.station.pk for s in result.stops] == [2]


def test_no_station_near_origin_is_infeasible():
    with pytest.raises(FuelPlanInfeasible, match="within 30 miles of the start"):
        plan([station(50, 3.00)], total_miles=300)


def test_gap_longer_than_range_is_infeasible():
    with pytest.raises(FuelPlanInfeasible, match="after mile 0"):
        plan([station(0, 3.00), station(600, 3.00)], total_miles=1000)


def test_zero_distance_trip_needs_no_fuel():
    result = plan([], total_miles=0)

    assert result.stops == [] and result.total_cost == 0
