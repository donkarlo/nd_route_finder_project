"""Regression tests for ordered direct and shortest circular routing."""
import unittest
from pathlib import Path
from unittest.mock import patch

import networkx as nx
from nd_route_finder.domain.activity_type import ActivityType
from nd_route_finder.domain.geo_point import GeoPoint
from nd_route_finder.domain.multi_waypoint_route_request import MultiWaypointRouteRequest
from nd_route_finder.routing.multi_waypoint_round_trip_generator import MultiWaypointRoundTripGenerator


class RouteModesTest(unittest.TestCase):
    def request(self, mode="direct", preference="shortest", waypoints=None):
        return MultiWaypointRouteRequest(
            gpx_root=Path("/tmp"), activity=ActivityType.CYCLING,
            start_latitude=47.0, start_longitude=15.0,
            target_distance_km=40.0, max_grade_percent=20.0,
            output_gpx=Path("/tmp/route.gpx"),
            waypoints=waypoints if waypoints is not None else (GeoPoint(47.002, 15.002),),
            route_mode=mode, route_preference=preference,
        )

    def network(self):
        g = nx.MultiDiGraph()
        for node in range(1, 5):
            g.add_node(node, x=15.0 + node * 0.001, y=47.0 + node * 0.001)
        for u,v,dist in [(1,2,1000),(1,4,100),(4,2,100),(2,1,1000)]:
            g.add_edge(u,v,length=float(dist),surface="asphalt")
        return g

    def test_direct_is_shortest_not_40km(self):
        with patch("nd_route_finder.routing.multi_waypoint_round_trip_generator.ox.distance.nearest_nodes",
                   side_effect=[1,2]):
            results=MultiWaypointRoundTripGenerator().generate_candidates(
                self.network(),self.request(),previous_tracks=[])
        self.assertEqual(len(results),1)
        self.assertEqual(results[0].nodes,[1,4,2])
        self.assertAlmostEqual(results[0].distance_m,200.0)

    def test_shortest_circle_returns_to_start(self):
        with patch("nd_route_finder.routing.multi_waypoint_round_trip_generator.ox.distance.nearest_nodes",
                   side_effect=[1,2]):
            results=MultiWaypointRoundTripGenerator().generate_candidates(
                self.network(),self.request(mode="circular"),previous_tracks=[])
        self.assertEqual(results[0].nodes,[1,4,2,1])

    def test_future_waypoint_guard_has_safe_relaxed_fallback(self):
        graph=nx.MultiDiGraph()
        for node in (1,2,3):
            graph.add_node(node,x=15+node*0.001,y=47+node*0.001)
        for u,v in [(1,3),(3,2),(2,3)]:
            graph.add_edge(u,v,length=50.0,surface="asphalt")
        with patch("nd_route_finder.routing.multi_waypoint_round_trip_generator.ox.distance.nearest_nodes",
                   side_effect=[1,2,3]):
            results=MultiWaypointRoundTripGenerator().generate_candidates(
                graph,self.request(waypoints=(GeoPoint(47.002,15.002),GeoPoint(47.003,15.003))),
                previous_tracks=[])
        self.assertEqual(results[0].nodes,[1,3,2,3])

    def test_direct_without_destination_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"destination"):
            MultiWaypointRoundTripGenerator().generate_candidates(
                self.network(),self.request(waypoints=()),previous_tracks=[])


if __name__=="__main__":
    unittest.main()
