"""Rank actual historic road use and soft-match distance/grade."""
import unittest
from pathlib import Path

from nd_route_finder.domain.activity_type import ActivityType
from nd_route_finder.domain.geo_point import GeoPoint
from nd_route_finder.domain.multi_waypoint_route_request import MultiWaypointRouteRequest
from nd_route_finder.domain.track import Track
from nd_route_finder.routing.route_quality import RouteQuality


class RouteQualityTests(unittest.TestCase):
    def setUp(self):
        self.request = MultiWaypointRouteRequest(
            gpx_root=Path('/tmp'), activity=ActivityType.CYCLING,
            start_latitude=47, start_longitude=15,
            target_distance_km=50, max_grade_percent=20,
            output_gpx=Path('/tmp/out.gpx'), route_mode='circular',
            route_preference='distance',
        )

    def test_history_is_spatial_not_candidate_self_overlap(self):
        old = Track('old', [[GeoPoint(47, 15), GeoPoint(47, 15.015)]])
        quality = RouteQuality([old], 47)
        repeated = [GeoPoint(47, 15.002), GeoPoint(47, 15.012)]
        distant = [GeoPoint(47.025, 15.002), GeoPoint(47.025, 15.012)]
        self.assertGreater(quality.historical_overlap(repeated), .90)
        self.assertLess(quality.historical_overlap(distant), .01)

    def test_target_matching_uses_overlap_and_slope_not_just_length(self):
        quality = RouteQuality([], 47)
        poor = quality.score(50_000, 25, .75, .95, self.request)
        better = quality.score(49_500, 19, .3, .1, self.request)
        self.assertLess(better, poor)

    def test_near_miss_still_has_finite_score(self):
        quality = RouteQuality([], 47)
        score = quality.score(54_000, 22, .45, .12, self.request)
        self.assertTrue(0 < score < 10)

    def test_loop_split_detects_outbound_retrace(self):
        finish = GeoPoint(47.02,15.01)
        points = [GeoPoint(47,15),GeoPoint(47.01,15.005),finish,
                  GeoPoint(47.01,15.005),GeoPoint(47,15)]
        self.assertGreater(RouteQuality([],47).self_retrace(points,finish),.9)


if __name__ == '__main__':
    unittest.main()
