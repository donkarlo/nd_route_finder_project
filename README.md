# nd_route_finder

A route finder for circular and direct cycling, hiking, and walking routes.

The application takes previously travelled GPX routes, a start point, a target
distance, and a maximum allowed slope as input. It generates a round-trip route
that tries to maximize the distance from previously traversed routes while
satisfying the routing, access, and slope constraints.

<img src="example.jpg" width="600">


### Closest feasible circular route when an exact match is unavailable

In the Ubuntu planner the default previous-route folder (when it exists) is
`/home/donkarlo/Dropbox/repo/nd_robotic_ai_project/data/kind/environment/map/done`.
All previous GPX files are loaded for spatial overlap comparison. In
**Circular + Match target distance**, the program evaluates candidate length,
estimated maximum slope, overlap with previously ridden GPX paths (sampled at
roughly 38 m with a 38 m tolerance), and return-leg retracing. It chooses the
lowest combined penalty even if no route meets all soft targets exactly.
Disconnected graph segments no longer immediately end the search: BRouter
checks multiple distinct return corridors with cycling or walking profiles.
If even the BRouter fallback cannot reach the locations, it reports that no
valid road-routed GPX was obtainable rather than inventing a path.

Sample checked on 18 Oct 2026: 50 km and 20% requested via
Semriacherstraße 100, 8102; 49.59 km, estimated 17.68% grade,
40.3% overlap with the 38 GPX tracks, 8.6% return retrace. BRouter was the
backend; independent Overpass barrier verification was unavailable.

## Route shape, previous GPX tracks, and phone heading

- **Circular**: return to the starting point via any ordered stops. **Direct**:
  visit those stops in order and finish at the last selected point.
- The GPX root is optional in the Ubuntu planner: leave it blank when no
  previously travelled GPX files are available. In **Auto** mode, a route with
  specified stops uses shortest-path routing when history is empty; otherwise
  circular routing can optimize the requested target distance. **Shortest**
  explicitly ignores target distance; **Match target distance** retains the
  original exploratory distance-matching behavior. A shortest circular route
  needs at least one stop to define the loop.
- Android Plan route has the same shape and priority selectors. A compressed
  snapshot of the 38 past GPX tracks from the configured Dropbox history folder
  is bundled with the APK for offline overlap ranking. **Auto** compares
  candidate routes against the previous rides and soft distance/slope targets;
  when no history is available and there is a destination, it picks the shortest
  available route. **Shortest** always overrides historical comparison. Android
  generates BRouter trekking/fastbike cycling candidates, including alternative
  return corridors, and offers the best available near miss if target distance
  or slope cannot be met exactly. To include new rides in this *snapshot*, run
  `scripts/build_android_route_history.py` on Ubuntu and rebuild/reinstall the APK;
  the phone cannot directly read the Ubuntu Dropbox root.
- Android Navigate GPX includes a persisted **Garmin heading calibration** value
  from -180 to +180 degrees (clockwise positive), which rotates the red
  elongated isosceles location arrow. With phone GPS, the arrow retains the
  latest actual direction of travel, even when the phone is turned or stops.
  The 2D arrow is flat, and the 3D map uses a gently beveled three-sided visual.
  Without a valid heading the position remains visible as a dot. Garmin-only
  calibration affects orientation in both maps, not recorded track coordinates.
- The maximum slope is evaluated as before; when it cannot be met, a route
  may be returned with an explicit constraint-fallback warning.

## Main behavior

- Recursively reads previous GPX tracks from the selected GPX root folder.
- Lets you choose `Cycling` or `Hiking`.
- Lets you choose the start point by clicking the map or entering latitude and
  longitude manually.
- Generates a round trip close to the requested distance.
- Treats the requested maximum slope as a mandatory constraint.
- Prefers routes that remain as far as possible from previously travelled GPX
  tracks.
- Filters access restrictions, unbridged fords, mapped water crossings without
  a bridge, and mapped blocked barriers without an opening.
- Draws previous GPX tracks and the generated route with different styles.
- Shows resizable elevation and slope profile panels after route generation.
- Shows the corresponding route position on the map while the mouse moves over
  either profile chart.
- Loads an existing GPX route on demand and shows its elevation and slope
  profiles when the GPX contains elevation data.


## Quick usage

1. Select the root folder containing previously travelled GPX tracks.
2. Choose `Cycling` or `Hiking`.
3. Select the start point by clicking on the map or entering latitude and
   longitude manually.
4. Enter the desired round-trip distance.
5. Enter the maximum allowed slope.
6. Optionally select a local DEM/GeoTIFF file.
7. Select the output GPX path.
8. Generate the route.
9. Resize the profile area or the two profile panels by dragging the splitter
   handles.
10. Move the mouse over either profile to locate that point on the map.

To inspect an existing GPX instead of generating a new route, click `Load GPX`
and select the file. The route is displayed on the map and the same elevation
and slope profile panels are used for inspection.


## Inputs

The route generator uses the following inputs:

