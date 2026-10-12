"""Choose where to buy fuel, and how much, so the trip is cheap *and* practical.

Pure cost minimisation (the textbook greedy "gas station problem") happily makes
a stop for one gallon because the next town is a cent cheaper. Real drivers do
not, so we minimise

    total fuel cost + ``stop_penalty`` x number of stops

with an exact dynamic program over the stations along the route. The penalty is
only used to choose the plan; the reported ``total_cost`` is the money actually
spent on fuel. With ``stop_penalty=0`` the result is the cost-optimal plan.

The DP uses the structure from Khuller, Malekian & Mestre, "To fill or not to
fill: the gas station problem" (2007): in some optimal plan, at every stop *u*
whose next stop is *v* you either

* buy just enough to reach *v*, when *v* is at least as cheap as *u*, or
* fill the tank, when *v* is more expensive,

so the fuel left on arrival at a stop is either 0 or ``range - d(w, u)`` for an
earlier stop *w*. Each station keeps a small Pareto set of (fuel on arrival,
objective) labels, which makes the search a few milliseconds for a
cross-country route.

The vehicle departs with an empty tank. Stations within ``origin_radius`` route
miles of the start are treated as being at mile 0 ("fuel up before leaving town"),
so the total covers every gallon burned on the trip.
"""

from dataclasses import dataclass

from .exceptions import FuelPlanInfeasible
from .station_index import Candidate

EPSILON = 1e-9


@dataclass
class FuelStop:
    candidate: Candidate
    gallons: float
    cost: float


@dataclass
class FuelPlan:
    stops: list[FuelStop]
    total_gallons: float
    total_cost: float


@dataclass
class _Label:
    """Arriving at a node with ``fuel`` miles of range, having paid ``objective`` so far."""

    fuel: float
    objective: float
    parent: "_Label | None" = None
    node: int = 0
    bought_miles: float = 0.0  # fuel bought at ``parent.node`` to get here


def plan_fuel_stops(
    candidates: list[Candidate],
    total_miles: float,
    max_range_miles: float,
    mpg: float,
    origin_radius_miles: float,
    stop_penalty: float = 0.0,
) -> FuelPlan:
    if total_miles <= EPSILON:
        return FuelPlan(stops=[], total_gallons=0.0, total_cost=0.0)

    nodes = _planning_nodes(candidates, total_miles, origin_radius_miles)
    if not nodes or nodes[0][0] > 0.0:
        raise FuelPlanInfeasible(
            f"No fuel station found within {origin_radius_miles:.0f} miles of the start to fill up."
        )

    positions = [p for p, _ in nodes]
    prices = [c.price / mpg for _, c in nodes]  # dollars per mile of range
    labels: list[list[_Label]] = [[] for _ in nodes]
    labels[0].append(_Label(fuel=0.0, objective=0.0, node=0))
    best: _Label | None = None  # label "arriving" at the destination

    for i, here in enumerate(positions):
        frontier = _pareto(labels[i])
        labels[i] = []  # free memory; the frontier is all we need
        reach = here + max_range_miles
        for label in frontier:
            base = label.objective + stop_penalty

            remaining = total_miles - here
            if remaining <= max_range_miles + EPSILON:
                buy = max(0.0, remaining - label.fuel)
                done = _Label(0.0, base + buy * prices[i], label, len(nodes), buy)
                if best is None or done.objective < best.objective - EPSILON:
                    best = done

            for j in range(i + 1, len(nodes)):
                there = positions[j]
                if there > reach + EPSILON:
                    break
                distance = there - here
                if prices[j] <= prices[i]:
                    if label.fuel > distance + EPSILON:
                        continue
                    buy = distance - label.fuel
                    arrive = 0.0
                else:
                    buy = max_range_miles - label.fuel
                    arrive = max_range_miles - distance
                labels[j].append(_Label(arrive, base + buy * prices[i], label, j, buy))

    if best is None:
        raise FuelPlanInfeasible(_gap_message(positions, total_miles, max_range_miles))

    stops = _unwind(best, nodes, mpg)
    return FuelPlan(
        stops=stops,
        total_gallons=sum(s.gallons for s in stops),
        total_cost=sum(s.cost for s in stops),
    )


def _planning_nodes(
    candidates: list[Candidate], total_miles: float, origin_radius_miles: float
) -> list[tuple[float, Candidate]]:
    """(planning position, cheapest candidate there), ordered along the route.

    Several stations can share a position (same city centroid / same route sample);
    only the cheapest of them can ever be worth stopping at.
    """
    cheapest: dict[float, Candidate] = {}
    for c in candidates:
        if c.mile >= total_miles:
            continue
        position = 0.0 if c.mile <= origin_radius_miles else c.mile
        if position not in cheapest or c.price < cheapest[position].price:
            cheapest[position] = c
    return sorted(cheapest.items(), key=lambda item: item[0])


def _pareto(labels: list[_Label]) -> list[_Label]:
    """Drop labels that arrive with less fuel *and* a worse objective than another."""
    labels.sort(key=lambda lab: (-lab.fuel, lab.objective))
    kept: list[_Label] = []
    best_objective = float("inf")
    for label in labels:
        if label.objective < best_objective - EPSILON:
            kept.append(label)
            best_objective = label.objective
    return kept


def _unwind(final: _Label, nodes: list[tuple[float, Candidate]], mpg: float) -> list[FuelStop]:
    stops: list[FuelStop] = []
    label = final
    while label.parent is not None:
        candidate = nodes[label.parent.node][1]
        gallons = label.bought_miles / mpg
        if gallons > EPSILON:
            stops.append(FuelStop(candidate, gallons, gallons * candidate.price))
        label = label.parent
    stops.reverse()
    return stops


def _gap_message(positions: list[float], total_miles: float, max_range_miles: float) -> str:
    previous = 0.0
    for position in [*positions, total_miles]:
        if position - previous > max_range_miles:
            break
        previous = position
    return (
        f"No fuel station within {max_range_miles:.0f} miles after mile {previous:.0f}; "
        "the trip cannot be completed with this range."
    )
