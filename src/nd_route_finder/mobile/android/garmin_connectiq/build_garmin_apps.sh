#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
DEVICE="${GARMIN_DEVICE:-fenix847mm}"
KEY="${GARMIN_DEVELOPER_KEY:-$ROOT/developer_key.der}"

find_monkeyc() {
  if [[ -n "${MONKEYC:-}" && -x "${MONKEYC}" ]]; then echo "$MONKEYC"; return; fi
  if command -v monkeyc >/dev/null 2>&1; then command -v monkeyc; return; fi
  for base in "$HOME/.Garmin/ConnectIQ/Sdks" "$HOME/ConnectIQ/Sdks" "$HOME/.Garmin/ConnectIQ"; do
    if [[ -d "$base" ]]; then
      local found
      found="$(find "$base" -type f -name monkeyc -perm -u+x 2>/dev/null | sort -V | tail -n 1 || true)"
      if [[ -n "$found" ]]; then echo "$found"; return; fi
    fi
  done
}

MONKEYC_BIN="$(find_monkeyc || true)"
if [[ -z "$MONKEYC_BIN" ]]; then
  echo "monkeyc not found. Install Connect IQ SDK 9.2+ with Garmin SDK Manager." >&2
  exit 2
fi
if [[ ! -f "$KEY" ]]; then
  echo "Developer key not found: $KEY" >&2
  echo "Set GARMIN_DEVELOPER_KEY=/path/to/developer_key.der" >&2
  exit 3
fi

mkdir -p "$ROOT/build"
for project in receiver datafield; do
  echo "Building $project for $DEVICE..."
  (cd "$ROOT/$project" && "$MONKEYC_BIN" -f monkey.jungle -o "$ROOT/build/nd_route_${project}.prg" -y "$KEY" -d "$DEVICE")
done

echo "Built:"
echo "  $ROOT/build/nd_route_receiver.prg"
echo "  $ROOT/build/nd_route_datafield.prg"
echo "Sideload both PRG files to GARMIN/APPS on the connected watch for testing."
