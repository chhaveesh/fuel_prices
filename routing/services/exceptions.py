class RoutingError(Exception):
    """Base error for anything that should become a 4xx/5xx API response."""
    status_code = 400


class LocationNotFound(RoutingError):
    status_code = 404


class RouteProviderError(RoutingError):
    status_code = 502


class NoFeasibleRoute(RoutingError):
    """Route exists but has a gap longer than the vehicle range with no station."""
    status_code = 422
