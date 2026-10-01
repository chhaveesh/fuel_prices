"""Small vectorized geometry helpers (numpy)."""
import numpy as np

EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(np.radians, (lat1, lng1, lat2, lng2))
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2)
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))


def to_unit_xyz(lat, lng):
    """Lat/lng -> 3D points on a unit sphere, so a KD-tree's straight-line
    (chord) distance is a correct proxy for distance along the Earth."""
    lat, lng = np.radians(lat), np.radians(lng)
    return np.column_stack((np.cos(lat) * np.cos(lng), np.cos(lat) * np.sin(lng), np.sin(lat)))


def miles_to_chord(miles):
    return 2 * np.sin(miles / EARTH_RADIUS_MILES / 2)


def chord_to_miles(chord):
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.clip(chord / 2, 0, 1))
