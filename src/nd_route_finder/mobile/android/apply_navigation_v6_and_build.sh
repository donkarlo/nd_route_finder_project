#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
HTML_SRC="$ROOT/route_finder_v6.html"
HTML_DST="$ROOT/app/src/main/assets/route_finder.html"
MAIN="$ROOT/app/src/main/java/com/ndroutefinder/mobile/MainActivity.java"
GRADLE="$ROOT/app/build.gradle.kts"

if [[ ! -f "$HTML_SRC" ]]; then
  echo "Missing: $HTML_SRC" >&2
  exit 2
fi

STAMP="20260916"
[[ -f "$HTML_DST.pre_navigation_v6_${STAMP}.bak" ]] || cp "$HTML_DST" "$HTML_DST.pre_navigation_v6_${STAMP}.bak"
[[ -f "$MAIN.pre_navigation_v6_${STAMP}.bak" ]] || cp "$MAIN" "$MAIN.pre_navigation_v6_${STAMP}.bak"
[[ -f "$GRADLE.pre_navigation_v6_${STAMP}.bak" ]] || cp "$GRADLE" "$GRADLE.pre_navigation_v6_${STAMP}.bak"

cp "$HTML_SRC" "$HTML_DST"
echo "Installed mobile v6 UI: stable 3D controls, 3D heading arrow, deterministic route arrows, Garmin default."

python3 - "$MAIN" "$GRADLE" <<'PY'
from pathlib import Path
import re
import sys

main = Path(sys.argv[1])
gradle = Path(sys.argv[2])

text = main.read_text(encoding="utf-8")
old = '    private String locationSource = "phone";'
new = '    private String locationSource = "garmin";'
if old in text:
    text = text.replace(old, new, 1)
    main.write_text(text, encoding="utf-8")
    print("Set native default GPS source to Garmin Fenix 8.")
elif new in text:
    print("Native default GPS source is already Garmin.")
else:
    raise SystemExit("Could not find MainActivity locationSource default; no blind edit made.")

g = gradle.read_text(encoding="utf-8")
g2 = re.sub(r'versionCode\s*=\s*\d+', 'versionCode = 24', g, count=1)
g2 = re.sub(r'versionName\s*=\s*"[^"]+"', 'versionName = "6.0.0-alpha1"', g2, count=1)
if g2 == g and ('versionCode = 24' not in g or 'versionName = "6.0.0-alpha1"' not in g):
    raise SystemExit("Could not update Android version.")
gradle.write_text(g2, encoding="utf-8")
print("Set Android version to 6.0.0-alpha1 (versionCode 24).")
PY

if command -v node >/dev/null 2>&1; then
  TMP_JS="$(mktemp --suffix=.js)"
  python3 - "$HTML_DST" "$TMP_JS" <<'PY'
from pathlib import Path
import re
import sys

html = Path(sys.argv[1]).read_text(encoding="utf-8")
blocks = re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', html, flags=re.S | re.I)
code = "\n".join(block for block in blocks if block.strip())
Path(sys.argv[2]).write_text(code, encoding="utf-8")
PY
  node --check "$TMP_JS"
  rm -f "$TMP_JS"
  echo "JavaScript syntax check passed."
else
  echo "node not found; skipped JavaScript syntax check."
fi

bash "$ROOT/build_and_install.sh"
