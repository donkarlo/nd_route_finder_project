# ND Route Finder — Android + Garmin bridge (v2 alpha)

This folder is the mobile companion of the existing desktop `nd_route_finder` project.
It does **not** replace or modify the desktop Python implementation.

The Android `applicationId` remains `com.ndroutefinder.garmin`, with a higher version code, so installing this APK with `adb install -r` upgrades/replaces the earlier experimental **ND Garmin Sender** app instead of creating a second launcher app.

## What this version does

Android UI mirrors the current Route Finder workflow:

- Leaflet/OpenStreetMap map
- search by place/address
- select the start point by map click or search result
- ordered intermediate waypoints (move up/down/remove)
- Cycling / Hiking / Walking
- target distance and maximum slope
- circular route generation
- load an existing GPX
- current route in blue; earlier displayed routes in green
- distance, max-slope and elevation/slope profiles
- send a point to Garmin native navigation
- send a point to the currently active Garmin activity
- send the current GPX to Garmin Connect for course import / Send to Device

### Mobile route engine

The Android version uses the public BRouter service for the first mobile implementation.
Cycling uses the `trekking` profile. Hiking/Walking use `hiking-mountain`, which allows paths that the cycling profile rejects. BRouter also returns elevation in the GPX, so the slope constraint can be evaluated.

This is intentionally independent of the desktop OSMnx/NetworkX Python backend. The desktop single-start-point logic is untouched.

## Garmin design

There are two small Connect IQ projects under `garmin_connectiq/`.

### 1. `ND Route Target` data field

Add this data field to Walking, Running, Cycling, etc. on the Fenix. While that activity is active, the Android button:

`Navigate active Garmin activity to start point`

sends the selected coordinate to the data field. The data field calls Garmin Connect IQ `routeTo(...)`; Garmin's native activity/navigation then calculates the route to that coordinate.

### 2. `ND Route Receiver` watch app

The Android button:

`Open Garmin navigation for start point`

sends the coordinate to the watch app and asks Garmin Connect to open that app. The watch app saves the point as a Garmin waypoint and hands its native intent back to Garmin, so the watch can offer its normal navigation/activity handling.

### 3. Full GPX route

The Android button:

`Send current GPX route to Garmin Connect`

opens/shares the GPX to **Garmin Connect** (not Garmin Explore). Import/save the course there and use `Send to Device` so it is stored as a course/route on the watch.

Connect IQ Mobile SDK does not expose a general phone-local `sendGpxFile()` operation for arbitrary GPX files, so this full-route path deliberately uses Garmin Connect's GPX import flow.

## Build Android APK

From this directory:

```bash
chmod +x build_and_install.sh
./build_and_install.sh
```

The script automatically creates `local.properties` when Android SDK is found at one of:

- `$ANDROID_SDK_ROOT`
- `$ANDROID_HOME`
- `$HOME/Android/Sdk`

It also reuses the working Gradle wrapper from the planning project when this folder does not contain a wrapper.

APK output:

```text
app/build/outputs/apk/debug/app-debug.apk
```

If exactly one ADB device is connected, the script also installs the APK. If several ADB transports are visible, it prints them and leaves installation to an explicit `adb -s <serial> install -r ...` command instead of failing with `more than one device/emulator`.

## Build the Fenix 8 Connect IQ apps

You need Garmin Connect IQ SDK 9.2 or newer and a developer key.

```bash
chmod +x garmin_connectiq/build_garmin_apps.sh
GARMIN_DEVELOPER_KEY=/path/to/developer_key.der \
  ./garmin_connectiq/build_garmin_apps.sh
```

Default device target is `fenix847mm`, Garmin's product target for Fenix 8 47/51mm AMOLED. To override:

```bash
GARMIN_DEVICE=fenix8solar51mm \
GARMIN_DEVELOPER_KEY=/path/to/developer_key.der \
  ./garmin_connectiq/build_garmin_apps.sh
```

Outputs:

```text
garmin_connectiq/build/nd_route_receiver.prg
garmin_connectiq/build/nd_route_datafield.prg
```

For development/sideload testing, copy both PRG files to the watch's `GARMIN/APPS` directory. Then add `ND Route Target` as a data field to the Walking/Run/Cycling activity in which you want the phone to retarget navigation.

## Garmin phone requirements

- Garmin Connect must be installed on Android.
- The Fenix must be paired and shown as connected in Garmin Connect.
- The Android app uses Garmin's `ciq-companion-app-sdk:2.4.0`.
- Current Garmin Connect Android releases have a reported Connect IQ messaging regression on some phone/OS combinations. If `openApplication()` works but point messages never arrive, test the current Garmin Connect version before changing Route Finder logic.

## Source locations

Android Java:

```text
app/src/main/java/com/ndroutefinder/mobile/
```

Android map/UI:

```text
app/src/main/assets/route_finder.html
```

Connect IQ receiver and data field:

```text
garmin_connectiq/receiver/
garmin_connectiq/datafield/
```
