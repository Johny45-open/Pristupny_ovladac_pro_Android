"""Testy AdbWorker (ovladac.qtapp.worker) – bez skutečného adb.

Signály ověřujeme přímým voláním slotů (bez QThread); vlákno a closeEvent
se testují v test_main_window.py.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from ovladac.adb import AdbClient, AdbError, AdbTimeoutError
from ovladac.qtapp.worker import AdbWorker

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


PACKAGES = (
    "package:com.google.android.marvin.talkback\n"
    "package:com.google.android.accessibility.reader\n"
    "package:com.example.other\n"
)


class RoutingRunner:
    """Vrací fixture dle typu příkazu; zaznamenává volání."""

    def __init__(self, on_call=None) -> None:
        self.calls: list[tuple[str, ...]] = []
        self._on_call = on_call

    def __call__(self, argv, timeout: float) -> str:
        argv = tuple(argv)
        self.calls.append(argv)
        if self._on_call is not None:
            self._on_call(argv)
        joined = " ".join(argv)
        if "devices" in argv:
            return _fixture("devices_l.txt")
        if "getprop" in argv:
            return _fixture("getprop.txt")
        if "pm list packages" in joined:
            return PACKAGES
        if "settings get secure accessibility_enabled" in joined:
            return _fixture("settings_accessibility_enabled.txt")
        if "settings get secure touch_exploration_enabled" in joined:
            return _fixture("settings_touch_exploration.txt")
        if "settings get secure enabled_accessibility_services" in joined:
            return _fixture("settings_enabled_services.txt")
        if "dumpsys accessibility" in joined:
            return _fixture("dumpsys_accessibility.txt")
        raise AssertionError(f"Neočekávaný příkaz: {argv}")


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class WorkerTest(unittest.TestCase):
    def setUp(self) -> None:
        _app()
        self.runner = RoutingRunner()
        self.made: list[str | None] = []

    def _factory(self, runner=None):
        runner = runner if runner is not None else self.runner

        def factory(serial: str | None) -> AdbClient:
            self.made.append(serial)
            return AdbClient(serial=serial, runner=runner)

        return factory

    def test_scan_emits_selection(self) -> None:
        worker = AdbWorker(client_factory=self._factory())
        results: list = []
        worker.scan_done.connect(results.append)
        worker.do_scan()
        self.assertEqual(len(results), 1)
        selection = results[0]
        self.assertEqual(selection.reason, "single")
        self.assertEqual(selection.selected_serial, "KBYD9DJJJRVCVCI7")
        self.assertEqual(self.made, [None], "scan nemá serial")

    def test_diagnostic_uses_explicit_serial_and_fresh_client(self) -> None:
        worker = AdbWorker(client_factory=self._factory())
        results: list = []
        worker.diagnostic_done.connect(results.append)
        worker.do_diagnostic("KBYD9DJJJRVCVCI7")
        self.assertEqual(len(results), 1)
        report = results[0]
        self.assertEqual(report.device.serial, "KBYD9DJJJRVCVCI7")
        self.assertTrue(report.talkback_installed)
        self.assertEqual(self.made, ["KBYD9DJJJRVCVCI7"])
        # žádný příkaz nesmí být mimo whitelist – ověří safety při volání

    def test_started_emitted_before_done(self) -> None:
        worker = AdbWorker(client_factory=self._factory())
        order: list[str] = []
        worker.started.connect(lambda: order.append("started"))
        worker.scan_done.connect(lambda _s: order.append("done"))
        worker.do_scan()
        self.assertEqual(order, ["started", "done"])

    def test_adb_error_maps_to_failed(self) -> None:
        def factory(serial: str | None) -> AdbClient:
            def runner(argv, timeout):
                raise AdbError("boom")

            return AdbClient(serial=serial, runner=runner)

        worker = AdbWorker(client_factory=factory)
        failed: list[tuple[str, str]] = []
        worker.failed.connect(lambda m, k: failed.append((m, k)))
        worker.do_scan()
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0][1], "adb")

    def test_timeout_maps_to_timeout_kind(self) -> None:
        def factory(serial: str | None) -> AdbClient:
            def runner(argv, timeout):
                raise AdbTimeoutError("přetečení")

            return AdbClient(serial=serial, runner=runner)

        worker = AdbWorker(client_factory=factory)
        failed: list[tuple[str, str]] = []
        worker.failed.connect(lambda m, k: failed.append((m, k)))
        worker.do_scan()
        self.assertEqual(failed[0][1], "timeout")

    def test_no_device_maps_to_no_device(self) -> None:
        out = "List of devices attached\nAAA    offline\n"
        worker = AdbWorker(client_factory=self._factory(_ConstRunner(out)))
        failed: list[tuple[str, str]] = []
        worker.failed.connect(lambda m, k: failed.append((m, k)))
        worker.do_diagnostic("AAA")
        self.assertEqual(failed[0][1], "no_device")

    def test_cancel_between_commands(self) -> None:
        """Po prvním příkazu si worker sám vyžádá zrušení."""
        worker_holder: dict[str, AdbWorker] = {}

        def on_call(argv):
            if len(worker_holder["runner"].calls) == 1:
                worker_holder["worker"].request_cancel()

        runner = RoutingRunner(on_call=on_call)
        worker_holder["runner"] = runner
        worker = AdbWorker(client_factory=self._factory(runner))
        worker_holder["worker"] = worker

        failed: list[tuple[str, str]] = []
        done: list = []
        worker.failed.connect(lambda m, k: failed.append((m, k)))
        worker.diagnostic_done.connect(done.append)
        worker.do_diagnostic("KBYD9DJJJRVCVCI7")
        self.assertEqual(done, [])
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0][1], "cancelled")


class _ConstRunner:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv, timeout: float) -> str:
        self.calls.append(tuple(argv))
        return self.text


if __name__ == "__main__":
    unittest.main()
