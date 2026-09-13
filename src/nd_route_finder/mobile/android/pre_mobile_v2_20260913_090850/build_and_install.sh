\
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLANNING_WRAPPER="/home/donkarlo/Dropbox/repo/nd_planning_project/src/nd_planning/mobile/android/gradlew"
ADB="${HOME}/Android/Sdk/platform-tools/adb"

if [[ -x "${ROOT}/gradlew" ]]; then
    GRADLE="${ROOT}/gradlew"
elif [[ -x "${PLANNING_WRAPPER}" ]]; then
    GRADLE="${PLANNING_WRAPPER}"
elif command -v gradle >/dev/null 2>&1; then
    GRADLE="$(command -v gradle)"
else
    echo "No Gradle executable found." >&2
    exit 1
fi

"${GRADLE}" -p "${ROOT}" :app:assembleDebug

APK="${ROOT}/app/build/outputs/apk/debug/app-debug.apk"
echo "Built: ${APK}"

if [[ -x "${ADB}" ]] && "${ADB}" devices | awk 'NR>1 && $2=="device"{found=1} END{exit !found}'; then
    "${ADB}" install -r "${APK}"
    echo "Installed on connected Android device."
else
    echo "No connected adb device; APK was built but not installed."
fi
