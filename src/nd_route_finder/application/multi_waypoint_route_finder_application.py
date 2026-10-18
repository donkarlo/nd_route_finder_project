from collections.abc import Callable
from pathlib import Path

import networkx as nx

from nd_route_finder.analysis.track_analyzer import TrackAnalyzer
from nd_route_finder.domain.route_candidate import RouteCandidate
from nd_route_finder.domain.route_request import RouteRequest
from nd_route_finder.domain.track import Track
from nd_route_finder.geodata.copernicus_dem_provider import CopernicusDemProvider
from nd_route_finder.geodata.brouter_route_fallback import BrouterRouteFallback
from nd_route_finder.geodata.overpass_unavailable_error import OverpassUnavailableError
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
from nd_route_finder.routing.route_quality import RouteQuality


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
        try:
            graph = MultiWaypointOsmNetworkBuilder().build(request, notify=notify)
            notify("Filtering access restrictions, water crossings and barriers …")
            graph = ObstacleFilter().apply(graph, request, notify=notify)
        except OverpassUnavailableError:
            return self._brouter_backup(request, previous_tracks, notify)

        route_mode = getattr(request, "route_mode", "circular")
        if route_mode == "direct":
            notify("Finding a point-to-point route through the selected stops …")
        elif waypoints:
            notify(
                "Generating circular candidates through the ordered intermediate points "
                "and searching for distance-compatible detours …"
            )
        else:
            notify(
                "Generating diverse route candidates and using suitable previous GPX tracks as seeds …"
            )
        generator = MultiWaypointRoundTripGenerator()
        try:
            candidates = generator.generate_candidates(graph, request, previous_tracks)
        except (RuntimeError, nx.NetworkXNoPath, nx.NodeNotFound) as exc:
            # The filtered graph can be disconnected or its chosen nodes may
            # snap to separate components. Never treat this as proof that no
            # alternative route exists on a different cycling network.
            if not isinstance(exc, (nx.NetworkXNoPath, nx.NodeNotFound)) and not any(
                term in str(exc).lower() for term in (
                    "no legal", "cannot", "not enough reachable", "no usable",
                    "no circular", "no route candidate", "no usable round-trip",
                )
            ):
                raise
            notify(f"The local OSM graph could not connect the stops; trying routed alternatives …")
            return self._brouter_backup(request, previous_tracks, notify)

        accepted, used_fallback = self._choose_candidate_with_slope(
            graph,
            candidates,
            request,
            notify,
            previous_tracks=previous_tracks,
        )
        generated = generator.to_track(graph, accepted)
        if route_mode == "direct":
            generated.name = "generated_direct_route"
        generated.metadata["route_mode"] = route_mode

        if generated.max_grade_percent is None:
            raise RuntimeError("Internal error: generated route has no evaluated slope.")

        if used_fallback:
            generated.metadata["constraint_fallback"] = "true"
            notify(
                "No candidate satisfied every requested constraint; using the closest "
                "available route and writing GPX …"
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

    def _brouter_backup(
        self,
        request: RouteRequest,
        previous_tracks: list[Track],
        notify: Callable[[str], None],
    ) -> tuple[list[Track], Track, Path, str]:
        generated = BrouterRouteFallback().generate(
            request, notify=notify, previous_tracks=previous_tracks
        )
        generated.metadata.setdefault("constraint_fallback", "true")
        output = GpxTrackWriter().write(generated, request.output_gpx)
        html = MapHtmlBuilder().build_routes(previous_tracks, generated)
        notify(
            f"BRouter backup saved: {output}; {generated.distance_m/1000:.2f} km, "
            f"grade {generated.max_grade_percent:.1f}%, "
            f"overlap with previous GPX {float(generated.metadata.get('history_overlap', 0.0)):.0%}. "
            "Independent OSM obstacle verification could not be completed."
        )
        return previous_tracks, generated, output, html

    def _choose_candidate_with_slope(
        self,
        graph: nx.MultiDiGraph,
        candidates: list[RouteCandidate],
        request: RouteRequest,
        notify: Callable[[str], None],
        previous_tracks: list[Track] | None = None,
    ) -> tuple[RouteCandidate, bool]:
        """Always choose the best *evaluated* candidate, even if none matches exactly.

        An acceptable slope alone isn't enough; proximity to target distance,
        overlap with previously travelled GPX files and retracing are considered
        together before selecting the final candidate.
        """
        enricher = ElevationEnricher()
        provider = CopernicusDemProvider()
        quality = RouteQuality(previous_tracks or [], request.start_latitude)
        ranked: list[tuple[float, RouteCandidate]] = []
        requested_waypoints = getattr(request, 'waypoints', ())
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
            points = evaluated.points
            historical_overlap = quality.historical_overlap(points)
            self_retrace = (
                quality.self_retrace(points, requested_waypoints[-1])
                if requested_waypoints and getattr(request, 'route_mode', 'circular') == 'circular'
                else evaluated.overlap_ratio
            )
            score = quality.score(evaluated.distance_m, grade,
                                  historical_overlap, self_retrace, request)
            ranked.append((score, evaluated))
            notify(f"Candidate {index}: {evaluated.distance_m/1000:.2f} km, "
                   f"max grade {grade:.1f}%, past GPX overlap {historical_overlap:.0%}, "
                   f"score {score:.3f} …")
        if not ranked:
            raise RuntimeError("No route candidate could be evaluated for elevation and slope.")
        ranked.sort(key=lambda pair: pair[0])
        score, best = ranked[0]
        grade = float(best.max_grade_percent)
        preference = getattr(request, 'route_preference', 'distance')
        distance_matched = (preference == 'shortest' or
                            abs(best.distance_m - request.target_distance_m) <= request.target_distance_m * 0.10)
        constraint_fallback = not distance_matched or grade > request.max_grade_percent
        notify(f"Best available of {len(ranked)} candidates: {best.distance_m/1000:.2f} km, "
               f"grade {grade:.1f}%, score {score:.3f}. "
               + ("One or more requested targets could not be met exactly."
                  if constraint_fallback else "Matches distance and slope targets."))
        return best, constraint_fallback
