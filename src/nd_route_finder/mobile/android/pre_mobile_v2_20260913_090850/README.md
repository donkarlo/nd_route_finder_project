# ND Route Finder Garmin Android Sender

Standalone Android utility for `nd_route_finder_project`.

## What it does

- Enter one latitude/longitude pair and send it as a GPX waypoint to Garmin Explore.
- Paste coordinates such as `47.070714, 15.439504`.
- Choose an existing `.gpx` route/track/waypoint file and open it in Garmin Explore.
- Tries the Garmin Explore package directly (`com.garmin.android.apps.explore`).
- Falls back to the normal Android "Open with" chooser if Explore cannot be launched directly.
- No Garmin credentials, unofficial Garmin Connect API, network permission, or background service is used.

Garmin Explore can import GPX on Android and sync compatible content to a paired compatible Garmin device. Fenix 8 is on Garmin's Explore compatibility list.

## Build on the user's Ubuntu machine

This project intentionally contains no copied Gradle wrapper binary. The user's existing `nd_planning_project`
already has a Gradle 9.6 wrapper compatible with the Android toolchain being used there.

From this project directory:

```bash
/home/donkarlo/Dropbox/repo/nd_planning_project/src/nd_planning/mobile/android/gradlew   -p "$PWD" :app:assembleDebug
```

APK output:

```text
app/build/outputs/apk/debug/app-debug.apk
```

Install:

```bash
~/Android/Sdk/platform-tools/adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## Typical point workflow

1. Pair Fenix 8 with Garmin Explore.
2. Open ND Garmin Sender.
3. Paste or type latitude/longitude.
4. Tap **Send point to Garmin Explore**.
5. Garmin Explore opens the GPX waypoint.
6. Complete the import in Explore and let Explore sync with the watch.

## Existing GPX workflow

Tap **Choose GPX file and send**, choose a GPX file produced by Route Finder, then import it in Garmin Explore.

## Design constraint

The desktop Route Finder source is untouched. This Android utility is standalone so the working route-generation logic
cannot be broken by Garmin integration.


## Project location

`/home/donkarlo/Dropbox/repo/nd_route_finder_project/src/nd_route_finder/mobile/android`

## Android icon

The launcher icon is rendered from the desktop Route Finder icon in `assets/app_icon.svg`. A source copy is kept in `app/src/main/icon_source/app_icon.svg`, and Android density PNGs are in `res/mipmap-*`.
