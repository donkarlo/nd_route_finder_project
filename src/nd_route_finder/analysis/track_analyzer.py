import math

from nd_route_finder.domain.geo_point import GeoPoint
from nd_route_finder.domain.track import Track


class TrackAnalyzer:
    _EARTH_RADIUS_M = 6_371_008.8

    def analyze(self, track: Track) -> Track:
        distance_m = 0.0
        max_grade: float | None = None

        for segment in track.segments:
            for first, second in zip(segment, segment[1:]):
                horizontal = self._distance(first, second)
                distance_m += horizontal

                if (
                    horizontal >= 5.0
                    and first.elevation is not None
                    and second.elevation is not None
                ):
                    grade = abs(second.elevation - first.elevation) / horizontal * 100.0
                    max_grade = grade if max_grade is None else max(max_grade, grade)

        track.distance_m = distance_m
        track.max_grade_percent = max_grade
        return track

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
