#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/donkarlo/Dropbox/repo/nd_route_finder_project/src/nd_route_finder/mobile/android/garmin_connectiq"

python3 - <<'PY'
from pathlib import Path

root = Path("/home/donkarlo/Dropbox/repo/nd_route_finder_project/src/nd_route_finder/mobile/android/garmin_connectiq")
items = [
    (
        root / "receiver/source/NdRouteReceiverApp.mc",
        '''            if (data["type"] != "point") {
                gReceiverStatus = "Unsupported message";
                WatchUi.requestUpdate();
                return;
            }

'''
    ),
    (
        root / "datafield/source/NdRouteTargetField.mc",
        '''            if (data["type"] != "point") {
                _label = "Bad target";
                WatchUi.requestUpdate();
                return;
            }

'''
    ),
]

for path, block in items:
    text = path.read_text(encoding="utf-8")
    if block in text:
        backup = path.with_name(path.name + ".pre_bad_message_fix")
        if not backup.exists():
            backup.write_text(text, encoding="utf-8")
        path.write_text(text.replace(block, "", 1), encoding="utf-8")
        print(f"Patched: {path}")
    elif 'data["type"] != "point"' not in text:
        print(f"Already tolerant: {path}")
    else:
        raise SystemExit(f"Unexpected source shape in {path}")
PY

cd "$ROOT"
./build_garmin_apps.sh

MTP_URI="$(gio mount -li 2>/dev/null | sed -n 's/.*activation_root=\(mtp:\/\/091e_51b8_[^[:space:]]*\/\).*/\1/p' | head -n 1 || true)"

if [[ -n "$MTP_URI" ]]; then
    DST="${MTP_URI}Internal%20Storage/GARMIN/Apps"
    echo "Garmin MTP detected: $MTP_URI"
    gio remove "$DST/nd_route_receiver.prg" 2>/dev/null || true
    gio remove "$DST/nd_route_datafield.prg" 2>/dev/null || true
    gio copy "$ROOT/build/nd_route_receiver.prg" "$DST/nd_route_receiver.prg"
    gio copy "$ROOT/build/nd_route_datafield.prg" "$DST/nd_route_datafield.prg"
    echo "Installed updated PRGs on watch:"
    gio list "$DST" | grep -E '^nd_route_(receiver|datafield)\.prg$' || true
else
    echo "Watch MTP mount not found."
    echo "Built files are in: $ROOT/build"
fi
