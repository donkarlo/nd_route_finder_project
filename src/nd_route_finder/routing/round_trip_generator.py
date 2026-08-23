import math
import random
from collections.abc import Mapping

import networkx as nx
import osmnx as ox

from nd_route_finder.domain.activity_type import ActivityType
from nd_route_finder.domain.geo_point import GeoPoint
from nd_route_finder.domain.route_candidate import RouteCandidate
from nd_route_finder.domain.route_request import RouteRequest
from nd_route_finder.domain.track import Track


class RoundTripGenerator:
    _MAX_CANDIDATES = 36
    _MAX_HISTORY_SEEDS = 12
    _HISTORY_START_TOLERANCE_M = 1800.0
    _EARTH_RADIUS_M = 6_371_008.8

    def generate_candidates(
        self,
        graph: nx.MultiDiGraph,
        request: RouteRequest,
        previous_tracks: list[Track] | None = None,
    ) -> list[RouteCandidate]:
        self._add_route_cost(graph, request.activity)
        start = int(
            ox.distance.nearest_nodes(
                graph,
                X=request.start_longitude,
                Y=request.start_latitude,
            )
        )

        generated: list[RouteCandidate] = []
        seen_routes: set[tuple[int, ...]] = set()

        if previous_tracks:
            for candidate in self._history_seed_candidates(
                graph,
                start,
                request,
                previous_tracks,
            ):
                self._append_unique(generated, seen_routes, candidate)

        candidate_nodes = self._candidate_nodes(graph, start, request.target_distance_m)
        if len(candidate_nodes) < 2 and not generated:
            raise RuntimeError(
                "Not enough reachable nodes remain after access/obstacle filtering."
            )

        rng = random.Random(20260816)
        for first, second in self._candidate_pairs(graph, start, candidate_nodes, rng):
            candidate = self._triangle_candidate(graph, start, first, second, request)
            if candidate is not None:
                self._append_unique(generated, seen_routes, candidate)

        if not generated:
            raise RuntimeError("No usable round-trip candidates could be generated.")

        generated.sort(key=lambda candidate: candidate.base_score)
        return generated[: self._MAX_CANDIDATES]

    def to_track(self, graph: nx.MultiDiGraph, candidate: RouteCandidate) -> Track:
        points = candidate.points or [
            GeoPoint(
                latitude=float(graph.nodes[node]["y"]),
                longitude=float(graph.nodes[node]["x"]),
            )
            for node in candidate.nodes
        ]
        return Track(
            name="generated_round_trip",
            segments=[points],
            distance_m=candidate.distance_m,
            max_grade_percent=candidate.max_grade_percent,
            metadata={
                "node_count": str(len(candidate.nodes)),
                "overlap_ratio": f"{candidate.overlap_ratio:.4f}",
            },
        )

    def _history_seed_candidates(
        self,
        graph: nx.MultiDiGraph,
        start: int,
        request: RouteRequest,
        tracks: list[Track],
    ) -> list[RouteCandidate]:
        ranked: list[tuple[float, Track]] = []
        request_start = GeoPoint(request.start_latitude, request.start_longitude)

        for track in tracks:
            if track.distance_m <= 0.0 or not track.segments:
                continue
            distance_ratio = track.distance_m / request.target_distance_m
            if not 0.60 <= distance_ratio <= 1.45:
                continue
            segment = max(track.segments, key=len)
            if len(segment) < 8:
                continue
            nearest_start_distance = min(
                self._distance(request_start, point)
                for point in (segment[0], segment[-1])
            )
            if nearest_start_distance > self._HISTORY_START_TOLERANCE_M:
                continue

            length_error = abs(track.distance_m - request.target_distance_m) / request.target_distance_m
            grade_penalty = 0.0
            if track.max_grade_percent is not None and track.max_grade_percent > request.max_grade_percent:
                grade_penalty = (track.max_grade_percent - request.max_grade_percent) / max(
                    1.0, request.max_grade_percent
                )
            ranked.append((length_error + 0.35 * grade_penalty, track))

        ranked.sort(key=lambda item: item[0])
        result: list[RouteCandidate] = []

        for _, track in ranked[: self._MAX_HISTORY_SEEDS]:
            segment = max(track.segments, key=len)
            anchors = [
                self._point_at_fraction(segment, fraction)
                for fraction in (1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6)
            ]
            waypoint_nodes = [
                int(ox.distance.nearest_nodes(graph, X=point.longitude, Y=point.latitude))
                for point in anchors
            ]
            route = self._route_through_waypoints(graph, start, waypoint_nodes)
            if route is None:
                continue

            distance_m = self._route_distance(graph, route)
            if distance_m <= 0.0:
                continue
            length_error = abs(distance_m - request.target_distance_m) / request.target_distance_m
            if length_error > 0.45:
                continue

            overlap_penalty = self._overlap_ratio(route)
            score = max(0.0, length_error + 0.65 * overlap_penalty - 0.18)
            result.append(
                RouteCandidate(
                    nodes=route,
                    distance_m=distance_m,
                    overlap_ratio=overlap_penalty,
                    base_score=score,
                    points=self._route_points(graph, route),
                )
            )

        return result

    def _route_through_waypoints(
        self,
        graph: nx.MultiDiGraph,
        start: int,
        waypoints: list[int],
    ) -> list[int] | None:
        route = [start]
        current = start
        try:
            for waypoint in waypoints:
                if waypoint == current:
                    continue
                leg = nx.shortest_path(graph, current, waypoint, weight="route_cost")
                route.extend(int(node) for node in leg[1:])
                current = waypoint
            if current != start:
                leg = nx.shortest_path(graph, current, start, weight="route_cost")
                route.extend(int(node) for node in leg[1:])
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
        return route if len(route) >= 3 else None

    def _triangle_candidate(
        self,
        graph: nx.MultiDiGraph,
        start: int,
        first: int,
        second: int,
        request: RouteRequest,
    ) -> RouteCandidate | None:
        try:
            route_a = nx.shortest_path(graph, start, first, weight="route_cost")
            route_b = nx.shortest_path(graph, first, second, weight="route_cost")
            route_c = nx.shortest_path(graph, second, start, weight="route_cost")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

        route = [int(node) for node in route_a + route_b[1:] + route_c[1:]]
        distance_m = self._route_distance(graph, route)
        if distance_m <= 0.0:
            return None

        length_error = abs(distance_m - request.target_distance_m) / request.target_distance_m
        if length_error > 0.50:
            return None

        overlap_penalty = self._overlap_ratio(route)
        score = length_error + 0.65 * overlap_penalty
        return RouteCandidate(
            nodes=route,
            distance_m=distance_m,
            overlap_ratio=overlap_penalty,
            base_score=score,
            points=self._route_points(graph, route),
        )

    def _append_unique(
        self,
        generated: list[RouteCandidate],
        seen_routes: set[tuple[int, ...]],
        candidate: RouteCandidate,
    ) -> None:
        route_key = tuple(candidate.nodes)
        if route_key in seen_routes:
            return
        seen_routes.add(route_key)
        generated.append(candidate)

    def _point_at_fraction(self, points: list[GeoPoint], fraction: float) -> GeoPoint:
        if len(points) == 1:
            return points[0]
        cumulative = [0.0]
        for first, second in zip(points, points[1:]):
            cumulative.append(cumulative[-1] + self._distance(first, second))
        total = cumulative[-1]
        if total <= 0.0:
            return points[min(len(points) - 1, round(fraction * (len(points) - 1)))]
        target = total * fraction
        for index in range(1, len(cumulative)):
            if cumulative[index] >= target:
                return points[index]
        return points[-1]

    def _route_points(
        self,
        graph: nx.MultiDiGraph,
        route: list[int],
    ) -> list[GeoPoint]:
        points: list[GeoPoint] = []
        for u, v in zip(route, route[1:]):
            edges = graph.get_edge_data(u, v)
            if not edges:
                continue
            best = min(
                edges.values(),
                key=lambda data: float(data.get("route_cost", math.inf)),
            )
            geometry = best.get("geometry")
            if geometry is not None and hasattr(geometry, "coords"):
                coords = [(float(x), float(y)) for x, y in geometry.coords]
                ux = float(graph.nodes[u]["x"])
                uy = float(graph.nodes[u]["y"])
                first_distance = (coords[0][0] - ux) ** 2 + (coords[0][1] - uy) ** 2
                last_distance = (coords[-1][0] - ux) ** 2 + (coords[-1][1] - uy) ** 2
                if last_distance < first_distance:
                    coords.reverse()
            else:
                coords = [
                    (float(graph.nodes[u]["x"]), float(graph.nodes[u]["y"])),
                    (float(graph.nodes[v]["x"]), float(graph.nodes[v]["y"])),
                ]

            for longitude, latitude in coords:
                point = GeoPoint(latitude=latitude, longitude=longitude)
                if not points or (
                    abs(points[-1].latitude - point.latitude) > 1e-10
                    or abs(points[-1].longitude - point.longitude) > 1e-10
                ):
                    points.append(point)
        return points

    def _add_route_cost(self, graph: nx.MultiDiGraph, activity: ActivityType) -> None:
        for _, _, _, data in graph.edges(keys=True, data=True):
            length = float(data.get("length", 1.0))
            surface_penalty = self._surface_penalty(data, activity)
            data["route_cost"] = length * (1.0 + surface_penalty)

    def _surface_penalty(
        self,
        data: Mapping[str, object],
        activity: ActivityType,
    ) -> float:
        if activity is ActivityType.HIKING:
            return 0.0
        surface = str(data.get("surface", "")).lower()
        smoothness = str(data.get("smoothness", "")).lower()
        penalty = 0.0
        if surface in {"sand", "mud", "deep_gravel", "grass", "ground"}:
            penalty += 1.5
        elif surface in {"gravel", "fine_gravel", "unpaved", "dirt"}:
            penalty += 0.35
        if smoothness in {"very_bad", "horrible", "very_horrible", "impassable"}:
            penalty += 2.0
        return penalty

    def _candidate_nodes(
        self,
        graph: nx.MultiDiGraph,
        start: int,
        target_m: float,
    ) -> list[int]:
        cutoff = target_m * 0.52
        lengths = nx.single_source_dijkstra_path_length(
            graph,
            start,
            cutoff=cutoff,
            weight="length",
        )
        low = target_m * 0.14
        high = target_m * 0.44
        candidates = [int(node) for node, distance in lengths.items() if low <= distance <= high]
        if len(candidates) <= 120:
            return candidates

        candidates.sort(key=lambda node: float(lengths[node]))
        step = max(1, len(candidates) // 120)
        return candidates[::step][:120]

    def _candidate_pairs(
        self,
        graph: nx.MultiDiGraph,
        start: int,
        candidates: list[int],
        rng: random.Random,
    ) -> list[tuple[int, int]]:
        if len(candidates) < 2:
            return []

        sx = float(graph.nodes[start]["x"])
        sy = float(graph.nodes[start]["y"])
        sectors: dict[int, list[int]] = {index: [] for index in range(16)}
        for node in candidates:
            nx_lon = float(graph.nodes[node]["x"])
            nx_lat = float(graph.nodes[node]["y"])
            angle = (math.degrees(math.atan2(nx_lon - sx, nx_lat - sy)) + 360.0) % 360.0
            sector = int(angle // 22.5) % 16
            sectors[sector].append(node)

        pairs: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        sector_order = list(range(16))
        rng.shuffle(sector_order)
        for first_sector in sector_order:
            first_nodes = sectors[first_sector][:6]
            if not first_nodes:
                continue
            offsets = [2, 3, 4, 5, 6, 7]
            rng.shuffle(offsets)
            for offset in offsets:
                second_sector = (first_sector + offset) % 16
                second_nodes = sectors[second_sector][:6]
                if not second_nodes:
                    continue
                first = rng.choice(first_nodes)
                second = rng.choice(second_nodes)
                pair = (first, second)
                if pair not in seen:
                    seen.add(pair)
                    pairs.append(pair)

        attempts = min(320, len(candidates) * 7)
        for _ in range(attempts):
            first, second = rng.sample(candidates, 2)
            pair = (first, second)
            if pair not in seen:
                seen.add(pair)
                pairs.append(pair)
        return pairs

    def _route_distance(self, graph: nx.MultiDiGraph, route: list[int]) -> float:
        total = 0.0
        for u, v in zip(route, route[1:]):
            edges = graph.get_edge_data(u, v)
            if not edges:
                return 0.0
            best = min(
                edges.values(),
                key=lambda data: float(data.get("route_cost", math.inf)),
            )
            total += float(best.get("length", 0.0))
        return total

    def _overlap_ratio(self, route: list[int]) -> float:
        edges = [tuple(sorted((u, v))) for u, v in zip(route, route[1:])]
        if not edges:
            return 1.0
        return 1.0 - len(set(edges)) / len(edges)

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
