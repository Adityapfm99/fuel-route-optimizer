from unittest import mock

import pytest
import requests

from fuelroute.services import osrm
from fuelroute.services.exceptions import NoRouteFound, RoutingUnavailable
from fuelroute.services.geo import Location

CHICAGO = Location("Chicago, IL", "Chicago, IL", 41.88, -87.63)
HOUSTON = Location("Houston, TX", "Houston, TX", 29.76, -95.37)


@pytest.fixture
def osrm_get():
    with mock.patch.object(osrm.requests, "get") as get:
        yield get


def test_parses_distance_duration_and_coordinates(osrm_get):
    osrm_get.return_value.json.return_value = {
        "code": "Ok",
        "routes": [
            {
                "distance": 1_609_344,  # metres = 1,000 miles
                "duration": 36_000,
                "geometry": {"coordinates": [[-87.63, 41.88], [-95.37, 29.76]]},
            }
        ],
    }

    route = osrm.fetch_route(CHICAGO, HOUSTON)

    assert route.distance_miles == pytest.approx(1000)
    assert route.duration_seconds == 36_000
    assert route.coords.tolist() == [[41.88, -87.63], [29.76, -95.37]]  # (lat, lng) rows


def test_makes_a_single_request_for_the_full_geometry(osrm_get):
    osrm_get.return_value.json.return_value = {"code": "NoRoute"}

    with pytest.raises(NoRouteFound):
        osrm.fetch_route(CHICAGO, HOUSTON)

    osrm_get.assert_called_once()
    url = osrm_get.call_args.args[0]
    assert url.endswith("/route/v1/driving/-87.63,41.88;-95.37,29.76")
    assert osrm_get.call_args.kwargs["params"]["overview"] == "full"


@pytest.mark.parametrize("error", [requests.Timeout("slow"), ValueError("not json")])
def test_service_failures_become_routing_unavailable(osrm_get, error):
    osrm_get.side_effect = error

    with pytest.raises(RoutingUnavailable):
        osrm.fetch_route(CHICAGO, HOUSTON)
