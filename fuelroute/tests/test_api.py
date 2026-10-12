from unittest import mock

import numpy as np
import pytest
from django.core.cache import cache

from fuelroute.models import FuelStation
from fuelroute.services import station_index
from fuelroute.services.exceptions import RoutingUnavailable
from fuelroute.services.geo import cumulative_miles
from fuelroute.services.osrm import Route

START = "30.0,-95.0"
FINISH = "45.0,-95.0"  # ~1,035 miles due north


def straight_route(*_args) -> Route:
    coords = np.column_stack((np.linspace(30.0, 45.0, 400), np.full(400, -95.0)))
    miles = cumulative_miles(coords)
    return Route(distance_miles=float(miles[-1]), duration_seconds=miles[-1] / 60 * 3600, coords=coords)


@pytest.fixture(autouse=True)
def clean_state():
    cache.clear()
    station_index.clear_cache()
    yield
    cache.clear()
    station_index.clear_cache()


@pytest.fixture
def stations(db):
    rows = [
        # (opis_id, lat, lng, price)
        (1, 30.05, -95.0, "3.50"),  # at the origin
        (2, 34.0, -95.05, "3.00"),  # ~276 mi
        (3, 37.5, -94.95, "3.20"),  # ~518 mi
        (4, 40.0, -95.0, "2.90"),  # ~690 mi
        (5, 40.0, -80.0, "1.00"),  # very cheap but nowhere near the route
    ]
    for opis_id, lat, lng, price in rows:
        FuelStation.objects.create(
            opis_id=opis_id,
            name=f"Station {opis_id}",
            address="I-35",
            city="Town",
            state="TX",
            price=price,
            latitude=lat,
            longitude=lng,
        )


@pytest.fixture
def mocked_route():
    with mock.patch("fuelroute.services.osrm.fetch_route", side_effect=straight_route) as fetch:
        yield fetch


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