- GPX root directory containing previously travelled routes
- Activity type: `Cycling` or `Hiking`
- Start latitude and longitude
- Desired round-trip distance
- Maximum allowed slope
- Optional local DEM/GeoTIFF
- Output GPX path

For profile inspection, a single existing `.gpx` file can also be loaded with
`Load GPX`.


## Output

The application produces a GPX file containing the generated round-trip route.

The generated route is also displayed on the map together with previously
travelled GPX tracks so that the relationship between new and previously
traversed areas can be inspected visually.

After generation, two resizable profile panels are displayed below the map:

- elevation in metres versus travelled distance in kilometres
- slope in percent versus travelled distance in kilometres

Moving the mouse over either chart displays the corresponding position on the
map.


## Routing objective

The main objective is to generate a round trip that explores new areas.

Previously travelled GPX tracks are used as a spatial penalty during route
selection. Candidate routes that remain farther from those tracks are preferred
over routes that repeatedly follow previously travelled paths.

At the same time, the generated route must satisfy constraints such as:

- requested route distance
- maximum allowed slope
- activity type
- access restrictions
- blocked barriers
- unsuitable water crossings


## OpenStreetMap / Overpass outages

The Ubuntu planner retries a failed routing-network or obstacle-feature query
through other public Overpass servers, without discarding your map selections.
A 502 response, a rate-limit response or a network timeout is a temporary
Overpass service problem, **not evidence that two places cannot be connected**.
If all worldwide Overpass providers fail, the Ubuntu planner can request a
**BRouter backup** for routes with ordered waypoints. This backup uses a
cycling/walking routing profile, provides GPX elevations for an estimated slope
check, and **clearly warns** that its barriers and water crossings have not
been independently verified with Overpass. No independent verification is
silently claimed. When neither backend is available, the UI gives an actionable
error instead of raw server HTML. Successful Overpass responses are cached by
OSMnx.

## Elevation and slope

Slope is always evaluated.

If `DEM / GeoTIFF` is left empty, the application automatically downloads the
required Copernicus GLO-30 30 m elevation tile(s) from the public Copernicus DEM
dataset on AWS and caches them under:

```text
~/.cache/nd_route_finder/dem/copernicus_glo30/
```

The same tile is reused on later runs, so elevation is not requested
point-by-point from a public elevation API and the previous HTTP 429 problem is
avoided.

If you select your own DEM/GeoTIFF, that raster is used instead of the automatic
Copernicus download.

The final route is accepted only when its evaluated maximum slope is at or below
the value entered in `Maximum slope`.

Copernicus GLO-30 is a 30 m Digital Surface Model, so the computed value is a
terrain-based slope estimate rather than a survey-grade measurement of the road
surface.

The interactive slope profile uses a centered 100 m window to avoid displaying
point-to-point noise as the local grade. Existing GPX files can be profiled when
they contain elevation values for all route points. If elevation values are
missing, the route is still shown on the map but the application reports that a
reliable elevation or slope profile cannot be calculated from that file.


## GPX output reliability

The GPX output process is designed to prevent incomplete or incorrectly reported
output files.

- The output path is fixed when generation starts.
- Input controls are locked until the generation run finishes.
- GPX output is written atomically through a temporary file and `os.replace`.
- The generated file must exist.
- The generated file must be non-empty.
- The generated file must parse back successfully before the UI reports success.
- The `Output GPX` field is synchronized with the exact verified path returned
  by the writer.


## Map rendering

The Qt WebEngine map is written to a local cached HTML document and loaded with
a file URL.

This avoids Qt WebEngine's `setHtml()` data-URL size limit when many historical
GPX tracks are displayed.

The generated route is drawn as a thick red line with a white outline, while
previously travelled tracks are displayed in gray.

A temporary marker is displayed on the map while a route profile is inspected,
so the chart distance, elevation or slope can be related directly to the route
geometry.


## Project structure

```text
route_finder.py

src/nd_route_finder/
├── analysis/
├── application/
├── domain/
├── entrypoint/
├── geodata/
├── gpx/
├── routing/
└── ui/
```

The Python source follows the project rule of one class per Python file.


## Installation

Install the required Python packages with:

```bash
python -m pip install -r requirements.txt
```


## Running

Run the application with:

```bash
python route_finder.py
```


## Limitations

- Slope values depend on the resolution and accuracy of the elevation model.
- Copernicus GLO-30 has a spatial resolution of approximately 30 m and therefore
  cannot represent every short or highly local road gradient accurately.
- Loaded GPX files need complete elevation values for elevation and slope
  profile visualization.
- Routing quality depends on the completeness and correctness of OpenStreetMap
  data.
- Missing or incorrect OpenStreetMap access, barrier, bridge, or surface
  information can affect route generation.
- A feasible route may not exist for very restrictive combinations of distance,
  maximum slope, access restrictions, and previously travelled areas.
- The requested route distance is a target rather than a guarantee; the final
  distance may differ when necessary to satisfy the mandatory routing
  constraints.
