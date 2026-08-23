from collections.abc import Mapping

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd
from shapely.geometry.base import BaseGeometry

from nd_route_finder.domain.activity_type import ActivityType
from nd_route_finder.domain.route_request import RouteRequest


class ObstacleFilter:
    _BLOCKED_BARRIERS = {"fence", "wall", "hedge", "retaining_wall", "chain"}
    _OPEN_BARRIERS = {"gate", "lift_gate", "swing_gate"}
    _WATERWAYS = {"river", "stream", "canal", "drain", "ditch"}
    _NO_ACCESS = {"no", "private"}

    def apply(self, graph: nx.MultiDiGraph, request: RouteRequest) -> nx.MultiDiGraph:
        features = self._download_obstacles(request)
        edges = ox.convert.graph_to_gdfs(graph, nodes=False, edges=True)
        edges_projected = ox.projection.project_gdf(edges)
        features_projected = (
            features.to_crs(edges_projected.crs) if not features.empty else features
        )

        water = self._water_features(features_projected)
        blocked = self._blocked_barriers(features_projected)
        openings = self._openings(features_projected)

        filtered = graph.copy()
        to_remove: list[tuple[int, int, int]] = []

        for edge_id, row in edges_projected.iterrows():
            u, v, key = edge_id
            data = graph.get_edge_data(u, v, key)
            if data is None:
                continue

            if self._fails_access(data, request.activity):
                to_remove.append((u, v, key))
                continue

            if self._is_unbridged_ford(graph, u, v, data):
                to_remove.append((u, v, key))
                continue

            geometry = row.geometry
            if self._crosses_water(geometry, water) and not self._is_bridge(data):
                to_remove.append((u, v, key))
                continue

            if self._crosses_blocked_barrier_without_opening(geometry, blocked, openings):
                to_remove.append((u, v, key))

        filtered.remove_edges_from(to_remove)
        filtered.remove_nodes_from(list(nx.isolates(filtered)))

        if filtered.number_of_edges() == 0:
            raise RuntimeError("All candidate route edges were removed by the safety constraints.")
        return filtered

    def _download_obstacles(self, request: RouteRequest) -> gpd.GeoDataFrame:
        tags: dict[str, object] = {
            "waterway": list(self._WATERWAYS),
            "natural": "water",
            "water": True,
            "barrier": list(self._BLOCKED_BARRIERS | self._OPEN_BARRIERS),
        }
        try:
            return ox.features.features_from_point(
                (request.start_latitude, request.start_longitude),
                tags=tags,
                dist=request.graph_radius_m,
            )
        except ox._errors.InsufficientResponseError:
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    def _water_features(self, features: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        if features.empty:
            return features
        mask = pd.Series(False, index=features.index)
        if "waterway" in features.columns:
            mask |= features["waterway"].isin(self._WATERWAYS)
        if "natural" in features.columns:
            mask |= features["natural"].eq("water")
        if "water" in features.columns:
            mask |= features["water"].notna()
        return features.loc[mask]

    def _blocked_barriers(self, features: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        if features.empty or "barrier" not in features.columns:
            return features.iloc[0:0]
        return features.loc[features["barrier"].isin(self._BLOCKED_BARRIERS)]

    def _openings(self, features: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        if features.empty:
            return features.iloc[0:0]
        mask = pd.Series(False, index=features.index)
        if "barrier" in features.columns:
            mask |= features["barrier"].isin(self._OPEN_BARRIERS)
        return features.loc[mask]

    def _fails_access(self, data: Mapping[str, object], activity: ActivityType) -> bool:
        if self._tag_in(data.get("access"), self._NO_ACCESS):
            return True
        if activity is ActivityType.CYCLING and self._tag_in(data.get("bicycle"), {"no"}):
            return True
        if activity is ActivityType.CYCLING and self._tag_in(data.get("smoothness"), {"impassable"}):
            return True
        if activity is ActivityType.HIKING and self._tag_in(data.get("foot"), {"no"}):
            return True
        return False

    def _is_unbridged_ford(
        self,
        graph: nx.MultiDiGraph,
        u: int,
        v: int,
        data: Mapping[str, object],
    ) -> bool:
        if self._is_bridge(data):
            return False
        if self._positive_tag(data.get("ford")):
            return True
        return self._positive_tag(graph.nodes[u].get("ford")) or self._positive_tag(
            graph.nodes[v].get("ford")
        )

    def _is_bridge(self, data: Mapping[str, object]) -> bool:
        value = data.get("bridge")
        values = value if isinstance(value, list) else [value]
        for item in values:
            text = str(item).strip().lower()
            if text not in {"", "none", "nan", "no", "false", "0"}:
                return True
        return False

    def _positive_tag(self, value: object) -> bool:
        values = value if isinstance(value, list) else [value]
        for item in values:
            if item is None:
                continue
            if str(item).strip().lower() not in {"", "no", "false", "0", "none", "nan"}:
                return True
        return False

    def _tag_in(self, value: object, forbidden: set[str]) -> bool:
        values = value if isinstance(value, list) else [value]
        return any(str(item).lower() in forbidden for item in values if item is not None)

    def _crosses_water(self, geometry: BaseGeometry, water: gpd.GeoDataFrame) -> bool:
        if water.empty or geometry is None or geometry.is_empty:
            return False
        positions = list(water.sindex.query(geometry, predicate="intersects"))
        for position in positions:
            obstacle = water.geometry.iloc[position]
            if obstacle is None or obstacle.is_empty:
                continue
            obstacle_type = obstacle.geom_type
            if "Polygon" in obstacle_type:
                if geometry.crosses(obstacle) or geometry.within(obstacle):
                    return True
            elif "LineString" in obstacle_type:
                if geometry.crosses(obstacle) or geometry.overlaps(obstacle):
                    return True
        return False

    def _crosses_blocked_barrier_without_opening(
        self,
        geometry: BaseGeometry,
        blocked: gpd.GeoDataFrame,
        openings: gpd.GeoDataFrame,
    ) -> bool:
        if blocked.empty or geometry is None or geometry.is_empty:
            return False

        positions = list(blocked.sindex.query(geometry, predicate="intersects"))
        for position in positions:
            barrier = blocked.geometry.iloc[position]
            if barrier is None or barrier.is_empty:
                continue
            crossing = geometry.intersection(barrier)
            if crossing.is_empty:
                continue
            if openings.empty:
                return True
            nearby = list(openings.sindex.query(crossing.buffer(4.0), predicate="intersects"))
            if not nearby:
                return True
        return False
