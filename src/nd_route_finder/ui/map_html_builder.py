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

        .search-control {
            position: absolute;
            top: 12px;
            left: 12px;
            z-index: 1100;
            width: min(390px, calc(100% - 24px));
            font: 14px sans-serif;
        }

        .search-input {
            box-sizing: border-box;
            width: 100%;
            min-height: 40px;
            padding: 9px 12px;
            border: 1px solid #9d9d9d;
            border-radius: 7px;
            background: rgba(255, 255, 255, 0.97);
            color: #111;
            outline: none;
            box-shadow: 0 1px 5px rgba(0, 0, 0, 0.28);
        }

        .search-input:focus {
            border-color: #555;
        }

        .search-results {
            display: none;
            margin-top: 4px;
            overflow: hidden;
            border: 1px solid #bbb;
            border-radius: 7px;
            background: rgba(255, 255, 255, 0.98);
            box-shadow: 0 2px 7px rgba(0, 0, 0, 0.24);
        }

        .search-result {
            display: block;
            box-sizing: border-box;
            width: 100%;
            padding: 9px 11px;
            border: 0;
            border-bottom: 1px solid #e4e4e4;
            background: transparent;
            color: #111;
            text-align: left;
            cursor: pointer;
        }

        .search-result:last-child {
            border-bottom: 0;
        }

        .search-result:hover,
        .search-result:focus {
            background: #f1f1f1;
            outline: none;
        }

        .search-message {
            padding: 9px 11px;
            color: #555;
        }

        .search-attribution {
            padding: 5px 11px 7px;
            border-top: 1px solid #e4e4e4;
            color: #666;
            font-size: 11px;
        }
    </style>
</head>
<body>
    <div class="search-control" id="searchControl">
        <input
            id="placeSearch"
            class="search-input"
            type="search"
            placeholder="Search place or address…"
            autocomplete="off"
            aria-label="Search place or address"
        >
        <div id="searchResults" class="search-results" role="listbox"></div>
    </div>

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

        const map = L.map("map", { zoomControl: false });
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: "&copy; OpenStreetMap contributors"
        }).addTo(map);

        const startMarker = L.marker(startPoint, { draggable: false }).addTo(map);
        let bridge = null;
        let pendingStart = null;

        function sendStartToQt(latitude, longitude) {
            if (bridge && bridge.setStart) {
                bridge.setStart(latitude, longitude);
                pendingStart = null;
            } else {
                pendingStart = [latitude, longitude];
            }
        }

        function selectStart(latitude, longitude, zoomToPoint) {
            const point = L.latLng(latitude, longitude);
            startMarker.setLatLng(point);
            if (zoomToPoint) {
                map.setView(point, Math.max(map.getZoom(), 16));
            }
            sendStartToQt(latitude, longitude);
        }

        if (
            typeof qt !== "undefined" &&
            typeof QWebChannel !== "undefined" &&
            qt.webChannelTransport
        ) {
            new QWebChannel(qt.webChannelTransport, function(channel) {
                bridge = channel.objects.bridge;
                if (pendingStart && bridge && bridge.setStart) {
                    bridge.setStart(pendingStart[0], pendingStart[1]);
                    pendingStart = null;
                }
            });
        }

        map.on("click", function(event) {
            selectStart(event.latlng.lat, event.latlng.lng, false);
        });

        const searchControl = document.getElementById("searchControl");
        const searchInput = document.getElementById("placeSearch");
        const searchResults = document.getElementById("searchResults");
        let searchTimer = null;
        let searchAbortController = null;

        function clearSearchResults() {
            searchResults.replaceChildren();
            searchResults.style.display = "none";
        }

        function showSearchMessage(message) {
            searchResults.replaceChildren();
            const row = document.createElement("div");
            row.className = "search-message";
            row.textContent = message;
            searchResults.appendChild(row);
            searchResults.style.display = "block";
        }

        function chooseSearchResult(result) {
            const latitude = Number(result.lat);
            const longitude = Number(result.lon);
            if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
                return;
            }
            searchInput.value = String(result.display_name || "");
            clearSearchResults();
            selectStart(latitude, longitude, true);
        }

        function showSearchResults(results) {
            searchResults.replaceChildren();
            if (!Array.isArray(results) || results.length === 0) {
                showSearchMessage("No matching place found.");
                return;
            }

            results.forEach(function(result) {
                const button = document.createElement("button");
                button.type = "button";
                button.className = "search-result";
                button.setAttribute("role", "option");
                button.textContent = String(result.display_name || "Unnamed place");
                button.addEventListener("click", function() {
                    chooseSearchResult(result);
                });
                searchResults.appendChild(button);
            });

            const attribution = document.createElement("div");
            attribution.className = "search-attribution";
            attribution.textContent = "Search © OpenStreetMap contributors";
            searchResults.appendChild(attribution);
            searchResults.style.display = "block";
        }

        async function searchPlaces(query) {
            if (searchAbortController) {
                searchAbortController.abort();
            }
            searchAbortController = new AbortController();
            showSearchMessage("Searching…");

            const url =
                "https://nominatim.openstreetmap.org/search" +
                "?format=jsonv2&addressdetails=1&limit=6&q=" +
                encodeURIComponent(query);

            try {
                const response = await fetch(url, {
                    method: "GET",
                    signal: searchAbortController.signal,
                    headers: { "Accept": "application/json" }
                });
                if (!response.ok) {
                    throw new Error("HTTP " + response.status);
                }
                const results = await response.json();
                showSearchResults(results);
            } catch (error) {
                if (error && error.name === "AbortError") {
                    return;
                }
                showSearchMessage("Search is temporarily unavailable.");
            }
        }

        searchInput.addEventListener("input", function() {
            const query = searchInput.value.trim();
            if (searchTimer) {
                clearTimeout(searchTimer);
            }
            if (query.length < 3) {
                if (searchAbortController) {
                    searchAbortController.abort();
                }
                clearSearchResults();
                return;
            }
            searchTimer = setTimeout(function() {
                searchPlaces(query);
            }, 350);
        });

        searchInput.addEventListener("keydown", function(event) {
            if (event.key === "Escape") {
                clearSearchResults();
                searchInput.blur();
                return;
            }
            if (event.key === "Enter") {
                const firstResult = searchResults.querySelector(".search-result");
                if (firstResult) {
                    event.preventDefault();
                    firstResult.click();
                }
            }
        });

        document.addEventListener("click", function(event) {
            if (!searchControl.contains(event.target)) {
                clearSearchResults();
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
