#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
ASSET_DIR="$ROOT/app/src/main/assets"
ACTIVE_HTML="$ASSET_DIR/route_finder.html"
V5_HTML="$ROOT/route_finder_v5.html"
GRADLE_FILE="$ROOT/app/build.gradle.kts"

if [[ ! -f "$V5_HTML" ]]; then
  echo "Missing: $V5_HTML" >&2
  exit 2
fi

HTML_BACKUP="$ASSET_DIR/route_finder.html.pre_navigation_v5_20260916.bak"
if [[ -f "$ACTIVE_HTML" && ! -f "$HTML_BACKUP" ]]; then
  cp -p "$ACTIVE_HTML" "$HTML_BACKUP"
  echo "Backup: $HTML_BACKUP"
fi

cp -f "$V5_HTML" "$ACTIVE_HTML"
echo "Installed navigation v5 UI."

if [[ -f "$GRADLE_FILE" ]]; then
  GRADLE_BACKUP="$ROOT/app/build.gradle.kts.pre_navigation_v5_20260916.bak"
  if [[ ! -f "$GRADLE_BACKUP" ]]; then
    cp -p "$GRADLE_FILE" "$GRADLE_BACKUP"
    echo "Backup: $GRADLE_BACKUP"
  fi
  python3 - "$GRADLE_FILE" <<'PY'
from pathlib import Path
import re, sys
p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
s = re.sub(r'versionCode\s*=\s*\d+', 'versionCode = 23', s)
s = re.sub(r'versionName\s*=\s*"[^"]+"', 'versionName = "5.0.0-alpha1"', s)
p.write_text(s, encoding="utf-8")
print("Set Android version to 5.0.0-alpha1 (versionCode 23).")
PY
fi

python3 - "$ACTIVE_HTML" <<'PY'
from pathlib import Path
import re, subprocess, sys, tempfile
p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
blocks = re.findall(r'<script(?: [^>]*)?>(.*?)</script>', s, flags=re.S)
inline = "\n".join(b for b in blocks if b.strip())
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
    f.write(inline)
    tmp = f.name
try:
    subprocess.run(["node", "--check", tmp], check=True)
    print("JavaScript syntax check passed.")
finally:
    Path(tmp).unlink(missing_ok=True)
PY

# build_and_install.sh can lose the executable bit after Dropbox sync; invoke it through bash.
bash "$ROOT/build_and_install.sh"
