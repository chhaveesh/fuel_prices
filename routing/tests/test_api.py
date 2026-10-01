"""API tests. The routing provider is mocked, so tests run offline and fast."""
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.urls import reverse

from routing.models import City, FuelStation
from routing.services import station_index
from routing.services.exceptions import NoFeasibleRoute, RouteProviderError
from routing.services.locations import resolve_location
from routing.services.ors_client import Route, get_route
from routing.utils import city_key

CITIES = [
    ("Chicago", "IL", 41.8858, -87.6181),
    ("Iowa City", "IA", 41.6611, -91.5302),
    ("Omaha", "NE", 41.2565, -95.9345),
    ("North Platte", "NE", 41.1240, -100.7654),
    ("Denver", "CO", 39.8406, -105.0080),
    ("Saint Louis", "MO", 38.6426, -90.3242),
]


@override_settings(ORS_API_KEY="test", FUEL_STOP_PENALTY_USD=10)
class TripPlanApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for name, state, lat, lng in CITIES:
            City.objects.create(name=name, state=state, key=city_key(name, state),
                                latitude=lat, longitude=lng)
        for i, (name, state, lat, lng) in enumerate(CITIES[:5]):
            FuelStation.objects.create(
                opis_id=i + 1, name=f"Stop {name}", address="I-80", city=name, state=state,
                rack_id=1, price=3.5 - i * 0.1, latitude=lat, longitude=lng)

    def setUp(self):
        station_index.reload_stations()  # in-memory index must see the test DB
        coords = [[lng, lat] for _, _, lat, lng in CITIES[:5]]
        self.route = Route(coordinates=coords, distance_miles=1000, duration_hours=15)

    def get(self, **params):
        with patch("routing.services.trip_planner.get_route", return_value=self.route) as mock:
            response = self.client.get(reverse("trip-plan"), params)
        return response, mock

    def test_plans_trip(self):
        response, mock = self.get(start="Chicago, IL", finish="Denver, CO")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(mock.call_count, 1)  # exactly one routing call
        self.assertAlmostEqual(data["summary"]["total_gallons"], 100, places=1)
        self.assertGreaterEqual(data["summary"]["fuel_stops"], 2)  # 1000 mi > 500 mi range
        self.assertAlmostEqual(
            data["summary"]["total_fuel_cost_usd"],
            sum(s["cost_usd"] for s in data["fuel_stops"]), places=1)
        self.assertEqual(data["route"]["type"], "LineString")
        self.assertIn("/api/route/map/", data["map_url"])

    def test_include_route_false_omits_geometry(self):
        response, _ = self.get(start="Chicago, IL", finish="Denver, CO", include_route="false")
        self.assertNotIn("route", response.json())

    def test_missing_param_is_400(self):
        response, _ = self.get(start="Chicago, IL")
        self.assertEqual(response.status_code, 400)

    def test_unknown_city_is_404(self):
        response, _ = self.get(start="Atlantis, ZZ", finish="Denver, CO")
        self.assertEqual(response.status_code, 404)

    def test_location_outside_usa_is_400(self):
        response, _ = self.get(start="51.5,-0.1", finish="Denver, CO")
        self.assertEqual(response.status_code, 400)

    def test_provider_failure_is_502(self):
        with patch("routing.services.trip_planner.get_route",
                   side_effect=RouteProviderError("down")):
            response = self.client.get(reverse("trip-plan"),
                                       {"start": "Chicago, IL", "finish": "Denver, CO"})
        self.assertEqual(response.status_code, 502)

    def test_map_page_renders(self):
        with patch("routing.services.trip_planner.get_route", return_value=self.route):
            response = self.client.get(reverse("trip-map"),
                                       {"start": "Chicago, IL", "finish": "Denver, CO"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "L.polyline")


    def test_same_start_and_finish_is_400(self):
        response, mock = self.get(start="Denver, CO", finish="Denver, CO")
        self.assertEqual(response.status_code, 400)
        self.assertIn("same location", response.json()["error"])
        mock.assert_not_called()  # rejected before spending an API call

    def test_response_includes_warnings_list(self):
        response, _ = self.get(start="Chicago, IL", finish="Denver, CO")
        self.assertEqual(response.json()["warnings"], [])


@override_settings(ORS_API_KEY="test")
class OrsClientTests(TestCase):
    def ors_error(self, status, code, message):
        resp = MagicMock(status_code=status)
        resp.json.return_value = {"error": {"code": code, "message": message}}
        return resp

    def call(self, response):
        start = resolve_location("21.30,-157.85")  # Honolulu
        finish = resolve_location("39.74,-104.99")  # Denver
        with patch("routing.services.ors_client.requests.post", return_value=response):
            return get_route(start, finish)

    def test_route_not_found_is_unroutable_422(self):
        with self.assertRaises(NoFeasibleRoute) as ctx:
            self.call(self.ors_error(404, 2009, "Route could not be found"))
        self.assertEqual(ctx.exception.status_code, 422)

    def test_server_error_is_502(self):
        with self.assertRaises(RouteProviderError) as ctx:
            self.call(self.ors_error(500, 2099, "Unknown internal error"))
        self.assertEqual(ctx.exception.status_code, 502)


class LocationTests(TestCase):
    def setUp(self):
        City.objects.create(name="Saint Louis", state="MO", key=city_key("Saint Louis", "MO"),
                            latitude=38.6, longitude=-90.3)

    def test_abbreviation_and_whitespace_are_normalized(self):
        self.assertEqual(resolve_location("  St. Louis , mo ").label, "Saint Louis, MO")

    def test_lat_lng_input(self):
        loc = resolve_location("39.74,-104.99")
        self.assertAlmostEqual(loc.lat, 39.74)
