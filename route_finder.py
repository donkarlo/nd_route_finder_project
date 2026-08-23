aimport sys
from pathlib import Path


class RouteFinder:
    @staticmethod
    def run() -> int:
        project_root = Path(__file__).resolve().parent
        src_path = project_root / "src"

        if not src_path.is_dir():
            raise FileNotFoundError(
                f"Could not find the src directory next to {Path(__file__).name}: {src_path}"
            )

        src_text = str(src_path)
        if src_text not in sys.path:
            sys.path.insert(0, src_text)

        from nd_route_finder.entrypoint.launcher import Launcher

        return Launcher.run()


if __name__ == "__main__":
    raise SystemExit(RouteFinder.run())
