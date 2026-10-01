# Fuel Route Optimizer API

A Django REST API that plans a road trip between two US locations and returns
the route, the most cost-effective places to fuel up (500-mile range, 10 mpg),
and the total fuel cost, plus an interactive map.

```
GET /api/route/?start=Chicago, IL&finish=Denver, CO
```

| | |
|---|---|
| External API calls per request | **1** (OpenRouteService directions), cached for 24 h |
| Response time | ~1–2 s for a new route (the routing call); **~3 ms** when cached |
| Planning time (stations + optimizer) | a few ms, even coast to coast |

## Quick start

Requires **Python 3.12+** (Django 6.1).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add a free key from https://openrouteservice.org
python manage.py migrate
python manage.py load_fuel_data # loads 6,614 US stations + 29,738 US cities (~1 s)
python manage.py runserver
```

Run tests (offline, routing provider mocked): `python manage.py test routing`

## Endpoints

### `GET /api/route/`

| Param | Description |
|---|---|
| `start`, `finish` | `City, ST` (e.g. `Dallas, TX`) or `lat,lng`. USA only. |
| `include_route` | `true` (default) / `false`: include the route GeoJSON. |

Response (abridged):

```json
{
  "start":  {"query": "Chicago, IL", "resolved": "Chicago, IL", "lat": 41.88, "lng": -87.61},
  "finish": {"query": "Denver, CO",  "resolved": "Denver, CO",  "lat": 39.84, "lng": -105.0},
  "summary": {
    "total_fuel_cost_usd": 291.48,
    "total_gallons": 99.92,
    "distance_miles": 999.2,
    "duration_hours": 15.9,
    "fuel_stops": 3,
    "stations_considered": 202,
    "vehicle_range_miles": 500,
    "mpg": 10,
    "stop_penalty_usd": 10
  },
  "warnings": [],
  "fuel_stops": [
    {"stop": 1, "name": "Gulf", "address": "SR-83", "city": "Bensenville", "state": "IL",
     "lat": 41.95, "lng": -87.93, "price_per_gallon": 3.059, "route_mile": 0.0,
     "gallons": 20.34, "cost_usd": 62.22}
  ],
  "route": {"type": "LineString", "coordinates": [[-87.61, 41.88], "..."]},
  "map_url": "http://127.0.0.1:8000/api/route/map/?start=Chicago%2C+IL&finish=Denver%2C+CO"
}
```

Errors (JSON `{"error": "..."}`):

| Status | When |
|---|---|
| `400` | missing/invalid input, location outside the USA, start = finish |
| `404` | unknown city |
| `422` | trip can't be done: no drivable route (e.g. Honolulu → Denver), or a stretch longer than 500 miles with no station |
| `502` | routing provider unavailable or erroring |

`warnings` lists anything the caller should know about the plan, e.g. when no
station exists within 25 miles of the start.

### `GET /api/route/map/`

Same parameters; returns an interactive Leaflet map with the route, numbered
fuel stops, and a cost summary. Reuses the cached route, so no extra API call.

## How it works

```
resolve start/finish (offline) → 1 routing call → stations near route → optimizer → response
```

1. **Data loading (one-off, `load_fuel_data`).** The CSV has no coordinates,
   only highway/exit addresses, so each station is placed at its city's
   coordinates using a bundled public US cities dataset: no geocoding API
   at all. Cleaning: Canadian rows dropped (620), duplicate station IDs
   collapsed to the cheapest price, whitespace and "St./Ft./Mt." normalized.
   99.8% of rows match; the 6 unmatched cities (15 rows) are logged.
2. **Location input** is resolved from the same cities table, so the only
   external call per request is the route itself.
3. **Stations along the route.** All stations live in memory as numpy arrays
   (loaded once per process). Per request, the route is densified to ~1-mile
   spacing, a KD-tree is built over it, and each station's nearest route point
   within 10 miles is found. That gives every nearby station a mile marker.
   Points are projected onto a 3D unit sphere so distances stay accurate
   anywhere in the country.
4. **Optimizer** (`routing/services/fuel_optimizer.py`): a shortest path over
   a DAG of stations sorted by mile marker. Edge *i → j* exists when *j* is
   within 500 miles; its weight is that leg's fuel at *i*'s price plus a
   per-stop cost. One backward pass solves it in ~1 ms.

### Why a per-stop cost?

Pure cheapest-fuel optimization is cost-optimal to the cent but impractical:
New York → Los Angeles produced 18 stops, some buying under 2 gallons to save
a few cents. A $10 per-stop cost (driver time, leaving the highway) roughly
**halves the number of stops for under 1% more fuel cost** on real
cross-country routes. It's a setting (`FUEL_STOP_PENALTY_USD`); `0` gives
lowest-fuel-cost plans. The reported total is fuel only.

## Assumptions

- The vehicle **starts empty**, so the total covers every gallon of the trip
  (distance ÷ 10 mpg). The first fill-up is the cheapest station within the
  first 25 miles. If there is none, the plan still works but includes a
  `warnings` entry explaining the assumption.
- The vehicle **arrives empty**: no fuel is bought that isn't used.
- A station counts as "on the route" within 10 miles of it.
- Station positions are city-level approximations (the source data has no
  street addresses).

## Known limitations and next steps

- **Optimality:** the optimizer picks the best plan among those that buy just
  enough fuel to reach the next stop. It doesn't "carry" cheap fuel past a
  stop; on real routes this costs under ~1% vs. the theoretical optimum.
- **Station locations** are city centroids; geocoding exit addresses offline
  would sharpen "distance from route".
- **"Near the route"** is straight-line distance, not real detour distance.
- **Cache** is per-process memory; production would use Redis. Reloading fuel
  data requires a server restart to refresh the in-memory station index.
- **No auth or rate limiting** on the API; OpenRouteService's free tier is
  about 2,000 requests/day.

## Project layout

```
config/                      settings (env-based), URLs
data/                        fuel_prices.csv, us_cities.csv
routing/
  models.py                  City, FuelStation
  management/commands/       load_fuel_data
  services/
    locations.py             'City, ST' / 'lat,lng' → coordinates (offline)
    ors_client.py            the single OpenRouteService call + cache
    station_index.py         stations near the route (KD-tree)
    fuel_optimizer.py        where to stop and how much to buy
    trip_planner.py          orchestrates the above
  views.py, serializers.py   thin API layer
  templates/routing/map.html Leaflet map
  tests/                     optimizer unit tests + API tests (mocked routing)
```

## Third-party services

- **Routing:** [OpenRouteService](https://openrouteservice.org) (free tier).
- **Map tiles:** OpenStreetMap, via [Leaflet](https://leafletjs.com). No key.
- **City coordinates:** [kelvins/US-Cities-Database](https://github.com/kelvins/US-Cities-Database).
