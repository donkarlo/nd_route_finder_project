import sys

from PySide6.QtWidgets import QApplication

from nd_route_finder.ui.main_window import MainWindow


class Launcher:
    @staticmethod
    def run() -> int:
        application = QApplication.instance() or QApplication(sys.argv)
        window = MainWindow()
        window.show()
        return application.exec()


if __name__ == "__main__":
    raise SystemExit(Launcher.run())
