import json

from nd_route_finder.domain.geo_point import GeoPoint
from nd_route_finder.domain.track import Track
from nd_route_finder.ui.map_html_builder import MapHtmlBuilder


class MultiWaypointMapHtmlBuilder(MapHtmlBuilder):
    def __init__(self) -> None:
        super().__init__()
        self._waypoints: tuple[GeoPoint, ...] = ()

    def set_waypoints(self, waypoints: tuple[GeoPoint, ...]) -> None:
        self._waypoints = tuple(waypoints)

    def build_selector(self, latitude: float, longitude: float) -> str:
        return self._enhance(super().build_selector(latitude, longitude))

    def build_routes(self, previous_tracks: list[Track], generated: Track) -> str:
        return self._enhance(super().build_routes(previous_tracks, generated))

    def _enhance(self, html: str) -> str:
        waypoints_json = json.dumps(
            [[point.latitude, point.longitude] for point in self._waypoints],
            separators=(",", ":"),
        )
        script = r"""
<script>
(function() {
    const initialWaypoints = __WAYPOINTS__;
    const waypointMarkers = [];
    let pendingWaypoint = null;
    window.ndSelectionMode = "start";

    function markerForWaypoint(point, index) {
        const marker = L.circleMarker(point, {
            radius: 10,
            color: "#172554",
            weight: 2,
            fillColor: "#60a5fa",
            fillOpacity: 0.96
        }).addTo(map);
        marker.bindTooltip(String(index + 1), {
            permanent: true,
            direction: "center",
            className: "nd-waypoint-index"
        });
        return marker;
    }

    window.ndSyncWaypoints = function(points) {
        waypointMarkers.forEach(function(marker) {
            map.removeLayer(marker);
        });
        waypointMarkers.length = 0;
        (Array.isArray(points) ? points : []).forEach(function(point, index) {
            if (!Array.isArray(point) || point.length < 2) {
                return;
            }
            waypointMarkers.push(markerForWaypoint(point, index));
        });
    };

    function currentSearchLabel() {
        if (typeof searchInput === "undefined" || !searchInput) {
            return "";
        }
        return String(searchInput.value || "");
    }

    function sendWaypointToQt(latitude, longitude) {
        const label = currentSearchLabel();
        if (bridge && bridge.addPoint) {
            bridge.addPoint(latitude, longitude, label);
            pendingWaypoint = null;
        } else {
            pendingWaypoint = [latitude, longitude, label];
        }
    }

    window.ndSetSelectionMode = function(mode) {
        window.ndSelectionMode = mode === "waypoint" ? "waypoint" : "start";
        if (typeof searchInput !== "undefined" && searchInput) {
            searchInput.placeholder = window.ndSelectionMode === "waypoint"
                ? "Search and add intermediate point…"
                : "Search place or address for start…";
        }
    };

    const originalSelectStart = selectStart;
    selectStart = function(latitude, longitude, zoomToPoint) {
        if (window.ndSelectionMode !== "waypoint") {
            originalSelectStart(latitude, longitude, zoomToPoint);
            return;
        }
        const point = L.latLng(latitude, longitude);
        if (zoomToPoint) {
            map.setView(point, Math.max(map.getZoom(), 16));
        }
        sendWaypointToQt(latitude, longitude);
    };

    const bridgeFlushTimer = window.setInterval(function() {
        if (!pendingWaypoint || !bridge || !bridge.addPoint) {
            return;
        }
        bridge.addPoint(pendingWaypoint[0], pendingWaypoint[1], pendingWaypoint[2]);
        pendingWaypoint = null;
    }, 120);
    window.setTimeout(function() {
        window.clearInterval(bridgeFlushTimer);
    }, 8000);

    window.ndSyncWaypoints(initialWaypoints);
    window.ndSetSelectionMode("start");
})();
</script>
""".replace("__WAYPOINTS__", waypoints_json)
        return html.replace("</body>", script + "\n</body>", 1)
