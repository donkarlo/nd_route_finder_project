from pathlib import Path


class GpxFileFinder:
    def find(self, root: Path) -> list[Path]:
        if not root.exists() or not root.is_dir():
            raise ValueError(f"GPX root folder does not exist: {root}")
        return sorted(path for path in root.rglob("*.gpx") if path.is_file())
