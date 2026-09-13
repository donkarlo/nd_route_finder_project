#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/donkarlo/Dropbox/repo/nd_route_finder_project/src/nd_route_finder/mobile/android/garmin_connectiq"

python3 - <<'PY'
from pathlib import Path

root = Path("/home/donkarlo/Dropbox/repo/nd_route_finder_project/src/nd_route_finder/mobile/android/garmin_connectiq")
files = [
    root / "receiver/source/NdRouteReceiverApp.mc",
    root / "datafield/source/NdRouteTargetField.mc",
]

old = "function onPhoneMessage(message) {"
new = "function onPhoneMessage(message as Communications.PhoneAppMessage) as Void {"

for path in files:
    text = path.read_text(encoding="utf-8")
    if new in text:
        print(f"Already fixed: {path}")
        continue
    if old not in text:
        raise SystemExit(f"Expected callback signature not found in {path}")
    backup = path.with_suffix(path.suffix + ".pre_phone_message_type_fix")
    backup.write_text(text, encoding="utf-8")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"Fixed: {path}")
    print(f"Backup: {backup}")
PY

cd "$ROOT"
./build_garmin_apps.sh
