"""Vstupní bod GUI – python main.py"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        print(
            "GUI vyžaduje PyQt6. Nainstaluj s GUI závislostí:\n"
            "    pip install .[gui]\n"
        )
        return 1

    from ovladac.qtapp.main_window import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
