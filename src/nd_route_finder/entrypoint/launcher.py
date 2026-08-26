import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from nd_route_finder.ui.main_window import MainWindow


class Launcher:
    @staticmethod
    def run() -> int:
        application = QApplication.instance() or QApplication(sys.argv)

        project_root = Path(__file__).resolve().parents[3]
        icon_path = project_root / "assets" / "app_icon.svg"
        icon = QIcon(str(icon_path)) if icon_path.is_file() else QIcon()
        if not icon.isNull():
            application.setWindowIcon(icon)

        window = MainWindow()
        if not icon.isNull():
            window.setWindowIcon(icon)
        window.show()
        return application.exec()


if __name__ == "__main__":
    raise SystemExit(Launcher.run())
