from unittest import mock

import pytest

from fuelroute.services.exceptions import RoutingUnavailable

from .conftest import FINISH, START


@pytest.fixture
def stations(make_station):
    make_station(1, 30.05, -95.0, "3.50")  # at the origin
    make_station(2, 34.0, -95.05, "3.00")  # ~276 mi
    make_station(3, 37.5, -94.95, "3.20")  # ~518 mi
    make_station(4, 40.0, -95.0, "2.90")  # ~690 mi
    make_station(5, 40.0, -80.0, "1.00")  # very cheap but nowhere near the route


def test_route_plan_returns_stops_cost_and_map_link(client, stations, mocked_route):
    response = client.get("/api/route/", {"start": START, "finish": FINISH})

    assert response.status_code == 200
    data = response.json()
    distance = data["route"]["distance_miles"]
    assert distance == pytest.approx(1035, abs=5)
    assert data["total_gallons"] == pytest.approx(distance / 10, abs=0.05)
    assert data["total_fuel_cost"] == pytest.approx(sum(s["cost"] for s in data["fuel_stops"]), abs=0.05)
    assert 5 not in [s["opis_id"] for s in data["fuel_stops"]]

    marks = [0.0] + [s["route_mile"] for s in data["fuel_stops"]] + [distance]
    assert all(b - a <= 500 for a, b in zip(marks[1:], marks[2:]))

    assert data["meta"]["external_api_calls"] == 1
    assert data["meta"]["cached"] is False
    assert data["route"]["geometry"]["type"] == "LineString"
    assert "/api/route/map/?" in data["map_url"]
    mocked_route.assert_called_once()


def test_repeat_request_is_served_from_cache(client, stations, mocked_route):
    client.get("/api/route/", {"start": START, "finish": FINISH})
    data = client.get("/api/route/", {"start": START, "finish": FINISH}).json()

    assert data["meta"]["cached"] is True
    assert data["meta"]["external_api_calls"] == 0
    mocked_route.assert_called_once()


def test_post_json_body(client, stations, mocked_route):
    response = client.post(
        "/api/route/", {"start": START, "finish": FINISH}, content_type="application/json"
    )

    assert response.status_code == 200
    assert response.json()["fuel_stops"]


def test_map_view_renders_html(client, stations, mocked_route):
    response = client.get("/api/route/map/", {"start": START, "finish": FINISH})

    assert response.status_code == 200
    assert b"leaflet" in response.content
    assert b"plan-data" in response.content


def test_missing_parameters(client):
    response = client.get("/api/route/", {"start": START})

    assert response.status_code == 400
    assert "required" in response.json()["error"]


def test_location_outside_usa(client, stations, mocked_route):
    response = client.get("/api/route/", {"start": "48.85,2.35", "finish": FINISH})

    assert response.status_code == 422
    mocked_route.assert_not_called()


def test_no_station_near_start_is_unprocessable(client, db, mocked_route):
    response = client.get("/api/route/", {"start": START, "finish": FINISH})

    assert response.status_code == 422
    assert "start" in response.json()["error"]


def test_routing_service_down(client, stations):
    with mock.patch("fuelroute.services.osrm.fetch_route", side_effect=RoutingUnavailable("down")):
        response = client.get("/api/route/", {"start": START, "finish": FINISH})

    assert response.status_code == 502
