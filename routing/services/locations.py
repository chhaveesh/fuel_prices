"""Resolve user input ('Chicago, IL' or '41.88,-87.63') to coordinates, offline."""
import re
from dataclasses import dataclass

from routing.models import City
from routing.utils import city_key

from .exceptions import LocationNotFound, RoutingError

_LATLNG = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")

# Rough bounding boxes: contiguous US, Alaska, Hawaii.
_US_BOXES = [
    (24.4, 49.5, -125.0, -66.9),
    (51.0, 71.5, -180.0, -129.9),
    (18.9, 22.3, -160.3, -154.8),
]


@dataclass(frozen=True)
class Location:
    label: str
    lat: float
    lng: float


def _in_usa(lat: float, lng: float) -> bool:
    return any(a <= lat <= b and c <= lng <= d for a, b, c, d in _US_BOXES)


def resolve_location(text: str) -> Location:
    text = (text or "").strip()
    if not text:
        raise RoutingError("Location must not be empty.")

    match = _LATLNG.match(text)
    if match:
        lat, lng = float(match.group(1)), float(match.group(2))
        if not _in_usa(lat, lng):
            raise RoutingError(f"'{text}' is outside the USA.")
        return Location(label=text, lat=lat, lng=lng)

    if "," not in text:
        raise RoutingError(f"'{text}': use 'City, ST' (e.g. 'Dallas, TX') or 'lat,lng'.")
    city, state = text.rsplit(",", 1)
    found = City.objects.filter(key=city_key(city, state)).first()
    if found is None:
        raise LocationNotFound(f"Could not find US city '{text}'.")
    return Location(label=str(found), lat=found.latitude, lng=found.longitude)
