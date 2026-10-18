from collections.abc import Callable

import networkx as nx
import osmnx as ox

from nd_route_finder.domain.activity_type import ActivityType
from nd_route_finder.domain.route_request import RouteRequest
from nd_route_finder.geodata.overpass_fallback import OverpassFallback


class OsmNetworkBuilder:
    def build(
        self, request: RouteRequest, notify: Callable[[str], None] | None = None
    ) -> nx.MultiDiGraph:
        self._ensure_useful_tags()
        graph = OverpassFallback().execute(
            lambda: ox.graph.graph_from_point(
                center_point=(request.start_latitude, request.start_longitude),
                dist=request.graph_radius_m,
                dist_type="bbox",
                network_type=ActivityType(request.activity).osmnx_network_type,
                simplify=True,
                retain_all=False,
                truncate_by_edge=True,
            ),
            purpose="routing network",
            notify=notify,
        )
        return graph

    def _ensure_useful_tags(self) -> None:
        for tag in (
            "access",
            "bicycle",
            "foot",
            "bridge",
            "tunnel",
            "ford",
            "surface",
            "smoothness",
            "tracktype",
            "incline",
        ):
            if tag not in ox.settings.useful_tags_way:
                ox.settings.useful_tags_way.append(tag)

        for tag in ("barrier", "access", "bicycle", "foot", "entrance", "ford"):
            if tag not in ox.settings.useful_tags_node:
                ox.settings.useful_tags_node.append(tag)
