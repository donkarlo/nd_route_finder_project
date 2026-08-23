import math
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from nd_route_finder.domain.geo_point import GeoPoint


class CopernicusDemProvider:
    _BASE_URL = "https://copernicus-dem-30m.s3.amazonaws.com"
    _USER_AGENT = "nd_route_finder/0.6 (desktop route planner; Copernicus GLO-30 DEM cache)"
    _CHUNK_SIZE = 1024 * 1024

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir or (
            Path.home() / ".cache" / "nd_route_finder" / "dem" / "copernicus_glo30"
        )

    def ensure_for_points(
        self,
        points: list[GeoPoint],
        status: Callable[[str], None] | None = None,
    ) -> list[Path]:
        if not points:
            raise ValueError("Cannot determine DEM tiles for an empty route.")

        notify = status or (lambda _: None)
        tile_names = sorted({self._tile_name(point) for point in points})
        paths: list[Path] = []
        for tile_name in tile_names:
            paths.append(self._ensure_tile(tile_name, notify))
        return paths

    def _ensure_tile(self, tile_name: str, notify: Callable[[str], None]) -> Path:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        destination = self._cache_dir / f"{tile_name}.tif"
        if destination.is_file() and destination.stat().st_size > 100_000:
            notify(f"Using cached elevation tile {tile_name} …")
            return destination

        partial = destination.with_suffix(destination.suffix + ".part")
        if partial.exists():
            partial.unlink()

        url = f"{self._BASE_URL}/{tile_name}/{tile_name}.tif"
        request = Request(url, headers={"User-Agent": self._USER_AGENT})
        notify(f"Downloading Copernicus GLO-30 elevation tile {tile_name} …")

        try:
            with urlopen(request, timeout=180) as response, partial.open("wb") as output:
                total_header = response.headers.get("Content-Length")
                total = int(total_header) if total_header and total_header.isdigit() else 0
                downloaded = 0
                last_reported_mb = -1
                while True:
                    chunk = response.read(self._CHUNK_SIZE)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    downloaded_mb = downloaded // (8 * self._CHUNK_SIZE)
                    if downloaded_mb != last_reported_mb:
                        last_reported_mb = downloaded_mb
                        if total > 0:
                            notify(
                                f"Downloading elevation tile: {downloaded / 1_048_576:.0f} / "
                                f"{total / 1_048_576:.0f} MB …"
                            )
                        else:
                            notify(
                                f"Downloading elevation tile: {downloaded / 1_048_576:.0f} MB …"
                            )
        except HTTPError as exc:
            partial.unlink(missing_ok=True)
            if exc.code == 404:
                raise RuntimeError(
                    "No Copernicus GLO-30 DEM tile is available for part of this route. "
                    "Choose a local DEM/GeoTIFF manually for this area."
                ) from exc
            raise RuntimeError(
                f"Copernicus DEM download failed with HTTP {exc.code}."
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            partial.unlink(missing_ok=True)
            raise RuntimeError(f"Copernicus DEM download failed: {exc}") from exc

        if not partial.is_file() or partial.stat().st_size <= 100_000:
            partial.unlink(missing_ok=True)
            raise RuntimeError("Downloaded Copernicus DEM tile is unexpectedly small or empty.")

        partial.replace(destination)
        notify(f"Cached elevation tile: {destination}")
        return destination

    def _tile_name(self, point: GeoPoint) -> str:
        latitude_degree = math.floor(point.latitude)
        longitude_degree = math.floor(point.longitude)
        northing = self._format_latitude(latitude_degree)
        easting = self._format_longitude(longitude_degree)
        return f"Copernicus_DSM_COG_10_{northing}_{easting}_DEM"

    def _format_latitude(self, degree: int) -> str:
        hemisphere = "N" if degree >= 0 else "S"
        return f"{hemisphere}{abs(degree):02d}_00"

    def _format_longitude(self, degree: int) -> str:
        hemisphere = "E" if degree >= 0 else "W"
        return f"{hemisphere}{abs(degree):03d}_00"
