#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

GARMIN_BRIDGE="$ROOT/app/src/main/java/com/ndroutefinder/mobile/GarminBridge.java"

if [[ -f "$GARMIN_BRIDGE" ]]; then
  python3 - "$GARMIN_BRIDGE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

old = '        } catch (InvalidStateException e) {\n            emit("Garmin GPS listener unavailable: " + message(e));\n'
new = '        } catch (InvalidStateException | ServiceUnavailableException e) {\n            emit("Garmin GPS listener unavailable: " + message(e));\n'

if old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("Applied Garmin registerForAppEvents exception fix.")
elif new in text:
    print("Garmin registerForAppEvents exception fix already present.")
else:
    print("Warning: GarminBridge exception block did not match expected text.", file=sys.stderr)
PY
fi

SDK_DIR="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"
if [[ ! -f local.properties && -d "$SDK_DIR" ]]; then
  printf 'sdk.dir=%s\n' "$SDK_DIR" > local.properties
fi

if [[ -x "$ROOT/gradlew" ]]; then
  GRADLE=("$ROOT/gradlew")
elif [[ -x "/home/donkarlo/Dropbox/repo/nd_planning_project/src/nd_planning/mobile/android/gradlew" ]]; then
  GRADLE=("/home/donkarlo/Dropbox/repo/nd_planning_project/src/nd_planning/mobile/android/gradlew" -p "$ROOT")
elif command -v gradle >/dev/null 2>&1; then
  GRADLE=(gradle -p "$ROOT")
else
  echo "No Gradle wrapper/system Gradle found." >&2
  exit 2
fi

"${GRADLE[@]}" :app:assembleDebug
APK="$ROOT/app/build/outputs/apk/debug/app-debug.apk"
echo "Built: $APK"

ADB="$SDK_DIR/platform-tools/adb"
if [[ ! -x "$ADB" ]]; then
  echo "adb not found; APK was built but not installed."
  exit 0
fi

mapfile -t DEVICES < <("$ADB" devices | awk 'NR>1 && $2=="device" {print $1}')
if [[ -n "${ANDROID_SERIAL:-}" ]]; then
  "$ADB" -s "$ANDROID_SERIAL" install -r "$APK"
  exit 0
fi

if (( ${#DEVICES[@]} == 1 )); then
  "$ADB" -s "${DEVICES[0]}" install -r "$APK"
elif (( ${#DEVICES[@]} == 0 )); then
  echo "No connected adb device; APK was built but not installed."
else
  echo "More than one adb device is connected. APK is built."
  echo "Choose one with:"
  echo "  $ADB devices -l"
  echo "Then install with:"
  echo "  ANDROID_SERIAL='<serial>' ./build_and_install.sh"
fi
