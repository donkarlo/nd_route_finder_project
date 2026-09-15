#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
HTML_SRC="$ROOT/route_finder_v4.html"
HTML_DST="$ROOT/app/src/main/assets/route_finder.html"
ROUTE_ENGINE="$ROOT/app/src/main/java/com/ndroutefinder/mobile/RouteEngine.java"
MAIN_ACTIVITY="$ROOT/app/src/main/java/com/ndroutefinder/mobile/MainActivity.java"
BUILD_GRADLE="$ROOT/app/build.gradle.kts"
STAMP="20260915"

if [[ ! -f "$HTML_SRC" ]]; then
  echo "Missing $HTML_SRC" >&2
  exit 2
fi

cp -n "$HTML_DST" "$HTML_DST.pre_navigation_v4_${STAMP}.bak" || true
cp -n "$ROUTE_ENGINE" "$ROUTE_ENGINE.pre_navigation_v4_${STAMP}.bak" || true
cp -n "$MAIN_ACTIVITY" "$MAIN_ACTIVITY.pre_navigation_v4_${STAMP}.bak" || true
cp -n "$BUILD_GRADLE" "$BUILD_GRADLE.pre_navigation_v4_${STAMP}.bak" || true

cp "$HTML_SRC" "$HTML_DST"

echo "Installed mobile v4 UI: direction arrows, circular reverse, auto-reroute, local-first search UI."

python3 - "$ROUTE_ENGINE" <<'PY'
from pathlib import Path
import re, sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

if "appendNominatimResults(" not in text:
    replacement = r'''    public void searchPlaces(String query, double originLat, double originLon, SearchCallback callback) {
        executor.execute(() -> {
            try {
                String clean = query == null ? "" : query.trim();
                if (clean.length() < 2) throw new IllegalArgumentException("Type at least two characters.");

                boolean haveOrigin = validCoordinate(originLat, originLon);
                List<SearchItem> items = new ArrayList<>();

                if (haveOrigin) {
                    // Local-first: ask Nominatim for matches inside a tight box around
                    // the current/start position before considering farther results.
                    appendNominatimResults(clean, originLat, originLon,
                            0.34, 0.25, true, 35, items);

                    // Keep recall for sparse/ambiguous searches. The final ordering is
                    // still strictly by distance from the selected GPS/start position.
                    if (items.size() < 12) {
                        appendNominatimResults(clean, originLat, originLon,
                                1.25, 0.90, false, 35, items);
                    }

                    items.sort(Comparator.comparingDouble(a -> a.distanceM));
                } else {
                    appendNominatimResults(clean, Double.NaN, Double.NaN,
                            0.0, 0.0, false, 25, items);
                }

                JSONArray out = new JSONArray();
                int count = Math.min(items.size(), 20);
                for (int i = 0; i < count; i++) {
                    SearchItem item = items.get(i);
                    JSONObject compact = new JSONObject();
                    compact.put("lat", item.lat);
                    compact.put("lon", item.lon);
                    compact.put("label", item.label);
                    if (Double.isFinite(item.distanceM)) compact.put("distanceM", item.distanceM);
                    out.put(compact);
                }
                callback.onSuccess(out);
            } catch (Exception e) {
                callback.onFailure(readable(e));
            }
        });
    }

    private void appendNominatimResults(String clean,
                                        double originLat,
                                        double originLon,
                                        double lonSpan,
                                        double latSpan,
                                        boolean bounded,
                                        int limit,
                                        List<SearchItem> items) throws Exception {
        StringBuilder url = new StringBuilder(NOMINATIM_URL)
                .append("?format=jsonv2&addressdetails=0&limit=")
                .append(limit)
                .append("&q=")
                .append(URLEncoder.encode(clean, "UTF-8"));

        boolean haveOrigin = validCoordinate(originLat, originLon);
        if (haveOrigin && lonSpan > 0.0 && latSpan > 0.0) {
            url.append("&viewbox=")
                    .append(String.format(Locale.US, "%.6f,%.6f,%.6f,%.6f",
                            originLon - lonSpan, originLat + latSpan,
                            originLon + lonSpan, originLat - latSpan))
                    .append("&bounded=")
                    .append(bounded ? "1" : "0");
        }

        String body = httpGet(url.toString(), "application/json");
        JSONArray raw = new JSONArray(body);
        for (int i = 0; i < raw.length(); i++) {
            JSONObject item = raw.optJSONObject(i);
            if (item == null) continue;
            try {
                double lat = Double.parseDouble(item.getString("lat"));
                double lon = Double.parseDouble(item.getString("lon"));
                if (!validCoordinate(lat, lon)) continue;
                String label = item.optString("display_name", "Result");
                double distance = haveOrigin
                        ? distanceMeters(originLat, originLon, lat, lon)
                        : Double.NaN;

                boolean duplicate = false;
                for (SearchItem existing : items) {
                    if (Math.abs(existing.lat - lat) < 1e-7
                            && Math.abs(existing.lon - lon) < 1e-7) {
                        duplicate = true;
                        break;
                    }
                    if (existing.label.equalsIgnoreCase(label)
                            && Double.isFinite(existing.distanceM)
                            && Double.isFinite(distance)
                            && Math.abs(existing.distanceM - distance) < 5.0) {
                        duplicate = true;
                        break;
                    }
                }
                if (!duplicate) items.add(new SearchItem(lat, lon, label, distance));
            } catch (RuntimeException ignored) {
            }
        }
    }

    private static final class SearchItem'''

    pattern = re.compile(
        r'    public void searchPlaces\(String query, double originLat, double originLon, SearchCallback callback\) \{.*?\n    \}\n\n    private static final class SearchItem',
        re.S,
    )
    text2, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise SystemExit("Could not patch RouteEngine.searchPlaces; source did not match expected v3 structure.")
    text = text2
    print("Patched RouteEngine: local bounded search first, then broader fallback, final distance sort.")
