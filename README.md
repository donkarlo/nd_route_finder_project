# nd_route_finder

Qt/PySide6 round-trip route finder for cycling and hiking.

## Run directly in PyCharm

Keep `route_finder.py` next to `src/` and run it with your existing Python interpreter.

Example interpreter:

```text
/home/donkarlo/phd-venv/bin/python
```

No new virtual environment is required.

## Main behavior

- Recursively reads previous GPX tracks from the selected GPX root folder.
- Lets you choose Cycling or Hiking.
- Lets you choose the start point by clicking the map or entering latitude/longitude.
- Generates a round trip close to the requested distance.
- Treats the requested maximum slope as a mandatory constraint.
- Filters access restrictions, unbridged fords, mapped water crossings without a bridge, and mapped blocked barriers without an opening.
- Draws previous GPX tracks and the generated route with different styles.

## Elevation and slope

Slope is always evaluated.

If `DEM / GeoTIFF` is left empty, the application automatically downloads the required Copernicus GLO-30 30 m elevation tile(s) from the public Copernicus DEM dataset on AWS and caches them under:

```text
~/.cache/nd_route_finder/dem/copernicus_glo30/
```

The same tile is reused on later runs, so elevation is not requested point-by-point from a public elevation API and the previous HTTP 429 problem is avoided.

If you select your own DEM/GeoTIFF, that raster is used instead of the automatic Copernicus download.

The final route is accepted only when its evaluated maximum slope is at or below the value entered in `Maximum slope`.

Copernicus GLO-30 is a 30 m Digital Surface Model, so the computed value is a terrain-based slope estimate rather than a survey-grade measurement of the road surface.

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


## GPX save guarantees (v0.7)

- The output path is fixed when generation starts and the input controls are locked until the run finishes.
- GPX output is written atomically through a temporary file and `os.replace`.
- The generated file must exist, be non-empty, and parse back successfully before the UI reports success.
- The Output GPX field is synchronized with the exact verified path returned by the writer.


## Map rendering

The Qt WebEngine map is written to a local cached HTML document and loaded with a file URL. This avoids Qt WebEngine's `setHtml()` data-URL size limit when many historical GPX tracks are displayed. The generated route is drawn as a thick red line with a white outline, while previous tracks are gray.
