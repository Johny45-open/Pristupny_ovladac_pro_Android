"""Testovací pomocníci: skriptování ADB, pumpování Qt event loop, časování."""

from __future__ import annotations

import re
import time
from typing import Any

# Rejstřík: co přesně se spustilo (pro read-only ověření)
RUN: list[tuple[str, ...]] = []


class FakeRunner:
    """Nahrádí skutečný adb spuštěním: vrací přípravené texty / výjimku.

    `script` je seznam – každý položka je str (stdout) nebo
    instance výjimky. Každé volání `fake_runner` spotřebuje další položku;
    po vyčerpání vrací poslední hodnotu (nebo vyhodí StopIteration).
    """

    def __init__(self, script: list[Any]) -> None:
        self.script = script
        self.idx = 0

    def __call__(self, argv, timeout: float) -> str:
        RUN.append(tuple(argv))
        if not self.script:
            raise AssertionError(f"FakeRunner vyčerpán, přesto volán: {argv}")
        entry = self.script[min(self.idx, len(self.script) - 1)]
        self.idx += 1
        if isinstance(entry, Exception):
            raise entry
        return str(entry)


def make_client(script: list[Any], **kwargs: Any):
    """Vytvoří AdbClient s přepnutím runneru na fake."""
    from ovladac.adb import AdbClient
    return AdbClient(runner=FakeRunner(script), **kwargs)


def pump(app, ms: float = 200.0) -> None:
    """Pumpuje Qt event loop po malých krocích, celkem `ms` ms."""
    import os
    from PyQt6.QtCore import QTimer
    app.processEvents()
    deadline = time.monotonic() + ms / 1000.0
    step = 0.02
    while time.monotonic() < deadline:
        QTimer.singleShot(20, app.processEvents)
        time.sleep(step)
        app.processEvents()
    app.processEvents()


def wait_for(predicate, timeout_ms: int = 4000) -> bool:
    """Čeká s pumpováním loopu, dokud predicate() není True."""
    import time
    from PyQt6.QtCore import QTimer

    app = __import__("PyQt6.QtWidgets", fromlist=["QApplication"]).QApplication.instance()
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        if predicate():
            return True
        QTimer.singleShot(10, app.processEvents)
        time.sleep(0.01)
        app.processEvents()
    return predicate()


def reset_run() -> None:
    RUN.clear()
