import numpy as np
import pytest

from fuelroute.services import station_index

from .conftest import straight_route

MAX_DETOUR_MILES = 10.0


def stations_along(route):
    return station_index.stations_along_route(
        route.coords, np.linspace(0, route.distance_miles, len(route.coords)), MAX_DETOUR_MILES
    )


def test_finds_stations_near_the_route_with_their_route_mile(make_station):
    make_station(1, 40.0, -95.0)  # on the road
    make_station(2, 35.0, -95.1)  # ~5.7 mi off the road
    make_station(3, 35.0, -95.3)  # ~17 mi off the road: too far
    make_station(4, 50.0, -95.0)  # past the end of the route

    found = stations_along(straight_route())

    assert [c.station.opis_id for c in found] == [2, 1]  # ordered along the route
    by_id = {c.station.opis_id: c for c in found}
    assert by_id[2].mile == pytest.approx(345, abs=3)
    assert by_id[1].mile == pytest.approx(690, abs=3)
    assert by_id[2].detour_miles == pytest.approx(5.7, abs=0.3)
    assert by_id[1].detour_miles == pytest.approx(0, abs=0.1)


def test_candidate_carries_the_station_price(make_station):
    make_station(1, 40.0, -95.0, price="3.1234")

    (candidate,) = stations_along(straight_route())

    assert candidate.price == pytest.approx(3.1234)


def test_no_stations_in_the_database(db):
    assert stations_along(straight_route()) == []
