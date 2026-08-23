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
        start = new_segments[0][0] if new_segments and new_segments[0] else [47.0707, 15.4395]
        return self._document(old_segments, new_segments, start, fit_routes=True)

    def _document(
        self,
        old_segments: list[list[list[float]]],
        new_segments: list[list[list[float]]],
        start: list[float],
        fit_routes: bool,
    ) -> str:
        return f"""<!doctype html>
<html>
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\">
<style>
html,body,#map{{height:100%;margin:0}}
.legend{{background:white;padding:8px 10px;border-radius:6px;line-height:1.5}}
.hint{{background:white;padding:7px 10px;border-radius:6px;font:14px sans-serif}}
</style>
</head>
<body>
<div id=\"map\"></div>
<script src=\"qrc:///qtwebchannel/qwebchannel.js\"></script>
<script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"></script>
<script>
const start = {json.dumps(start)};
const oldSegments = {json.dumps(old_segments, separators=(",", ":"))};
const newSegments = {json.dumps(new_segments, separators=(",", ":"))};
const map = L.map('map');
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
}}).addTo(map);

const routeLayers = [];
oldSegments.forEach(function(segment) {{
  const layer = L.polyline(segment, {{color:'#64748b', weight:3, opacity:0.55}}).addTo(map);
  routeLayers.push(layer);
}});
newSegments.forEach(function(segment) {{
  const outline = L.polyline(segment, {{color:'#ffffff', weight:10, opacity:0.92}}).addTo(map);
  const layer = L.polyline(segment, {{color:'#dc2626', weight:6, opacity:1.0}}).addTo(map);
  routeLayers.push(outline);
  routeLayers.push(layer);
}});

const marker = L.circleMarker(start, {{radius:7, color:'#15803d', fillColor:'#22c55e', fillOpacity:1}})
  .addTo(map).bindTooltip('Start');
if ({str(fit_routes).lower()} && routeLayers.length) {{
  const bounds = L.featureGroup(routeLayers).getBounds();
  if (bounds.isValid()) {{
    map.fitBounds(bounds.pad(0.08));
  }} else {{
    map.setView(start, 13);
  }}
}} else {{
  map.setView(start, 13);
}}

let bridge = null;
if (typeof qt !== 'undefined') {{
  new QWebChannel(qt.webChannelTransport, function(channel) {{
    bridge = channel.objects.bridge;
  }});
}}
map.on('click', function(event) {{
  marker.setLatLng(event.latlng);
  if (bridge) {{
    bridge.setStart(event.latlng.lat, event.latlng.lng);
  }}
}});

const hint = L.control({{position:'topleft'}});
hint.onAdd = function() {{
  const div = L.DomUtil.create('div', 'hint');
  div.innerHTML = '<b>Click the map to choose the start point</b>';
  return div;
}};
hint.addTo(map);

const legend = L.control({{position:'topright'}});
legend.onAdd = function() {{
  const div = L.DomUtil.create('div', 'legend');
  div.innerHTML = '<b>Routes</b><br><span style=\"color:#64748b\">━━</span> Previous GPX<br><span style=\"color:#dc2626\">━━</span> Generated';
  return div;
}};
legend.addTo(map);
</script>
</body>
</html>"""
