"""Ensure BRouter backup is validated, slope-checked and exportable."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from nd_route_finder.application.multi_waypoint_route_finder_application import MultiWaypointRouteFinderApplication
from nd_route_finder.domain.activity_type import ActivityType
from nd_route_finder.domain.geo_point import GeoPoint
from nd_route_finder.domain.multi_waypoint_route_request import MultiWaypointRouteRequest
from nd_route_finder.domain.track import Track
from nd_route_finder.geodata.brouter_route_fallback import BrouterRouteFallback
from nd_route_finder.geodata.overpass_unavailable_error import OverpassUnavailableError
from nd_route_finder.gpx.gpx_track_reader import GpxTrackReader


class BrouterFallbackTests(unittest.TestCase):
    def request(self, root):
        return MultiWaypointRouteRequest(
            gpx_root=root, activity=ActivityType.CYCLING,
            start_latitude=47.077531, start_longitude=15.4776239,
            target_distance_km=40, max_grade_percent=20,
            output_gpx=root/'route.gpx',
            waypoints=(GeoPoint(47.175987, 15.362206),),
            route_mode='direct', route_preference='shortest',
        )

    def test_valid_brouter_response_and_slope(self):
        points = [(47.077531, 15.4776239, 380),
                  (47.100000, 15.4500000, 400),
                  (47.130000, 15.4200000, 430),
                  (47.175987, 15.3622060, 449)]
        xml = '<?xml version="1.0"?><gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
        for lat, lon, z in points:
            xml += f'<trkpt lat="{lat}" lon="{lon}"><ele>{z}</ele></trkpt>'
        xml += '</trkseg></trk></gpx>'
        response = SimpleNamespace(text=xml, raise_for_status=lambda: None)
        with tempfile.TemporaryDirectory() as d:
            req = self.request(Path(d))
            with patch('nd_route_finder.geodata.brouter_route_fallback.requests.get', return_value=response) as fetch:
                track = BrouterRouteFallback().generate(req)
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(track.metadata['routing_backend'], 'BRouter')
            self.assertTrue(0 <= track.max_grade_percent < 20)
            self.assertEqual(len(track.segments[0]), 4)

    def test_disconnected_graph_uses_backup_instead_of_route_failed(self):
        with tempfile.TemporaryDirectory() as d:
            req = self.request(Path(d))
            track = Track('backup', [[GeoPoint(47.077531,15.4776239,380),
                GeoPoint(47.175987,15.362206,449)]], distance_m=21000,
                max_grade_percent=11.0, metadata={'routing_backend':'BRouter',
                    'history_overlap':'0.2', 'constraint_fallback':'true'})
            with (
                patch('nd_route_finder.application.multi_waypoint_route_finder_application.MultiWaypointOsmNetworkBuilder.build',
                      return_value=object()),
                patch('nd_route_finder.application.multi_waypoint_route_finder_application.ObstacleFilter.apply',
                      return_value=object()),
                patch('nd_route_finder.application.multi_waypoint_route_finder_application.MultiWaypointRoundTripGenerator.generate_candidates',
                      side_effect=RuntimeError('No legal cycling/walking path connects the start and selected points')),
                patch('nd_route_finder.application.multi_waypoint_route_finder_application.BrouterRouteFallback.generate',
                      return_value=track),
                patch('nd_route_finder.application.multi_waypoint_route_finder_application.MapHtmlBuilder.build_routes',
                      return_value='<html>route</html>'),
            ):
                _, result, output, _ = MultiWaypointRouteFinderApplication().run(req)
            self.assertTrue(output.is_file())
            self.assertEqual(result.metadata['routing_backend'], 'BRouter')

    def test_application_uses_backup_after_overpass_failure(self):
        with tempfile.TemporaryDirectory() as d:
            req = self.request(Path(d))
            track = Track('test_backup', [[GeoPoint(47.077531,15.4776239,380),
                GeoPoint(47.175987,15.362206,449)]], distance_m=19000,
                max_grade_percent=9.0, metadata={'routing_backend':'BRouter'})
            with (
                patch('nd_route_finder.application.multi_waypoint_route_finder_application.MultiWaypointOsmNetworkBuilder.build',
                      side_effect=OverpassUnavailableError('no servers')),
                patch('nd_route_finder.application.multi_waypoint_route_finder_application.BrouterRouteFallback.generate',
                      return_value=track),
                patch('nd_route_finder.application.multi_waypoint_route_finder_application.MapHtmlBuilder.build_routes',
                      return_value='<html>route</html>'),
            ):
                previous, generated, output, html = MultiWaypointRouteFinderApplication().run(req)
            self.assertFalse(previous)
            self.assertEqual(generated.metadata['routing_backend'], 'BRouter')
            self.assertEqual(generated.metadata['constraint_fallback'], 'true')
            self.assertTrue(output.exists())
            self.assertEqual(len(GpxTrackReader().read(output).segments[0]), 2)
            self.assertIn('route', html)


if __name__ == '__main__':
    unittest.main()
