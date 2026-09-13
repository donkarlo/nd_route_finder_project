#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ZIP="$HERE/nd_route_finder_mobile_v2_source.zip"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="$HERE/pre_mobile_v2_$STAMP"
TMP="$HERE/.nd_route_finder_mobile_v2_unpack_$STAMP"

if [[ ! -f "$ZIP" ]]; then
  echo "Source archive not found: $ZIP" >&2
  exit 2
fi

mkdir -p "$TMP"
unzip -q "$ZIP" -d "$TMP"

# Keep a recoverable copy of the experimental v1 source before replacing it.
mkdir -p "$BACKUP"
for item in app build.gradle.kts settings.gradle.kts gradle.properties build_and_install.sh README.md INSTALL_NOTES.txt garmin_connectiq; do
  if [[ -e "$HERE/$item" ]]; then
    mv "$HERE/$item" "$BACKUP/"
  fi
done
if [[ -f "$HERE/.gitignore" ]]; then
  cp -a "$HERE/.gitignore" "$BACKUP/.gitignore"
fi

# Preserve local Android SDK selection if the user already created it.
LOCAL_PROPERTIES=""
if [[ -f "$HERE/local.properties" ]]; then
  LOCAL_PROPERTIES="$(cat "$HERE/local.properties")"
fi

cp -a "$TMP/." "$HERE/"
rm -rf "$TMP"

if [[ -n "$LOCAL_PROPERTIES" ]]; then
  printf '%s\n' "$LOCAL_PROPERTIES" > "$HERE/local.properties"
fi

chmod +x "$HERE/build_and_install.sh" "$HERE/garmin_connectiq/build_garmin_apps.sh"

echo "Installed ND Route Finder mobile v2 source into: $HERE"
echo "Previous Android source backup: $BACKUP"
echo

if [[ "${NO_BUILD:-0}" != "1" ]]; then
  exec "$HERE/build_and_install.sh"
fi
