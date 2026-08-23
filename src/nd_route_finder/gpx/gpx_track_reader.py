from pathlib import Path

import gpxpy

from nd_route_finder.domain.geo_point import GeoPoint
from nd_route_finder.domain.track import Track


class GpxTrackReader:
    def read_many(self, paths: list[Path]) -> list[Track]:
        tracks: list[Track] = []
        for path in paths:
            try:
                tracks.append(self.read(path))
            except Exception:
                # A broken historical GPX should not prevent the rest from loading.
                continue
        return tracks

    def read(self, path: Path) -> Track:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            gpx = gpxpy.parse(handle)

        segments: list[list[GeoPoint]] = []
        for gpx_track in gpx.tracks:
            for segment in gpx_track.segments:
                points = [
                    GeoPoint(
                        latitude=float(point.latitude),
                        longitude=float(point.longitude),
                        elevation=float(point.elevation) if point.elevation is not None else None,
                    )
                    for point in segment.points
                ]
                if points:
                    segments.append(points)

        for route in gpx.routes:
            points = [
                GeoPoint(
                    latitude=float(point.latitude),
                    longitude=float(point.longitude),
                    elevation=float(point.elevation) if point.elevation is not None else None,
                )
                for point in route.points
            ]
            if points:
                segments.append(points)

        if not segments:
            for waypoint in gpx.waypoints:
                segments.append(
                    [
                        GeoPoint(
                            latitude=float(waypoint.latitude),
                            longitude=float(waypoint.longitude),
                            elevation=float(waypoint.elevation) if waypoint.elevation is not None else None,
                        )
                    ]
                )

        return Track(name=path.stem, segments=segments, source=path)
