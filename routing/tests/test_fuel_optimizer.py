"""Unit tests for the optimizer. Pure functions: no DB, no HTTP."""
from types import SimpleNamespace

from django.test import SimpleTestCase

from routing.services.exceptions import NoFeasibleRoute
from routing.services.fuel_optimizer import plan_fuel_stops


def station(name, mile, price):
    return SimpleNamespace(name=name, route_mile=mile, price=price)


class FuelOptimizerTests(SimpleTestCase):
    def test_short_trip_needs_one_stop(self):
        plan = plan_fuel_stops([station("A", 0, 3.50)], 200, 500, 10)
        self.assertEqual(len(plan.stops), 1)
        self.assertAlmostEqual(plan.total_gallons, 20)
        self.assertAlmostEqual(plan.total_cost, 70)

    def test_departure_uses_cheapest_station_near_start(self):
        stations = [station("pricey", 2, 4.00), station("cheap", 10, 3.00)]
        plan = plan_fuel_stops(stations, 100, 500, 10)
        self.assertEqual(plan.stops[0].station.name, "cheap")

    def test_buys_only_enough_to_reach_cheaper_station(self):
        stations = [station("A", 0, 4.00), station("B", 300, 3.00), station("C", 700, 3.50)]
        plan = plan_fuel_stops(stations, 1000, 500, 10)
        by_name = {s.station.name: s for s in plan.stops}
        self.assertAlmostEqual(by_name["A"].gallons, 30)  # just 300 miles of $4 fuel
        self.assertAlmostEqual(plan.total_gallons, 100)   # every mile is paid for

    def test_total_gallons_matches_distance(self):
        stations = [station(str(m), m, 3 + (m % 7) / 10) for m in range(0, 2500, 40)]
        plan = plan_fuel_stops(stations, 2500, 500, 10, stop_penalty=10)
        self.assertAlmostEqual(plan.total_gallons, 250)
        self.assertAlmostEqual(plan.total_cost, sum(s.cost for s in plan.stops))

    def test_no_leg_exceeds_vehicle_range(self):
        stations = [station(str(m), m, 3 + (m % 5) / 10) for m in range(0, 3000, 90)]
        plan = plan_fuel_stops(stations, 3000, 500, 10, stop_penalty=10)
        legs = [s.gallons * 10 for s in plan.stops]
        self.assertTrue(all(leg <= 500 + 1e-6 for leg in legs))

    def test_stop_penalty_reduces_number_of_stops(self):
        # A slightly cheaper station every 20 miles tempts many tiny stops.
        stations = [station(str(m), m, 3.50 - m / 100000) for m in range(0, 1000, 20)]
        greedy = plan_fuel_stops(stations, 1000, 500, 10, stop_penalty=0)
        practical = plan_fuel_stops(stations, 1000, 500, 10, stop_penalty=10)
        self.assertLess(len(practical.stops), len(greedy.stops))
        self.assertLessEqual(len(practical.stops), 3)

    def test_gap_longer_than_range_is_infeasible(self):
        stations = [station("A", 0, 3.0), station("B", 600, 3.0)]
        with self.assertRaises(NoFeasibleRoute):
            plan_fuel_stops(stations, 1000, 500, 10)

    def test_no_stations_is_infeasible(self):
        with self.assertRaises(NoFeasibleRoute):
            plan_fuel_stops([], 100, 500, 10)

    def test_remote_start_adds_warning(self):
        plan = plan_fuel_stops([station("far", 120, 3.0)], 400, 500, 10)
        self.assertEqual(len(plan.warnings), 1)
        self.assertIn("first 120 miles", plan.warnings[0])
        self.assertAlmostEqual(plan.total_gallons, 40)  # still every mile paid for

    def test_nearby_start_has_no_warning(self):
        plan = plan_fuel_stops([station("near", 5, 3.0)], 400, 500, 10)
        self.assertEqual(plan.warnings, [])
