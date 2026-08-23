import math
import statistics
from collections.abc import Mapping
from pathlib import Path

import networkx as nx
import rasterio
from rasterio.warp import transform

from nd_route_finder.domain.geo_point import GeoPoint
from nd_route_finder.domain.route_candidate import RouteCandidate


class ElevationEnricher:
    _EARTH_RADIUS_M = 6_371_008.8
    _MAX_PROFILE_STEP_M = 110.0
    _MIN_GRADE_WINDOW_M = 70.0
    _MAX_GRADE_WINDOW_M = 180.0

    def __init__(self) -> None:
        self._cache: dict[tuple[float, float], float] = {}

    def evaluate_candidate(
        self,
        graph: nx.MultiDiGraph,
        candidate: RouteCandidate,
        dem_paths: list[Path],
    ) -> RouteCandidate:
        points, segment_lengths, special_segments, explicit_inclines = self._route_profile(
            graph,
            candidate,
        )
        if len(points) < 2:
            raise RuntimeError("The candidate route contains no usable elevation profile.")
        if not dem_paths:
            raise RuntimeError("No DEM raster is available for slope evaluation.")

        self._ensure_raster_elevations(points, dem_paths)
        elevations = [self._require_elevation(point) for point in points]
        elevations = self._median_smooth(elevations, special_segments)
        candidate.max_grade_percent = max(
            self._calculate_windowed_max_grade(
                elevations,
                segment_lengths,
                special_segments,
            ),
            max(explicit_inclines, default=0.0),
        )
        return candidate

    def uncached_profile_point_count(
        self,
        graph: nx.MultiDiGraph,
        candidate: RouteCandidate,
    ) -> int:
        points, _, _, _ = self._route_profile(graph, candidate)
        return len({self._key(point) for point in points if self._key(point) not in self._cache})

    def _route_profile(
        self,
        graph: nx.MultiDiGraph,
        candidate: RouteCandidate,
    ) -> tuple[list[GeoPoint], list[float], list[bool], list[float]]:
        if len(candidate.nodes) < 2:
            return [], [], [], []

        first_node = candidate.nodes[0]
        points = [
            GeoPoint(
                latitude=float(graph.nodes[first_node]["y"]),
                longitude=float(graph.nodes[first_node]["x"]),
            )
        ]
        segment_lengths: list[float] = []
        special_segments: list[bool] = []
        explicit_inclines: list[float] = []

        for u, v in zip(candidate.nodes, candidate.nodes[1:]):
            edges = graph.get_edge_data(u, v)
            if not edges:
                continue
            data = min(
                edges.values(),
                key=lambda edge: float(edge.get("route_cost", math.inf)),
            )
            edge_length = max(0.1, float(data.get("length", 0.1)))
            special = self._is_bridge_or_tunnel(data)
            incline = self._explicit_incline_percent(data.get("incline"))
            if incline is not None:
                explicit_inclines.append(abs(incline))

            edge_points = self._sample_edge(graph, u, v, data, edge_length, special)
            if not edge_points:
                continue
            sub_length = edge_length / len(edge_points)
            for point in edge_points:
                if self._same_position(points[-1], point):
                    continue
                points.append(point)
                segment_lengths.append(sub_length)
                special_segments.append(special)

        return points, segment_lengths, special_segments, explicit_inclines

    def _sample_edge(
        self,
        graph: nx.MultiDiGraph,
        u: int,
        v: int,
        data: Mapping[str, object],
        edge_length_m: float,
        special: bool,
    ) -> list[GeoPoint]:
        end = GeoPoint(
            latitude=float(graph.nodes[v]["y"]),
            longitude=float(graph.nodes[v]["x"]),
        )
        if special or edge_length_m <= self._MAX_PROFILE_STEP_M:
            return [end]

        geometry = data.get("geometry")
        if geometry is None or not hasattr(geometry, "coords"):
            start = GeoPoint(
                latitude=float(graph.nodes[u]["y"]),
                longitude=float(graph.nodes[u]["x"]),
            )
            count = max(1, math.ceil(edge_length_m / self._MAX_PROFILE_STEP_M))
            return [self._interpolate(start, end, index / count) for index in range(1, count + 1)]

        coords = [(float(x), float(y)) for x, y in geometry.coords]
        if len(coords) < 2:
            return [end]
        start_lon = float(graph.nodes[u]["x"])
        start_lat = float(graph.nodes[u]["y"])
        first_error = (coords[0][0] - start_lon) ** 2 + (coords[0][1] - start_lat) ** 2
        last_error = (coords[-1][0] - start_lon) ** 2 + (coords[-1][1] - start_lat) ** 2
        if last_error < first_error:
            coords.reverse()

        polyline = [GeoPoint(latitude=lat, longitude=lon) for lon, lat in coords]
        cumulative = [0.0]
        for first, second in zip(polyline, polyline[1:]):
            cumulative.append(cumulative[-1] + self._distance(first, second))
        total = cumulative[-1]
        if total <= 0.0:
            return [end]

        count = max(1, math.ceil(edge_length_m / self._MAX_PROFILE_STEP_M))
        result: list[GeoPoint] = []
        for sample_index in range(1, count + 1):
            target = total * sample_index / count
            result.append(self._point_at_distance(polyline, cumulative, target))
        result[-1] = end
        return result

    def _point_at_distance(
        self,
        points: list[GeoPoint],
        cumulative: list[float],
        target: float,
    ) -> GeoPoint:
        for index in range(1, len(cumulative)):
            if cumulative[index] >= target:
                span = cumulative[index] - cumulative[index - 1]
                ratio = 1.0 if span <= 0.0 else (target - cumulative[index - 1]) / span
                return self._interpolate(points[index - 1], points[index], ratio)
        return points[-1]

    def _interpolate(self, first: GeoPoint, second: GeoPoint, ratio: float) -> GeoPoint:
        return GeoPoint(
            latitude=first.latitude + (second.latitude - first.latitude) * ratio,
            longitude=first.longitude + (second.longitude - first.longitude) * ratio,
        )

    def _ensure_raster_elevations(self, points: list[GeoPoint], dem_paths: list[Path]) -> None:
        missing_by_key: dict[tuple[float, float], GeoPoint] = {}
        for point in points:
            key = self._key(point)
            if key not in self._cache:
                missing_by_key[key] = point
        missing_points = list(missing_by_key.values())
        if not missing_points:
            return

        self._cache.update(self._read_raster_elevations(missing_points, dem_paths))

    def _read_raster_elevations(
        self,
        points: list[GeoPoint],
        dem_paths: list[Path],
    ) -> dict[tuple[float, float], float]:
        for dem_path in dem_paths:
            if not dem_path.exists():
                raise ValueError(f"DEM file does not exist: {dem_path}")

        unresolved = {self._key(point): point for point in points}
        result: dict[tuple[float, float], float] = {}

        for dem_path in dem_paths:
            if not unresolved:
                break
            with rasterio.open(dem_path) as dataset:
                if dataset.crs is None:
                    raise ValueError(f"DEM has no CRS information: {dem_path}")

                keys = list(unresolved.keys())
                candidate_points = [unresolved[key] for key in keys]
                longitudes = [point.longitude for point in candidate_points]
                latitudes = [point.latitude for point in candidate_points]
                xs, ys = transform("EPSG:4326", dataset.crs, longitudes, latitudes)
                bounds = dataset.bounds

                covered_indices = [
                    index
                    for index, (x, y) in enumerate(zip(xs, ys))
                    if bounds.left <= x <= bounds.right and bounds.bottom <= y <= bounds.top
                ]
                if not covered_indices:
                    continue

                coordinates = [(xs[index], ys[index]) for index in covered_indices]
                samples = list(dataset.sample(coordinates))
                nodata = dataset.nodata

                for covered_index, sample in zip(covered_indices, samples):
                    if len(sample) == 0:
                        continue
                    value = float(sample[0])
                    if nodata is not None and math.isclose(value, float(nodata)):
                        continue
                    if not math.isfinite(value):
                        continue
                    key = keys[covered_index]
                    result[key] = value
                    unresolved.pop(key, None)

        if unresolved:
            point = next(iter(unresolved.values()))
            raise RuntimeError(
                "The DEM data does not cover the complete candidate route. "
                f"Missing elevation near {point.latitude:.6f}, {point.longitude:.6f}."
            )
        return result

    def _calculate_windowed_max_grade(
        self,
        elevations: list[float],
        segment_lengths: list[float],
        special_segments: list[bool],
    ) -> float:
        if len(elevations) < 2:
            return 0.0

        cumulative = [0.0]
        special_prefix = [0]
        for length, special in zip(segment_lengths, special_segments):
            cumulative.append(cumulative[-1] + length)
            special_prefix.append(special_prefix[-1] + (1 if special else 0))

        max_grade = 0.0
        for start in range(len(elevations) - 1):
            best_end: int | None = None
            for end in range(start + 1, len(elevations)):
                distance = cumulative[end] - cumulative[start]
                if distance < self._MIN_GRADE_WINDOW_M:
                    continue
                best_end = end
                if distance >= self._MAX_GRADE_WINDOW_M:
                    break
                if special_prefix[end] - special_prefix[start] > 0:
                    continue
                grade = abs(elevations[end] - elevations[start]) / distance * 100.0
                max_grade = max(max_grade, grade)
            if best_end is not None:
                distance = cumulative[best_end] - cumulative[start]
                if (
                    distance >= self._MIN_GRADE_WINDOW_M
                    and special_prefix[best_end] - special_prefix[start] == 0
                ):
                    grade = abs(elevations[best_end] - elevations[start]) / distance * 100.0
                    max_grade = max(max_grade, grade)
        return max_grade

    def _median_smooth(
        self,
        elevations: list[float],
        special_segments: list[bool],
    ) -> list[float]:
        if len(elevations) < 3:
            return elevations
        result = elevations.copy()
        for index in range(1, len(elevations) - 1):
            if special_segments[index - 1] or special_segments[index]:
                continue
            result[index] = float(
                statistics.median(
                    (elevations[index - 1], elevations[index], elevations[index + 1])
                )
            )
        return result

    def _require_elevation(self, point: GeoPoint) -> float:
        key = self._key(point)
        if key not in self._cache:
            raise RuntimeError(
                f"No elevation is available near {point.latitude:.6f}, {point.longitude:.6f}."
            )
        return self._cache[key]

    def _explicit_incline_percent(self, value: object) -> float | None:
        values = value if isinstance(value, list) else [value]
        for item in values:
            if item is None:
                continue
            text = str(item).strip().lower()
            if not text or text in {"up", "down", "none", "nan"}:
                continue
            text = text.rstrip("%")
            try:
                return float(text)
            except ValueError:
                continue
        return None

    def _is_bridge_or_tunnel(self, data: Mapping[str, object]) -> bool:
        return self._positive_tag(data.get("bridge")) or self._positive_tag(data.get("tunnel"))

    def _positive_tag(self, value: object) -> bool:
        values = value if isinstance(value, list) else [value]
        for item in values:
            if item is None:
                continue
            if str(item).strip().lower() not in {"", "no", "false", "0", "none", "nan"}:
                return True
        return False

    def _same_position(self, first: GeoPoint, second: GeoPoint) -> bool:
        return (
            abs(first.latitude - second.latitude) <= 1e-10
            and abs(first.longitude - second.longitude) <= 1e-10
        )

    def _distance(self, first: GeoPoint, second: GeoPoint) -> float:
        lat1 = math.radians(first.latitude)
        lat2 = math.radians(second.latitude)
        dlat = lat2 - lat1
        dlon = math.radians(second.longitude - first.longitude)
        a = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
        )
        return self._EARTH_RADIUS_M * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    def _key(self, point: GeoPoint) -> tuple[float, float]:
        return round(point.latitude, 6), round(point.longitude, 6)