else:
    print("RouteEngine local-first search patch already present.")

text = text.replace('nd_route_finder_mobile/3.0 (personal route planner)',
                    'nd_route_finder_mobile/4.0 (personal route planner)')
path.write_text(text, encoding="utf-8")
PY

python3 - "$MAIN_ACTIVITY" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

if "setCurrentRouteFromPoints(" not in text:
    needle = '''        @JavascriptInterface
        public void sendRouteToGarminConnect() {
            runOnUiThread(MainActivity.this::sendCurrentRouteToGarminConnect);
        }
'''
    addition = needle + '''
        @JavascriptInterface
        public void setCurrentRouteFromPoints(String name, String pointsJson) {
            try {
                JSONArray arr = new JSONArray(pointsJson == null ? "[]" : pointsJson);
                java.util.List<GpxCodec.Point> points = new java.util.ArrayList<>();
                for (int i = 0; i < arr.length(); i++) {
                    JSONArray p = arr.optJSONArray(i);
                    if (p == null || p.length() < 2) continue;
                    double lat = p.optDouble(0, Double.NaN);
                    double lon = p.optDouble(1, Double.NaN);
                    if (!validCoordinate(lat, lon)) continue;
                    Double elevation = null;
                    if (p.length() > 2 && !p.isNull(2)) {
                        double ele = p.optDouble(2, Double.NaN);
                        if (Double.isFinite(ele)) elevation = ele;
                    }
                    points.add(new GpxCodec.Point(lat, lon, elevation));
                }
                if (points.size() < 2) return;
                String routeName = (name == null || name.trim().isEmpty()) ? "ND route" : name.trim();
                String gpx = GpxCodec.buildTrack(routeName, points);
                GpxCodec.Track track = GpxCodec.parse(gpx, routeName);
                currentTrack = track;
                cacheCurrentRoute(track);
            } catch (Exception e) {
                callJs("window.ndGarminStatus && window.ndGarminStatus("
                        + JSONObject.quote("Could not update reversed route: " + message(e)) + ");");
            }
        }
'''
    if needle not in text:
        raise SystemExit("Could not patch MainActivity NativeBridge; sendRouteToGarminConnect block not found.")
    text = text.replace(needle, addition, 1)
    path.write_text(text, encoding="utf-8")
    print("Patched MainActivity: reversed GPX order is also synced to native currentTrack.")
else:
    print("MainActivity reverse-route bridge already present.")
PY

python3 - "$BUILD_GRADLE" <<'PY'
from pathlib import Path
import re, sys
p=Path(sys.argv[1]); s=p.read_text(encoding='utf-8')
s=re.sub(r'versionCode\s*=\s*\d+', 'versionCode = 22', s, count=1)
s=re.sub(r'versionName\s*=\s*"[^"]+"', 'versionName = "4.0.0-alpha1"', s, count=1)
p.write_text(s, encoding='utf-8')
print('Set Android version to 4.0.0-alpha1 (versionCode 22).')
PY

if command -v node >/dev/null 2>&1; then
  python3 - "$HTML_DST" <<'PY'
from pathlib import Path
import re, sys, tempfile
s=Path(sys.argv[1]).read_text(encoding='utf-8')
blocks=re.findall(r'<script(?: [^>]*)?>(.*?)</script>',s,re.S)
if not blocks:
    raise SystemExit('No inline JavaScript block found.')
Path('/tmp/nd_route_finder_v4_check.js').write_text(blocks[-1],encoding='utf-8')
PY
  node --check /tmp/nd_route_finder_v4_check.js
  echo "JavaScript syntax check passed."
fi

exec "$ROOT/build_and_install.sh"
