"""Rank viable routes against length, grade, and *actual* past GPX geometry."""
from __future__ import annotations

from math import cos, radians

import numpy as np
from scipy.spatial import cKDTree

from nd_route_finder.domain.geo_point import GeoPoint
from nd_route_finder.domain.route_request import RouteRequest
from nd_route_finder.domain.track import Track


class RouteQuality:
    """Prepared spatial index for historical GPX tracks, constructed once per search."""

    def __init__(self, previous_tracks: list[Track], latitude: float) -> None:
        self._meters_x = 111_195 * cos(radians(latitude))
        self._meters_y = 111_195
        sampled: list[tuple[float, float]] = []
        for track in previous_tracks:
            for segment in track.segments:
                sampled.extend(self._resample(segment))
        self._history_tree = cKDTree(np.asarray(sampled)) if sampled else None

    def _xy(self, p: GeoPoint) -> tuple[float, float]:
        return (p.longitude * self._meters_x, p.latitude * self._meters_y)

    def _resample(self, points: list[GeoPoint], step: float = 38.0) -> list[tuple[float, float]]:
        if not points:
            return []
        result: list[tuple[float, float]] = [self._xy(points[0])]
        for a, b in zip(points, points[1:]):
            x0, y0 = self._xy(a)
            x1, y1 = self._xy(b)
            length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
            count = max(1, int(length / step + 0.999))
            result.extend((x0 + (x1 - x0) * i / count,
                           y0 + (y1 - y0) * i / count) for i in range(1, count + 1))
        return result

    def historical_overlap(self, points: list[GeoPoint], tolerance_m: float = 38) -> float:
        if self._history_tree is None or len(points) < 2:
            return 0.0
        coords = self._resample(points)
        if len(coords) <= 1:
            return 0.0
        distances, _ = self._history_tree.query(np.asarray(coords), k=1)
        return float(np.mean(distances <= tolerance_m))

    def self_retrace(self, points: list[GeoPoint], split_point: GeoPoint) -> float:
        """Count how often the return leg follows the outbound leg (~40m)."""
        if len(points) < 3:
            return 0.0
        target = self._xy(split_point)
        index = min(range(len(points)), key=lambda i: (
            (self._xy(points[i])[0] - target[0]) ** 2 +
            (self._xy(points[i])[1] - target[1]) ** 2
        ))
        if index < 2 or index >= len(points) - 2:
            return 0.0
        outbound = np.asarray(self._resample(points[:index + 1]))
        inbound = np.asarray(self._resample(points[index:]))
        if len(outbound) == 0 or len(inbound) == 0:
            return 0.0
        distances, _ = cKDTree(outbound).query(inbound, k=1)
        return float(np.mean(distances <= 40.0))

    @staticmethod
    def score(
        distance_m: float,
        grade: float,
        historical_overlap: float,
        self_retrace: float,
        request: RouteRequest,
    ) -> float:
        """Soft targets: prefer matching both constraints but never reject a near miss."""
        target = max(1.0, request.target_distance_m)
        distance_error = abs(distance_m - target) / target
        grade_excess = max(0.0, grade - request.max_grade_percent) / max(1.0, request.max_grade_percent)
        preference = getattr(request, 'route_preference', 'distance')
        if preference == 'shortest':
            return distance_m / 1000 + 20.0 * grade_excess + 3.0 * historical_overlap
        # Distance near-misses, slope excess, history, self-retrace: all soft.
        return (3.0 * distance_error + 3.5 * grade_excess +
                1.7 * historical_overlap + 0.9 * self_retrace)
