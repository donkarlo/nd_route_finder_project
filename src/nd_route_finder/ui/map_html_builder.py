import json

from nd_route_finder.domain.track import Track


class MapHtmlBuilder:
    def build_selector(self, latitude: float, longitude: float) -> str:
        return self._document(
            old_segments=[],
            new_segments=[],
            start=[latitude, longitude],
            fit_routes=False,
        )

    def build_routes(self, previous_tracks: list[Track], generated: Track) -> str:
        old_segments = [
            [[point.latitude, point.longitude] for point in segment]
            for track in previous_tracks
            for segment in track.segments
            if len(segment) >= 2
        ]
        new_segments = [
            [[point.latitude, point.longitude] for point in segment]
            for segment in generated.segments
            if len(segment) >= 2
        ]
        start = (
            new_segments[0][0]
            if new_segments and new_segments[0]
            else [47.0707, 15.4395]
        )
        return self._document(old_segments, new_segments, start, fit_routes=True)

    def _document(
        self,
        old_segments: list[list[list[float]]],
        new_segments: list[list[list[float]]],
        start: list[float],
        fit_routes: bool,
    ) -> str:
        old_segments_json = json.dumps(old_segments, separators=(",", ":"))
        new_segments_json = json.dumps(new_segments, separators=(",", ":"))
        start_json = json.dumps(start, separators=(",", ":"))
        fit_routes_json = "true" if fit_routes else "false"

        template = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ND Route Finder</title>
    <link
        rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        crossorigin=""
    >
    <style>
        html, body, #map {
            width: 100%;
            height: 100%;
            margin: 0;
            padding: 0;
        }

        .route-legend {
            position: absolute;
            top: 12px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 1000;
            display: flex;
            gap: 18px;
            align-items: center;
            padding: 8px 12px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.94);
            box-shadow: 0 1px 5px rgba(0, 0, 0, 0.28);
            font: 13px sans-serif;
        }

        .legend-item {
            display: flex;
            align-items: center;
            gap: 6px;
            white-space: nowrap;
        }

        .legend-line {
            width: 28px;
            height: 5px;
            border-radius: 3px;
        }

        .legend-old {
            background: #238b45;
        }

        .legend-new {
            background: #d62728;
        }
    </style>
</head>
<body>
    <div id="routeLegend" class="route-legend">
        <div class="legend-item">
            <span class="legend-line legend-old"></span>
            <span>Previous routes</span>
        </div>
        <div class="legend-item">
            <span class="legend-line legend-new"></span>
            <span>Generated route</span>
        </div>
    </div>
    <div id="map"></div>

    <script
        src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        crossorigin=""
    ></script>
    <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
    <script>
        const oldSegments = __OLD_SEGMENTS__;
        const newSegments = __NEW_SEGMENTS__;
        const startPoint = __START_POINT__;
        const fitRoutes = __FIT_ROUTES__;

        const map = L.map("map");
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: "&copy; OpenStreetMap contributors"
        }).addTo(map);

        const startMarker = L.marker(startPoint, { draggable: false }).addTo(map);
        let bridge = null;

        if (
            typeof qt !== "undefined" &&
            typeof QWebChannel !== "undefined" &&
            qt.webChannelTransport
        ) {
            new QWebChannel(qt.webChannelTransport, function(channel) {
                bridge = channel.objects.bridge;
            });
        }

        map.on("click", function(event) {
            startMarker.setLatLng(event.latlng);
            if (bridge && bridge.setStart) {
                bridge.setStart(event.latlng.lat, event.latlng.lng);
            }
        });

        const routeBounds = [];

        oldSegments.forEach(function(segment) {
            if (segment.length < 2) {
                return;
            }
            L.polyline(segment, {
                color: "#238b45",
                weight: 5,
                opacity: 0.85
            }).addTo(map);
            segment.forEach(function(point) {
                routeBounds.push(point);
            });
        });

        newSegments.forEach(function(segment) {
            if (segment.length < 2) {
                return;
            }
            L.polyline(segment, {
                color: "#ffffff",
                weight: 10,
                opacity: 0.95
            }).addTo(map);
            L.polyline(segment, {
                color: "#d62728",
                weight: 6,
                opacity: 1.0
            }).addTo(map);
            segment.forEach(function(point) {
                routeBounds.push(point);
            });
        });

        if (fitRoutes && routeBounds.length > 0) {
            map.fitBounds(routeBounds, { padding: [36, 36] });
        } else {
            map.setView(startPoint, 14);
        }

        if (oldSegments.length === 0 && newSegments.length === 0) {
            document.getElementById("routeLegend").style.display = "none";
        }
    </script>
</body>
</html>
"""
        return (
            template
            .replace("__OLD_SEGMENTS__", old_segments_json)
            .replace("__NEW_SEGMENTS__", new_segments_json)
            .replace("__START_POINT__", start_json)
            .replace("__FIT_ROUTES__", fit_routes_json)
        )
