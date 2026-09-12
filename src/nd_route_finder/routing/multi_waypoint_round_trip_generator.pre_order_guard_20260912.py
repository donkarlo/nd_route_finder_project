import math
import random

import networkx as nx
import osmnx as ox

from nd_route_finder.domain.route_candidate import RouteCandidate
from nd_route_finder.domain.route_request import RouteRequest
from nd_route_finder.domain.track import Track
from nd_route_finder.routing.round_trip_generator import RoundTripGenerator


class MultiWaypointRoundTripGenerator(RoundTripGenerator):
    """
    Adds ordered intermediate-point routing without changing the successful path of
    the original one-point generator. With no waypoints, the original generator is
    tried first and its result is returned unchanged. A more permissive one-point
    search is used only if the original generator cannot produce any candidate.
    """

    _MAX_MULTI_CANDIDATES = 48
    _MAX_DETOUR_ATTEMPTS = 180
    _MAX_SINGLE_FALLBACK_CANDIDATES = 36

    def generate_candidates(
        self,
        graph: nx.MultiDiGraph,
        request: RouteRequest,
        previous_tracks: list[Track] | None = None,
    ) -> list[RouteCandidate]:
        waypoints = tuple(getattr(request, "waypoints", ()))
        if not waypoints:
            # Preserve the current one-start-point logic byte-for-byte on the normal
            # successful path. Only extend behavior where it used to fail outright.
            try:
                return super().generate_candidates(graph, request, previous_tracks)
            except RuntimeError as original_error:
                fallback = self._single_point_fallback_candidates(graph, request)
                if fallback:
                    return fallback
                raise original_error

        self._add_route_cost(graph, request.activity)
        start = int(
            ox.distance.nearest_nodes(
                graph,
                X=request.start_longitude,
                Y=request.start_latitude,
            )
        )
        mandatory_nodes = [
            int(
                ox.distance.nearest_nodes(
                    graph,
                    X=point.longitude,
                    Y=point.latitude,
                )
            )
            for point in waypoints
        ]

        generated: list[RouteCandidate] = []
        seen_routes: set[tuple[int, ...]] = set()

        base_route = self._route_through_waypoints(graph, start, mandatory_nodes)
        if base_route is None:
            raise RuntimeError(
                "The selected intermediate points cannot all be connected in the requested order."
            )
        self._append_route_candidate(
            graph,
            request,
            base_route,
            generated,
            seen_routes,
        )

        # Candidate detours are inserted around the ordered mandatory points. The
        # user-selected waypoint order is never changed; only optional detour nodes
        # are inserted so the loop can approach the requested total length.
        candidate_nodes = self._candidate_nodes(graph, start, request.target_distance_m)
        candidate_nodes = [
            node
            for node in candidate_nodes
            if node != start and node not in mandatory_nodes
        ]
        rng = random.Random(20260912)
        rng.shuffle(candidate_nodes)
        candidate_nodes = candidate_nodes[:90]

        insertion_slots = len(mandatory_nodes) + 1
        attempts = 0
        for detour in candidate_nodes:
            slot_order = list(range(insertion_slots))
            rng.shuffle(slot_order)
            for slot in slot_order[: min(3, insertion_slots)]:
                ordered_nodes = list(mandatory_nodes)
                ordered_nodes.insert(slot, detour)
                route = self._route_through_waypoints(graph, start, ordered_nodes)
                attempts += 1
                if route is not None:
                    self._append_route_candidate(
                        graph,
                        request,
                        route,
                        generated,
                        seen_routes,
                    )
                if attempts >= self._MAX_DETOUR_ATTEMPTS:
                    break
            if attempts >= self._MAX_DETOUR_ATTEMPTS:
                break

        # When the mandatory loop is substantially shorter than requested, also try
        # a modest set of two-detour variants. Mandatory points still keep their
        # exact user-defined order.
        base_distance = generated[0].distance_m if generated else 0.0
        if (
            candidate_nodes
            and base_distance < request.target_distance_m * 0.82
            and len(candidate_nodes) >= 2
        ):
            pair_attempts = min(55, len(candidate_nodes) * 2)
            for _ in range(pair_attempts):
                first, second = rng.sample(candidate_nodes, 2)
                first_slot = rng.randrange(insertion_slots)
                second_slot = rng.randrange(insertion_slots)
                if second_slot < first_slot:
                    first, second = second, first
                    first_slot, second_slot = second_slot, first_slot

                ordered_nodes = list(mandatory_nodes)
                ordered_nodes.insert(first_slot, first)
                ordered_nodes.insert(second_slot + 1, second)
                route = self._route_through_waypoints(graph, start, ordered_nodes)
                if route is not None:
                    self._append_route_candidate(
                        graph,
                        request,
                        route,
                        generated,
                        seen_routes,
                    )

        if not generated:
            raise RuntimeError("No circular route through the selected intermediate points was found.")

        generated.sort(key=lambda candidate: candidate.base_score)
        return generated[: self._MAX_MULTI_CANDIDATES]

    def _single_point_fallback_candidates(
        self,
        graph: nx.MultiDiGraph,
        request: RouteRequest,
    ) -> list[RouteCandidate]:
        """Return nearest-length loops when the original strict candidate search fails."""
        self._add_route_cost(graph, request.activity)
        start = int(
            ox.distance.nearest_nodes(
                graph,
                X=request.start_longitude,
                Y=request.start_latitude,
            )
        )

        lengths = nx.single_source_dijkstra_path_length(
            graph,
            start,
            weight="route_cost",
        )
        reachable = [int(node) for node, distance in lengths.items() if node != start and distance > 0.0]
        if not reachable:
            return []

        # A triangular loop often has a radial leg close to one third of the target.
        # Ranking around that distance keeps the search useful even when the target
        # is outside the originally accepted +/-50% window.
        preferred_leg_m = max(1.0, request.target_distance_m / 3.0)
        reachable.sort(key=lambda node: abs(float(lengths[node]) - preferred_leg_m))
        candidate_nodes = reachable[:120]

        generated: list[RouteCandidate] = []
        seen_routes: set[tuple[int, ...]] = set()
        rng = random.Random(20260912)
        pairs = self._candidate_pairs(graph, start, candidate_nodes, rng)
        for first, second in pairs[:360]:
            route = self._permissive_triangle_route(graph, start, first, second)
            if route is None:
                continue
            self._append_route_candidate(
                graph,
                request,
                route,
                generated,
                seen_routes,
            )

        # Very small/fragmented networks may not offer two useful intermediate
        # nodes. An out-and-back loop is still a valid GPX and is preferable to
        # returning no file at all.
        if not generated:
            for node in candidate_nodes[:80]:
                route = self._out_and_back_route(graph, start, node)
                if route is None:
                    continue
                self._append_route_candidate(
                    graph,
                    request,
                    route,
                    generated,
                    seen_routes,
                )

        generated.sort(key=lambda candidate: candidate.base_score)
        return generated[: self._MAX_SINGLE_FALLBACK_CANDIDATES]

    def _permissive_triangle_route(
        self,
        graph: nx.MultiDiGraph,
        start: int,
        first: int,
        second: int,
    ) -> list[int] | None:
        try:
            route_a = nx.shortest_path(graph, start, first, weight="route_cost")
            route_b = nx.shortest_path(graph, first, second, weight="route_cost")
            route_c = nx.shortest_path(graph, second, start, weight="route_cost")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
        route = [int(node) for node in route_a + route_b[1:] + route_c[1:]]
        return route if len(route) >= 3 else None

    def _out_and_back_route(
        self,
        graph: nx.MultiDiGraph,
        start: int,
        node: int,
    ) -> list[int] | None:
        try:
            outbound = nx.shortest_path(graph, start, node, weight="route_cost")
            inbound = nx.shortest_path(graph, node, start, weight="route_cost")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
        route = [int(item) for item in outbound + inbound[1:]]
        return route if len(route) >= 3 else None

    def _append_route_candidate(
        self,
        graph: nx.MultiDiGraph,
        request: RouteRequest,
        route: list[int],
        generated: list[RouteCandidate],
        seen_routes: set[tuple[int, ...]],
    ) -> None:
        route_key = tuple(route)
        if route_key in seen_routes:
            return
        distance_m = self._route_distance(graph, route)
        if distance_m <= 0.0:
            return
        seen_routes.add(route_key)

        length_error = abs(distance_m - request.target_distance_m) / max(
            1.0,
            request.target_distance_m,
        )
        overlap_penalty = self._overlap_ratio(route)
        generated.append(
            RouteCandidate(
                nodes=route,
                distance_m=distance_m,
                overlap_ratio=overlap_penalty,
                base_score=length_error + 0.65 * overlap_penalty,
                points=self._route_points(graph, route),
            )
        )
