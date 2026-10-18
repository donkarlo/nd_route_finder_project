"""Bundle a compact snapshot of past GPX geometry for offline Android scoring.

Run at each Android build when past GPX files in the Dropbox source change.
This is historical reference geometry only, not a route or a location upload.
"""
from pathlib import Path
import gzip
import math
import gpxpy

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path.home() / 'Dropbox/repo/nd_robotic_ai_project/data/kind/environment/map/done'
TARGET = ROOT / 'src/nd_route_finder/mobile/android/app/src/main/assets/history_gpx_points.csv.gz'


def dist(a, b):
    dy = (b.latitude - a.latitude) * 111195
    dx = (b.longitude - a.longitude) * (111195 * math.cos(math.radians((a.latitude + b.latitude) / 2)))
    return math.hypot(dx, dy)


def main():
    rows = set()
    count = 0
    for path in sorted(SOURCE.rglob('*.gpx')):
        try:
            with path.open(encoding='utf-8', errors='replace') as f:
                parsed = gpxpy.parse(f)
        except Exception:
            continue
        segments = [seg.points for track in parsed.tracks for seg in track.segments]
        segments.extend(route.points for route in parsed.routes)
        usable = False
        for points in segments:
            if not points:
                continue
            usable = True
            last = None
            for p in points:
                if last is not None and dist(last, p) < 32:
                    continue
                rows.add((round(p.latitude, 6), round(p.longitude, 6)))
                last = p
            rows.add((round(points[-1].latitude, 6), round(points[-1].longitude, 6)))
        if usable:
            count += 1
    if count == 0:
        raise RuntimeError(f'No past GPX tracks in {SOURCE}')
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(TARGET, 'wt', encoding='ascii', compresslevel=9) as file:
        file.write(f'#routes={count}\n')
        for lat, lon in sorted(rows):
            file.write(f'{lat:.6f},{lon:.6f}\n')
    print(f'Bundled past GPX: {count} routes, {len(rows)} points, {TARGET.stat().st_size} gzip bytes')


if __name__ == '__main__':
    main()
