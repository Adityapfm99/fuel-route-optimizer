from unittest import mock

import pytest
import requests

from fuelroute.services import geocoding
from fuelroute.services.exceptions import LocationNotFound, LocationOutsideUSA, RoutingUnavailable


@pytest.fixture
def nominatim():
    with mock.patch.object(geocoding.requests, "get") as get:
        yield get


def nominatim_returns(get, results):
    get.return_value.json.return_value = results
    get.return_value.raise_for_status.return_value = None


def test_lat_lng_is_used_as_is(nominatim):
    location, called = geocoding.resolve(" 41.88 , -87.63 ")

    assert (location.lat, location.lng) == (41.88, -87.63)
    assert called is False
    nominatim.assert_not_called()


@pytest.mark.parametrize("query", ["Chicago, IL", "  chicago ,il ", "Chicago, IL, USA"])
def test_city_state_uses_the_local_index(nominatim, query):
    location, called = geocoding.resolve(query)

    assert location.name == "Chicago, IL"
    assert location.lat == pytest.approx(41.88, abs=0.1)
    assert called is False
    nominatim.assert_not_called()


def test_free_text_calls_nominatim_once_then_uses_the_cache(nominatim):
    nominatim_returns(nominatim, [{"lat": "38.8977", "lon": "-77.0365", "display_name": "White House"}])

    first, first_called = geocoding.resolve("1600 Pennsylvania Ave, Washington DC")
    second, second_called = geocoding.resolve("1600 Pennsylvania Ave, Washington DC")

    assert (first.lat, first.lng, first.name) == (38.8977, -77.0365, "White House")
    assert second == first
    assert (first_called, second_called) == (True, False)
    nominatim.assert_called_once()


def test_unknown_place_is_not_found(nominatim):
    nominatim_returns(nominatim, [])

    with pytest.raises(LocationNotFound):
        geocoding.resolve("Nowhereville Xyz")


def test_empty_query_is_not_found():
    with pytest.raises(LocationNotFound):
        geocoding.resolve("   ")


def test_coordinates_outside_the_usa_are_rejected():
    with pytest.raises(LocationOutsideUSA):
        geocoding.resolve("48.8566,2.3522")


def test_geocoder_outage_is_reported(nominatim):
    nominatim.side_effect = requests.ConnectionError("down")

    with pytest.raises(RoutingUnavailable):
        geocoding.resolve("Some Street, Springfield")
