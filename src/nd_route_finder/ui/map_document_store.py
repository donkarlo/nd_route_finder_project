import os
import tempfile
from pathlib import Path


class MapDocumentStore:
    def __init__(self, cache_directory: Path | None = None) -> None:
        self._cache_directory = (
            cache_directory
            if cache_directory is not None
            else Path.home() / ".cache" / "nd_route_finder" / "map"
        )
        self._current_path: Path | None = None

    def write(self, html: str) -> Path:
        self._cache_directory.mkdir(parents=True, exist_ok=True)

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._cache_directory,
                prefix="map_",
                suffix=".html",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(html)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            final_path = temporary_path.with_suffix(".ready.html")
            os.replace(temporary_path, final_path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        previous_path = self._current_path
        self._current_path = final_path
        if previous_path is not None and previous_path != final_path:
            previous_path.unlink(missing_ok=True)

        return final_path
