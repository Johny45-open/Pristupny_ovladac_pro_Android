"""Pracovní objekt (QObject) pro ADB úlohy ve sdílené QThread.

Každá úloha si vytvoří SVĚŽÍ AdbClient (explicitní serial), takže AdbClient
zůstává jednovláknový. Výsledky putují do GUI výhradně signály.

Kooperativní přerušení: request_cancel() zakáže další ADB příkazy;
běžící subprocess se dokončí, nebo vyprší timeout AdbClient.
Žádný QThread.terminate(), žádné blokující wait() na pevný čas.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from ..adb import (
    AdbClient,
    AdbError,
    AdbTimeoutError,
    NoDeviceError,
)
from ..safety import SafetyViolationError
from ..diagnostics import (
    DiagnosticCancelled,
    collect_diagnostic,
    scan_devices,
)


class AdbWorker(QObject):
    started = pyqtSignal()
    scan_done = pyqtSignal(object)      # DeviceSelection
    diagnostic_done = pyqtSignal(object)  # DiagnosticReport
    failed = pyqtSignal(str, str)       # (hláška, druh)

    def __init__(
        self,
        adb_path: str = "adb",
        timeout: float = 15.0,
        client_factory: "Callable[[str | None], AdbClient] | None" = None,
    ) -> None:
        super().__init__()
        self._adb_path = adb_path
        self._timeout = timeout
        self._cancel = False
        self._client_factory = client_factory

    def _make_client(self, serial: str | None = None) -> AdbClient:
        """Žádná úloha nesdílí klienta – každá dostane vlastní instanci."""
        if self._client_factory is not None:
            return self._client_factory(serial)
        return AdbClient(
            adb_path=self._adb_path, serial=serial, timeout=self._timeout
        )

    # ---- požadavek na zrušení (volá MainWindow, GUI vlákno) ----

    def request_cancel(self) -> None:
        """Zakáže další ADB příkazy. Aktuálně běžící se dokončí / dopadne timeoutem."""
        self._cancel = True

    def _reset_cancel(self) -> None:
        self._cancel = False

    def _cancel_check(self) -> None:
        if self._cancel or QThread.currentThread().isInterruptionRequested():
            raise DiagnosticCancelled("Požadavek na zrušení.")

    # ---- úlohy (spouštějí se ve QThread) ----

    @pyqtSlot()
    def do_scan(self) -> None:
        self._reset_cancel()
        self.started.emit()
        client = self._make_client()
        try:
            selection = scan_devices(client, cancel_check=self._cancel_check)
        except DiagnosticCancelled:
            self._reset_cancel()
            self.failed.emit("Zrušeno.", "cancelled")
            return
        except SafetyViolationError as exc:
            self.failed.emit(f"Odmítnuto bezpečnostním whitelistem: {exc}", "adb")
            return
        except AdbError as exc:
            kind = "timeout" if isinstance(exc, AdbTimeoutError) else "adb"
            self.failed.emit(str(exc), kind)
            return
        self.scan_done.emit(selection)

    @pyqtSlot(str)
    def do_diagnostic(self, serial: str) -> None:
        self._reset_cancel()
        self.started.emit()
        # Svěží klient s EXPLICITNÍM serial – nikdy ensure_device().
        client = self._make_client(serial)
        try:
            report = collect_diagnostic(client, cancel_check=self._cancel_check)
        except DiagnosticCancelled:
            self._reset_cancel()
            self.failed.emit("Zrušeno.", "cancelled")
            return
        except NoDeviceError as exc:
            self.failed.emit(str(exc), "no_device")
            return
        except SafetyViolationError as exc:
            self.failed.emit(f"Odmítnuto bezpečnostním whitelistem: {exc}", "adb")
            return
        except AdbError as exc:
            kind = "timeout" if isinstance(exc, AdbTimeoutError) else "adb"
            self.failed.emit(str(exc), kind)
            return
        self.diagnostic_done.emit(report)
