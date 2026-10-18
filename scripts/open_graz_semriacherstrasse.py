"""Open the verified Graz-to-Semriacherstrasse GPX in the updated Ubuntu UI."""
from pathlib import Path

from PySide6.QtWidgets import QApplication

from nd_route_finder.analysis.track_analyzer import TrackAnalyzer
from nd_route_finder.ui.multi_waypoint_main_window import MultiWaypointMainWindow
from nd_route_finder.gpx.gpx_track_reader import GpxTrackReader


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    path = project_root / "gpx/graz_ragnitzstrasse_62b_to_semriacherstrasse_100_direct.gpx"
    if not path.is_file():
        raise FileNotFoundError(path)
    app = QApplication.instance() or QApplication([])
    window = MultiWaypointMainWindow()
    window._map_start_selected(47.077531, 15.4776239)
    window._map_point_selected(47.175987, 15.362206, "Semriacherstraße 100, 8102")
    window._route_mode.setCurrentIndex(1)  # Direct
    window._route_preference.setCurrentIndex(1)  # Shortest
    window._distance.setValue(40.0)
    window._max_grade.setValue(20.0)
    window._output_path.setText(str(path))
    window._last_generated_output = path

    track = GpxTrackReader().read(path)
    track = TrackAnalyzer().analyze(track)
    window._prepare_map_builder()
    window._load_map_html(window._map_builder.build_routes([], track))
    window._show_profiles(track)
    window._status.setText(
        f"BRouter cycling GPX loaded: {track.distance_m / 1000:.2f} km. "
        "Independent Overpass obstacle checks unavailable; verify local conditions."
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
