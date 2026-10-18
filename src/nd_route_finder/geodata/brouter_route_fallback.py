"""Route candidates from BRouter when graph routing cannot connect selected stops."""
from __future__ import annotations

from collections.abc import Callable
from math import asin, atan2, cos, degrees, radians, sin
from urllib.parse import urlencode

import gpxpy
import requests

from nd_route_finder.analysis.track_analyzer import TrackAnalyzer
from nd_route_finder.domain.geo_point import GeoPoint
from nd_route_finder.domain.route_request import RouteRequest
from nd_route_finder.domain.track import Track
from nd_route_finder.geodata.elevation_enricher import ElevationEnricher
from nd_route_finder.routing.route_quality import RouteQuality


class BrouterRouteFallback:
    _URL = "https://brouter.de/brouter"
    _USER_AGENT = "nd_route_finder/1.0 (personal route planner)"

    def generate(
        self,
        request: RouteRequest,
        notify: Callable[[str], None] | None = None,
        previous_tracks: list[Track] | None = None,
    ) -> Track:
        stops = tuple(getattr(request, "waypoints", ()))
        message = notify or (lambda _: None)
        mode = getattr(request, "route_mode", "circular")
        if mode == "direct" and not stops:
            raise ValueError("Direct BRouter backup requires a destination.")
        start = GeoPoint(request.start_latitude, request.start_longitude)
        positions = [start, *stops]
        quality = RouteQuality(previous_tracks or [], start.latitude)
        analyzer = TrackAnalyzer()
        pref = getattr(request, "route_preference", "auto")
        shortest = pref == 'shortest' or (pref == 'auto' and not previous_tracks and bool(stops))
        activity = getattr(request.activity, "value", str(request.activity))
        profiles = ("trekking", "fastbike") if activity == "cycling" else ("hiking-mountain",)

        # BRouter may return an out-and-back 'circle' when given start -> stop ->
        # start. Add return-leg detours on both sides of the chord so genuinely
        # circular alternatives can be compared for repeat distance and history.
        plans = [("base", positions + [start] if mode == 'circular' else positions)] if stops else []
        if not stops and mode == "circular":
            # Without user-supplied waypoints, sample multiple geographical
            # directions. Returning no GPX simply because the graph is fragmented
            # would defeat the user's 'closest feasible suggestion' requirement.
            radius = max(650.0, min(16_000.0, request.target_distance_m / 5.2))
            for azimuth in (20, 85, 145, 210, 280):
                via = [self._destination(start, radius, azimuth + offset)
                       for offset in (0, 120, 240)]
                plans.append((f"automatic_{azimuth}", [start, *via, start]))
        if stops and mode == "circular" and not shortest:
            for side in (-1.0, 1.0):
                for lateral_m in (1500.0, 2700.0, 4200.0):
                    via = self._return_detours(start, stops[-1], side * lateral_m)
                    plans.append((f"return_{side:+.0f}_{int(lateral_m)}", positions + via + [start]))
            # A corridor displaced east/west (rather than perpendicular to
            # start->destination) explores valleys that the perpendicular
            # detours miss, especially with mountainous terrain.
            for east_m in (-2800.0, 2200.0, 3000.0, 3900.0):
                via = self._east_west_return(start, stops[-1], east_m)
                plans.append((f"east_west_{int(east_m)}", positions + via + [start]))

        scored: list[tuple[float, Track]] = []
        failures: list[str] = []
        for plan_name, route_points in plans:
            lonlats = "|".join(f"{pt.longitude:.7f},{pt.latitude:.7f}" for pt in route_points)
            for profile in profiles:
                message(f"Evaluating BRouter {plan_name} ({profile}) …")
                query = urlencode({"lonlats": lonlats, "profile": profile,
                                   "alternativeidx": 0, "format": "gpx",
                                   "trackname": "ND_circular_candidate"})
                try:
                    response = requests.get(
                        f"{self._URL}?{query}", timeout=50,
                        headers={"User-Agent": self._USER_AGENT, "Accept": "application/gpx+xml"},
                    )
                    response.raise_for_status()
                    parsed = gpxpy.parse(response.text)
                    segments = [[GeoPoint(float(pt.latitude), float(pt.longitude),
                                    float(pt.elevation) if pt.elevation is not None else None)
                        for pt in segment.points]
                        for trk in parsed.tracks for segment in trk.segments
                        if len(segment.points) >= 2]
                    if not segments:
                        raise RuntimeError("BRouter returned no usable GPX track.")
                    points = [pt for segment in segments for pt in segment]
                    self._validate_stops(points, route_points, analyzer)
                    if any(pt.elevation is None for pt in points):
                        raise RuntimeError("BRouter GPX is missing elevations.")
                    track = analyzer.analyze(Track(name="generated_brouter_backup", segments=segments))
                    if mode == 'circular' and analyzer._distance(points[0], points[-1]) > 150:
                        raise RuntimeError("Candidate does not close the loop.")
                    distances = [analyzer._distance(a,b) for a,b in zip(points,points[1:])]
                    heights = [float(p.elevation) for p in points]
                    enricher = ElevationEnricher()
                    track.max_grade_percent = enricher._calculate_windowed_max_grade(
                        enricher._median_smooth(heights, [False] * len(distances)),
                        distances, [False] * len(distances))
                    history_overlap = quality.historical_overlap(points)
                    split = stops[-1] if stops else route_points[min(2, len(route_points) - 2)]
                    self_retrace = quality.self_retrace(points, split) if mode == 'circular' else 0.0
                    score = quality.score(track.distance_m, track.max_grade_percent,
                                          history_overlap, self_retrace, request)
                    track.metadata.update({
                        "route_mode": mode, "routing_backend": "BRouter",
                        "obstacle_verification": "BRouter routing only; independent Overpass barriers unavailable",
                        "elevation_source": "BRouter GPX",
                        "history_overlap": f"{history_overlap:.4f}",
                        "self_retrace": f"{self_retrace:.4f}",
                        "selection_score": f"{score:.5f}",
                        "candidate_variant": plan_name,
                    })
                    scored.append((score, track))
                    message(f"Candidate: {track.distance_m/1000:.1f} km, "
                            f"grade {track.max_grade_percent:.1f}%, "
                            f"previous-route overlap {history_overlap:.0%}, "
                            f"return retrace {self_retrace:.0%} …")
                except (requests.RequestException, RuntimeError, ValueError, TypeError, IndexError) as exc:
                    failures.append(f"{plan_name}/{profile}: {type(exc).__name__}")
                    message(f"Candidate unavailable ({plan_name}/{profile}); trying alternatives …")
        if not scored:
            raise RuntimeError("No legal routed GPX was returned by BRouter. "
                               "Try another time or adjust the intermediate point.")
        best = min(scored, key=lambda pair: pair[0])[1]
        best.metadata["candidate_count"] = str(len(scored))
        best.metadata["constraint_fallback"] = (
            "true" if abs(best.distance_m - request.target_distance_m) > .10 * request.target_distance_m
            or best.max_grade_percent > request.max_grade_percent else "false"
        )
        message(f"Best of {len(scored)} BRouter alternatives: "
                f"{best.distance_m/1000:.2f} km, "
                f"estimated grade {best.max_grade_percent:.1f}%, "
                f"previous-route overlap {float(best.metadata['history_overlap']):.0%}.")
        return best

    @staticmethod
    def _return_detours(start: GeoPoint, finish: GeoPoint, lateral_m: float) -> list[GeoPoint]:
        dx = (finish.longitude - start.longitude) * (111_195 * cos(radians(start.latitude)))
        dy = (finish.latitude - start.latitude) * 111_195
        length = max(1, (dx*dx + dy*dy) ** .5)
        # Rotate the start->finish vector clockwise to obtain a return corridor.
        px, py = dy / length * lateral_m, -dx / length * lateral_m
        return [GeoPoint(start.latitude + dy * frac / 111_195 + py / 111_195,
                         start.longitude + (dx * frac + px) / (111_195 * cos(radians(start.latitude))))
                for frac in (0.72, 0.38)]

    @staticmethod
    def _destination(start: GeoPoint, metres: float, bearing_degrees: float) -> GeoPoint:
        angular = metres / 6_371_008.8
        phi, lam, bearing = radians(start.latitude), radians(start.longitude), radians(bearing_degrees)
        lat = asin(sin(phi) * cos(angular) + cos(phi) * sin(angular) * cos(bearing))
        lon = lam + atan2(sin(bearing) * sin(angular) * cos(phi),
                          cos(angular) - sin(phi) * sin(lat))
        return GeoPoint(degrees(lat), degrees(lon))

    @staticmethod
    def _east_west_return(start: GeoPoint, finish: GeoPoint, east_m: float) -> list[GeoPoint]:
        mx = 111_195 * cos(radians(start.latitude))
        return [GeoPoint(start.latitude + fraction * (finish.latitude - start.latitude),
                         start.longitude + fraction * (finish.longitude - start.longitude)
                         + east_m * taper / mx)
                for fraction, taper in ((0.77, 1.0), (0.39, 0.76))]

    @staticmethod
    def _validate_stops(points: list[GeoPoint], stops: list[GeoPoint], analyzer: TrackAnalyzer) -> None:
        current = 0
        for stop in stops:
            nearest = min(range(current, len(points)),
                          key=lambda i: analyzer._distance(points[i], stop))
            gap = analyzer._distance(points[nearest], stop)
            if gap > 500:
                raise RuntimeError(f"BRouter missed an ordered waypoint by {gap:.0f} metres.")
            current = nearest
