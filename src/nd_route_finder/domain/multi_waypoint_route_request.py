from dataclasses import dataclass

from nd_route_finder.domain.geo_point import GeoPoint
from nd_route_finder.domain.route_request import RouteRequest


@dataclass(slots=True, frozen=True)
class MultiWaypointRouteRequest(RouteRequest):
    """Backward-compatible RouteRequest with optional ordered intermediate points."""

    waypoints: tuple[GeoPoint, ...] = ()
