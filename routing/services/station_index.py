"""Find fuel stations along a route.

Stations are loaded from the DB once per process and kept as numpy arrays.
Per request we:
  1. densify the route polyline to ~1 mile spacing (ORS geometry can have
     long straight segments with no vertices),
  2. build a KD-tree over those route points (small: one point per mile),
  3. query every station's nearest route point within the search radius.
That gives each nearby station its mile marker along the route in a few ms.
"""
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.spatial import cKDTree

from routing.models import FuelStation

from .geo import chord_to_miles, haversine_miles, miles_to_chord, to_unit_xyz


@dataclass
class StationOnRoute:
    id: int
    name: str
    address: str
    city: str
    state: str
    price: float
    lat: float
    lng: float
    route_mile: float      # distance from the start along the route
    off_route_miles: float  # straight-line distance from the route


@lru_cache(maxsize=1)
def _stations():
    rows = list(FuelStation.objects.values_list(
        "opis_id", "name", "address", "city", "state", "price", "latitude", "longitude"))
    lats = np.array([r[6] for r in rows])
    lngs = np.array([r[7] for r in rows])
    return rows, to_unit_xyz(lats, lngs)


def reload_stations():
    _stations.cache_clear()


def densify(coords, step_miles=1.0):
    """Return (lats, lngs, cumulative_miles) with points at most ~step_miles apart."""
    pts = np.asarray(coords, dtype=float)
    lngs, lats = pts[:, 0], pts[:, 1]
    seg = haversine_miles(lats[:-1], lngs[:-1], lats[1:], lngs[1:])
    out_lat, out_lng, out_mile = [lats[0]], [lngs[0]], [0.0]
    mile = 0.0
    for i, length in enumerate(seg):
        n = max(1, int(np.ceil(length / step_miles)))
        t = np.arange(1, n + 1) / n
        out_lat.extend(lats[i] + (lats[i + 1] - lats[i]) * t)
        out_lng.extend(lngs[i] + (lngs[i + 1] - lngs[i]) * t)
        out_mile.extend(mile + length * t)
        mile += length
    return np.array(out_lat), np.array(out_lng), np.array(out_mile)


def stations_along_route(coords, radius_miles, route_length_miles=None):
    rows, station_xyz = _stations()
    if not rows:
        return []
    lats, lngs, miles = densify(coords)
    # Scale polyline miles to the provider's road distance so mile markers
    # and fuel math agree with the reported total.
    if route_length_miles and miles[-1] > 0:
        miles = miles * (route_length_miles / miles[-1])

    tree = cKDTree(to_unit_xyz(lats, lngs))
    dist, idx = tree.query(station_xyz, distance_upper_bound=miles_to_chord(radius_miles))
    hits = np.flatnonzero(np.isfinite(dist))

    result = [
        StationOnRoute(
            id=rows[i][0], name=rows[i][1], address=rows[i][2], city=rows[i][3],
            state=rows[i][4], price=float(rows[i][5]), lat=rows[i][6], lng=rows[i][7],
            route_mile=float(miles[idx[i]]), off_route_miles=float(chord_to_miles(dist[i])),
        )
        for i in hits
    ]
    result.sort(key=lambda s: s.route_mile)
    return result
