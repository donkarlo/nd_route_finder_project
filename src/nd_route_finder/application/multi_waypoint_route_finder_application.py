from collections.abc import Callable
from pathlib import Path

import networkx as nx

from nd_route_finder.analysis.track_analyzer import TrackAnalyzer
from nd_route_finder.domain.route_candidate import RouteCandidate
from nd_route_finder.domain.route_request import RouteRequest
from nd_route_finder.domain.track import Track
from nd_route_finder.geodata.copernicus_dem_provider import CopernicusDemProvider
from nd_route_finder.geodata.elevation_enricher import ElevationEnricher
from nd_route_finder.geodata.multi_waypoint_osm_network_builder import (
    MultiWaypointOsmNetworkBuilder,
)
from nd_route_finder.geodata.obstacle_filter import ObstacleFilter
from nd_route_finder.gpx.gpx_file_finder import GpxFileFinder
from nd_route_finder.gpx.gpx_track_reader import GpxTrackReader
from nd_route_finder.gpx.gpx_track_writer import GpxTrackWriter
from nd_route_finder.routing.multi_waypoint_round_trip_generator import (
    MultiWaypointRoundTripGenerator,
)
from nd_route_finder.ui.map_html_builder import MapHtmlBuilder


class MultiWaypointRouteFinderApplication:
    """Enhanced application path with a best-available GPX fallback."""

    def run(
        self,
        request: RouteRequest,
        status: Callable[[str], None] | None = None,
    ) -> tuple[list[Track], Track, Path, str]:
        notify = status or (lambda _: None)

        notify("Searching recursively for previous GPX files …")
        files = [
            path
            for path in GpxFileFinder().find(request.gpx_root)
            if path.resolve() != request.output_gpx.resolve()
        ]
        previous_tracks = GpxTrackReader().read_many(files)
        analyzer = TrackAnalyzer()
        previous_tracks = [analyzer.analyze(track) for track in previous_tracks]

        waypoints = tuple(getattr(request, "waypoints", ()))
        if waypoints:
            notify(
                f"Loaded {len(previous_tracks)} previous GPX track(s). "
                f"Downloading OSM network for start + {len(waypoints)} intermediate point(s) …"
            )
        else:
            notify(
                f"Loaded {len(previous_tracks)} previous GPX track(s). Downloading OSM network …"
            )
        graph = MultiWaypointOsmNetworkBuilder().build(request)

        notify("Filtering access restrictions, water crossings and barriers …")
        graph = ObstacleFilter().apply(graph, request)

        if waypoints:
            notify(
                "Generating circular candidates through the ordered intermediate points "
                "and searching for distance-compatible detours …"
            )
        else:
            notify(
                "Generating diverse route candidates and using suitable previous GPX tracks as seeds …"
            )
        generator = MultiWaypointRoundTripGenerator()
        candidates = generator.generate_candidates(graph, request, previous_tracks)

        accepted, used_fallback = self._choose_candidate_with_slope(
            graph,
            candidates,
            request,
            notify,
        )
        generated = generator.to_track(graph, accepted)

        if generated.max_grade_percent is None:
            raise RuntimeError("Internal error: generated route has no evaluated slope.")

        if used_fallback:
            generated.metadata["constraint_fallback"] = "true"
            notify(
                "No candidate satisfied every requested constraint; using the closest "
                "available circular route and writing GPX …"
            )
        else:
            generated.metadata["constraint_fallback"] = "false"
            notify(
                f"Accepted route: {generated.distance_m / 1000.0:.1f} km, "
                f"maximum slope {generated.max_grade_percent:.1f}%. Writing and verifying GPX …"
            )

        output = GpxTrackWriter().write(generated, request.output_gpx)
        html = MapHtmlBuilder().build_routes(previous_tracks, generated)
        notify(f"GPX verified on disk: {output}")
        return previous_tracks, generated, output, html

    def _choose_candidate_with_slope(
        self,
        graph: nx.MultiDiGraph,
        candidates: list[RouteCandidate],
        request: RouteRequest,
        notify: Callable[[str], None],
    ) -> tuple[RouteCandidate, bool]:
        enricher = ElevationEnricher()
        provider = CopernicusDemProvider()
        best_fallback: RouteCandidate | None = None
        best_fallback_score = float("inf")

        for index, candidate in enumerate(candidates, start=1):
            if request.dem_path is not None:
                dem_paths = [request.dem_path]
                dem_description = "local DEM"
            else:
                dem_paths = provider.ensure_for_points(candidate.points, notify)
                dem_description = "cached Copernicus GLO-30 DEM"

            missing = enricher.uncached_profile_point_count(graph, candidate)
            notify(
                f"Checking {dem_description} slope for candidate {index}/{len(candidates)} "
                f"({missing} new elevation point(s)) …"
            )
            evaluated = enricher.evaluate_candidate(graph, candidate, dem_paths)
            grade = evaluated.max_grade_percent
            if grade is None:
                continue

            # Preserve the old behavior whenever a slope-compliant candidate exists:
            # candidates are already ordered by the generator's distance/overlap score.
            if grade <= request.max_grade_percent:
                return evaluated, False

            length_error = abs(evaluated.distance_m - request.target_distance_m) / max(
                1.0,
                request.target_distance_m,
            )
            grade_excess = max(0.0, grade - request.max_grade_percent) / max(
                1.0,
                request.max_grade_percent,
            )
            fallback_score = (
                length_error
                + 1.25 * grade_excess
                + 0.15 * evaluated.overlap_ratio
            )
            if fallback_score < best_fallback_score:
                best_fallback = evaluated
                best_fallback_score = fallback_score

        if best_fallback is not None:
            notify(
                f"Slope limit {request.max_grade_percent:.1f}% could not be met exactly. "
                f"Closest available candidate: {best_fallback.distance_m / 1000.0:.1f} km, "
                f"max slope {best_fallback.max_grade_percent:.1f}%."
            )
            return best_fallback, True

        raise RuntimeError("No route candidate could be evaluated for elevation and slope.")
