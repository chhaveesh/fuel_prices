"""OpenRouteService client: exactly one HTTP call per (uncached) route."""
import hashlib
from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.cache import cache

from .exceptions import NoFeasibleRoute, RouteProviderError
from .locations import Location

ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
METERS_PER_MILE = 1609.344
CACHE_SECONDS = 60 * 60 * 24

# ORS error codes meaning "your trip can't be driven", not "ORS is broken":
# 2004 route too long for the service, 2009 no route found,
# 2010 no road near a given point (e.g. Honolulu -> Denver).
UNROUTABLE_ERROR_CODES = {2004, 2009, 2010}


@dataclass
class Route:
    coordinates: list  # [[lng, lat], ...] (GeoJSON order)
    distance_miles: float
    duration_hours: float


def get_route(start: Location, finish: Location) -> Route:
    cache_key = "route:" + hashlib.md5(
        f"{start.lat:.5f},{start.lng:.5f}->{finish.lat:.5f},{finish.lng:.5f}".encode()
    ).hexdigest()
    cached = cache.get(cache_key)
    if cached:
        return cached

    if not settings.ORS_API_KEY:
        raise RouteProviderError("ORS_API_KEY is not configured.")

    try:
        resp = requests.post(
            ORS_URL,
            json={
                "coordinates": [[start.lng, start.lat], [finish.lng, finish.lat]],
                # City centroids may sit off-road; allow snapping up to 5 km.
                "radiuses": [5000, 5000],
                "instructions": False,
            },
            headers={"Authorization": settings.ORS_API_KEY},
            timeout=20,
        )
    except requests.RequestException as exc:
        raise RouteProviderError(f"Routing service unreachable: {exc}") from exc

    if resp.status_code != 200:
        try:
            error = resp.json().get("error", {})
            code, message = error.get("code"), error.get("message", resp.text)
        except (ValueError, AttributeError):
            code, message = None, resp.text
        if code in UNROUTABLE_ERROR_CODES:
            raise NoFeasibleRoute(f"No drivable route between these locations ({message}).")
        raise RouteProviderError(f"Routing service error: {message}")

    feature = resp.json()["features"][0]
    summary = feature["properties"]["summary"]
    route = Route(
        coordinates=feature["geometry"]["coordinates"],
        distance_miles=summary["distance"] / METERS_PER_MILE,
        duration_hours=summary["duration"] / 3600,
    )
    cache.set(cache_key, route, CACHE_SECONDS)
    return route
