import math

import networkx as nx
import osmnx as ox

from nd_route_finder.domain.activity_type import ActivityType
from nd_route_finder.domain.geo_point import GeoPoint
from nd_route_finder.domain.route_request import RouteRequest
from nd_route_finder.geodata.osm_network_builder import OsmNetworkBuilder


class MultiWaypointOsmNetworkBuilder(OsmNetworkBuilder):
    """Expands the OSM download area only when intermediate waypoints are used."""

    _EARTH_RADIUS_M = 6_371_008.8

    def build(self, request: RouteRequest) -> nx.MultiDiGraph:
        waypoints = tuple(getattr(request, "waypoints", ()))
        if not waypoints:
            return super().build(request)

        self._ensure_useful_tags()
        points = (
            GeoPoint(request.start_latitude, request.start_longitude),
            *waypoints,
        )
        center_latitude = sum(point.latitude for point in points) / len(points)
        center_longitude = sum(point.longitude for point in points) / len(points)
        center = GeoPoint(center_latitude, center_longitude)
        farthest_m = max(self._distance(center, point) for point in points)

        # Keep the old single-point radius semantics as the minimum, but make sure
        # every explicitly selected waypoint is comfortably inside the downloaded
        # network. The extra margin leaves room for detours used to match distance.
        detour_margin_m = max(
            1_200.0,
            min(5_000.0, request.target_distance_m * 0.18),
        )
        radius_m = max(request.graph_radius_m, farthest_m + detour_margin_m)

        return ox.graph.graph_from_point(
            center_point=(center_latitude, center_longitude),
            dist=radius_m,
            dist_type="bbox",
            network_type=ActivityType(request.activity).osmnx_network_type,
            simplify=True,
            retain_all=False,
            truncate_by_edge=True,
        )

    def _distance(self, first: GeoPoint, second: GeoPoint) -> float:
        lat1 = math.radians(first.latitude)
        lat2 = math.radians(second.latitude)
        dlat = lat2 - lat1
        dlon = math.radians(second.longitude - first.longitude)
        a = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
        )
        return 2.0 * self._EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))
