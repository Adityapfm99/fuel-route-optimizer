import json
import time
from urllib.parse import urlencode

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .services.exceptions import TripPlanningError
from .services.trip_planner import plan_trip

RESPONSE_ORDER = (
    "start",
    "finish",
    "total_fuel_cost",
    "total_gallons",
    "map_url",
    "fuel_stops",
    "vehicle",
    "meta",
    "route",
)


def _read_params(request: HttpRequest) -> tuple[str, str]:
    if request.method == "POST" and request.content_type == "application/json":
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            body = {}
        return str(body.get("start", "")), str(body.get("finish", ""))
    params = request.POST if request.method == "POST" else request.GET
    return params.get("start", ""), params.get("finish", "")


@csrf_exempt
@require_http_methods(["GET", "POST"])
def route_plan(request: HttpRequest) -> JsonResponse:
    """Plan a trip: route, optimal fuel stops and total fuel cost.

    GET  /api/route/?start=Chicago, IL&finish=Houston, TX
    POST /api/route/   {"start": "Chicago, IL", "finish": "Houston, TX"}
    """
    start, finish = _read_params(request)
    if not start or not finish:
        return JsonResponse({"error": "Both 'start' and 'finish' are required."}, status=400)

    began = time.perf_counter()
    try:
        plan = plan_trip(start, finish)
    except TripPlanningError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status)

    query = urlencode({"start": start, "finish": finish})
    plan["map_url"] = request.build_absolute_uri(f"{reverse('route-map')}?{query}")
    plan["meta"]["elapsed_ms"] = round((time.perf_counter() - began) * 1000, 1)
    # Summary first, the (long) route geometry last, so the answer is readable at a glance.
    ordered = {key: plan[key] for key in RESPONSE_ORDER}
    return JsonResponse(ordered)


@require_GET
def route_map(request: HttpRequest) -> HttpResponse:
    """Interactive Leaflet map of the planned route and its fuel stops."""
    start, finish = request.GET.get("start", ""), request.GET.get("finish", "")
    if not start or not finish:
        return HttpResponse("Both 'start' and 'finish' query parameters are required.", status=400)
    try:
        plan = plan_trip(start, finish)
    except TripPlanningError as exc:
        return HttpResponse(str(exc), status=exc.status)
    return render(request, "fuelroute/map.html", {"plan": plan})
