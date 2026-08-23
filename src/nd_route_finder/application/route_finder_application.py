from collections.abc import Callable
from pathlib import Path

import networkx as nx

from nd_route_finder.analysis.track_analyzer import TrackAnalyzer
from nd_route_finder.domain.route_candidate import RouteCandidate
from nd_route_finder.domain.route_request import RouteRequest
from nd_route_finder.domain.track import Track
from nd_route_finder.geodata.copernicus_dem_provider import CopernicusDemProvider
from nd_route_finder.geodata.elevation_enricher import ElevationEnricher
from nd_route_finder.geodata.obstacle_filter import ObstacleFilter
from nd_route_finder.geodata.osm_network_builder import OsmNetworkBuilder
from nd_route_finder.gpx.gpx_file_finder import GpxFileFinder
from nd_route_finder.gpx.gpx_track_reader import GpxTrackReader
from nd_route_finder.gpx.gpx_track_writer import GpxTrackWriter
from nd_route_finder.routing.round_trip_generator import RoundTripGenerator
from nd_route_finder.ui.map_html_builder import MapHtmlBuilder


class RouteFinderApplication:
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

        notify(f"Loaded {len(previous_tracks)} previous GPX track(s). Downloading OSM network …")
        graph = OsmNetworkBuilder().build(request)

        notify("Filtering access restrictions, water crossings and barriers …")
        graph = ObstacleFilter().apply(graph, request)

        notify("Generating diverse route candidates and using suitable previous GPX tracks as seeds …")
        generator = RoundTripGenerator()
        candidates = generator.generate_candidates(graph, request, previous_tracks)

        accepted = self._choose_candidate_with_slope(graph, candidates, request, notify)
        generated = generator.to_track(graph, accepted)

        if generated.max_grade_percent is None:
            raise RuntimeError("Internal error: generated route has no evaluated slope.")

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
    ) -> RouteCandidate:
        enricher = ElevationEnricher()
        provider = CopernicusDemProvider()
        best: RouteCandidate | None = None

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
            best_grade = best.max_grade_percent if best is not None else None
            if grade is not None and (best_grade is None or grade < best_grade):
                best = evaluated
            if grade is not None and grade <= request.max_grade_percent:
                return evaluated

        if best is not None and best.max_grade_percent is not None:
            raise RuntimeError(
                f"No candidate satisfied the {request.max_grade_percent:.1f}% slope limit. "
                f"The best candidate was {best.max_grade_percent:.1f}% "
                f"and {best.distance_m / 1000.0:.1f} km."
            )
        raise RuntimeError(
            f"No candidate route stayed below the requested maximum slope "
            f"of {request.max_grade_percent:.1f}%."
        )
