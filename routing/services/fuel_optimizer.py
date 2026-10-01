"""Choose where to fuel up and how much to buy.

Goal: minimize   total fuel cost  +  STOP_PENALTY_USD x number of stops.

The pure cheapest-fuel answer (a classic greedy) is cost-optimal to the cent
but produces impractical plans: on a cross-country trip it stops ~18 times,
some stops buying under 2 gallons to save a few cents. A small per-stop cost
(the driver's time, getting off the highway) gives plans a real driver would
follow, at a fuel cost within ~1% of the theoretical minimum. Setting the
penalty to 0 recovers near-pure cost minimization.

Model: a shortest path over a DAG.
  * Nodes are stations sorted by mile marker, plus the finish.
  * An edge i -> j exists when j is within tank range of i. Its weight is
    the fuel for that leg, bought at i's price, plus the stop penalty.
  * The vehicle starts with an empty tank, so every gallon of the trip is
    paid for; the departure fill-up is the cheapest station within the first
    START_SEARCH_MILES (the few miles driven to reach it count toward it).
  * The vehicle arrives empty: no fuel is bought that isn't used.
  * If no station lies within START_SEARCH_MILES of the start, the plan still
    works but carries a warning saying so (no silent assumptions).

Because stations are sorted along the route, the DAG is solved in a single
backward pass: O(n x stations-in-range), a few ms for a coast-to-coast route.

The functions here are pure (no DB, no HTTP), which keeps them easy to test.
"""
from bisect import bisect_right
from dataclasses import dataclass, field

import numpy as np

from .exceptions import NoFeasibleRoute

START_SEARCH_MILES = 25.0
EPS = 1e-6


@dataclass
class FuelStop:
    station: object          # StationOnRoute
    route_mile: float
    gallons: float
    cost: float


@dataclass
class FuelPlan:
    stops: list = field(default_factory=list)
    total_gallons: float = 0.0
    total_cost: float = 0.0
    warnings: list = field(default_factory=list)


def plan_fuel_stops(stations, route_miles, tank_range, mpg, stop_penalty=0.0):
    """stations: objects with .route_mile and .price."""
    if route_miles <= 0:
        return FuelPlan()

    candidates = sorted((s for s in stations if s.route_mile < route_miles),
                        key=lambda s: s.route_mile)
    if not candidates:
        raise NoFeasibleRoute("No fuel stations found along this route.")

    warnings = []
    near_start = [s for s in candidates if s.route_mile <= START_SEARCH_MILES]
    if near_start:
        start = min(near_start, key=lambda s: s.price)
    elif candidates[0].route_mile <= tank_range:
        start = candidates[0]
        warnings.append(
            f"No fuel station within {START_SEARCH_MILES:.0f} miles of the start. The vehicle "
            f"must depart with enough fuel for the first {start.route_mile:.0f} miles; that fuel "
            f"is costed at the first station's price.")
    else:
        raise NoFeasibleRoute(f"No fuel station within {tank_range:.0f} miles of the start.")

    # Node 0 = departure station (treated as mile 0); then stations after it.
    nodes = [start] + [s for s in candidates if s is not start]
    pos = np.array([0.0] + [s.route_mile for s in nodes[1:]] + [route_miles])
    price = np.array([s.price for s in nodes] + [0.0])
    n = len(nodes)  # index n is the finish

    best = np.full(n + 1, np.inf)   # min cost from node i to the finish
    nxt = np.full(n + 1, -1, dtype=int)
    best[n] = 0.0
    pos_list = pos.tolist()
    for i in range(n - 1, -1, -1):
        lo = i + 1
        hi = bisect_right(pos_list, pos_list[i] + tank_range + EPS)  # exclusive
        if lo >= hi:
            continue
        legs = (pos[lo:hi] - pos[i]) * price[i] / mpg + best[lo:hi]
        k = int(np.argmin(legs))
        if np.isfinite(legs[k]):
            best[i] = legs[k] + stop_penalty
            nxt[i] = lo + k

    if not np.isfinite(best[0]):
        gap_at = _first_gap(pos_list, tank_range)
        raise NoFeasibleRoute(
            f"No fuel station within {tank_range:.0f} miles after mile {gap_at:.0f}; "
            "the trip isn't possible on one tank.")

    plan = FuelPlan(warnings=warnings)
    i = 0
    while i != n:
        prev, j = i, nxt[i]
        gallons = (pos[j] - pos[prev]) / mpg
        cost = gallons * price[prev]
        i = j
        if gallons < 0.01:  # same-mile duplicate station; nothing bought
            continue
        plan.stops.append(FuelStop(station=nodes[prev], route_mile=float(pos[prev]),
                                   gallons=float(gallons), cost=float(cost)))
        plan.total_gallons += gallons
        plan.total_cost += cost
    plan.total_gallons = float(plan.total_gallons)
    plan.total_cost = float(plan.total_cost)
    return plan


def _first_gap(positions, tank_range):
    for a, b in zip(positions, positions[1:]):
        if b - a > tank_range:
            return a
    return positions[0]
