"""Orchestrates one trip plan: resolve -> route (1 API call) -> stations -> optimize."""
from django.conf import settings

from .exceptions import RoutingError
from .fuel_optimizer import plan_fuel_stops
from .geo import haversine_miles
from .locations import resolve_location
from .ors_client import get_route
from .station_index import stations_along_route


MIN_TRIP_MILES = 1.0


def plan_trip(start_text: str, finish_text: str) -> dict:
    start = resolve_location(start_text)
    finish = resolve_location(finish_text)
    if haversine_miles(start.lat, start.lng, finish.lat, finish.lng) < MIN_TRIP_MILES:
        raise RoutingError("Start and finish are the same location.")
    route = get_route(start, finish)  # the only external call (and it's cached)

    stations = stations_along_route(
        route.coordinates, settings.STATION_SEARCH_RADIUS_MILES, route.distance_miles)
    plan = plan_fuel_stops(
        stations, route.distance_miles, settings.VEHICLE_RANGE_MILES, settings.VEHICLE_MPG,
        stop_penalty=settings.FUEL_STOP_PENALTY_USD)

    return {
        "start": {"query": start_text, "resolved": start.label, "lat": start.lat, "lng": start.lng},
        "finish": {"query": finish_text, "resolved": finish.label, "lat": finish.lat, "lng": finish.lng},
        "summary": {
            "total_fuel_cost_usd": round(plan.total_cost, 2),
            "total_gallons": round(plan.total_gallons, 2),
            "distance_miles": round(route.distance_miles, 1),
            "duration_hours": round(route.duration_hours, 1),
            "fuel_stops": len(plan.stops),
            "stations_considered": len(stations),
            "vehicle_range_miles": settings.VEHICLE_RANGE_MILES,
            "mpg": settings.VEHICLE_MPG,
            "stop_penalty_usd": settings.FUEL_STOP_PENALTY_USD,
        },
        "warnings": plan.warnings,
        "fuel_stops": [
            {
                "stop": n,
                "name": s.station.name,
                "address": s.station.address,
                "city": s.station.city,
                "state": s.station.state,
                "lat": s.station.lat,
                "lng": s.station.lng,
                "price_per_gallon": round(s.station.price, 3),
                "route_mile": round(s.route_mile, 1),
                "gallons": round(s.gallons, 2),
                "cost_usd": round(s.cost, 2),
            }
            for n, s in enumerate(plan.stops, start=1)
        ],
        "route": {
            "type": "LineString",
            # 5 decimals is ~1 m precision; keeps the payload small.
            "coordinates": [[round(x, 5), round(y, 5)] for x, y in route.coordinates],
        },
    }
