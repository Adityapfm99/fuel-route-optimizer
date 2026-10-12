class TripPlanningError(Exception):
    """Base error; ``status`` is the HTTP status the API should answer with."""

    status = 400


class LocationNotFound(TripPlanningError):
    status = 404


class LocationOutsideUSA(TripPlanningError):
    status = 422


class RoutingUnavailable(TripPlanningError):
    status = 502


class NoRouteFound(TripPlanningError):
    status = 422


class FuelPlanInfeasible(TripPlanningError):
    status = 422
