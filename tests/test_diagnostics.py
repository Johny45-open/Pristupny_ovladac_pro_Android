"""Testy Qt-free jádra ovladac.diagnostics."""

from __future__ import annotations

import unittest

from ovladac.adb import NoDeviceError, parse_devices_output
from ovladac.diagnostics import (
    DiagnosticCancelled,
    scan_devices,
    select_device,
)
from tests._helpers import make_client, reset_run, RUN


DEVICES_OUT = (
    "List of devices attached\n"
    "KBYD9DJJJRVCVCI7    device product:aristotle model:2306EPN60G "
    "device:aristotle transport_id:1\n"
)


class ScanTest(unittest.TestCase):
    def test_single_ready_autoselected(self) -> None:
        client = make_client([DEVICES_OUT])
        sel = scan_devices(client)
        self.assertEqual(sel.reason, "single")
        self.assertEqual(sel.selected_serial, "KBYD9DJJJRVCVCI7")
        self.assertEqual(len(sel.devices), 1)

    def test_multiple_never_autoselect(self) -> None:
        out = "List of devices attached\nAAA    device\nBBB    device\n"
        client = make_client([out])
        sel = scan_devices(client)
        self.assertEqual(sel.reason, "multiple")
        self.assertIsNone(sel.selected_serial)

    def test_none_when_empty(self) -> None:
        client = make_client(["List of devices attached\n"])
        sel = scan_devices(client)
        self.assertEqual(sel.reason, "none")
        self.assertIsNone(sel.selected_serial)

    def test_offline_not_ready(self) -> None:
        out = "List of devices attached\nAAA    offline\nBBB    device\n"
        client = make_client([out])
        sel = scan_devices(client)
        # jediné ready je BBB, ale AAA zůstává v seznamu
        self.assertEqual(sel.reason, "single")
        self.assertEqual(sel.selected_serial, "BBB")
        self.assertEqual(len(sel.devices), 2)

    def test_only_offline_means_none(self) -> None:
        out = "List of devices attached\nAAA    offline\nAAA    unauthorized\n"
        client = make_client([out])
        sel = scan_devices(client)
        self.assertEqual(sel.reason, "none")


class SelectTest(unittest.TestCase):
    def test_explicit_ready(self) -> None:
        client = make_client([DEVICES_OUT], serial="KBYD9DJJJRVCVCI7")
        dev = select_device(client, "KBYD9DJJJRVCVCI7")
        self.assertEqual(dev.serial, "KBYD9DJJJRVCVCI7")
        self.assertTrue(dev.is_ready)

    def test_offline_raises(self) -> None:
        out = "List of devices attached\nAAA    offline\n"
        client = make_client([out], serial="AAA")
        with self.assertRaises(NoDeviceError):
            select_device(client, "AAA")

    def test_missing_raises(self) -> None:
        client = make_client([DEVICES_OUT], serial="NOPE")
        with self.assertRaises(NoDeviceError):
            select_device(client, "NOPE")


class CancelTest(unittest.TestCase):
    def test_cancel_before_first_step(self) -> None:
        from ovladac.diagnostics import collect_diagnostic

        client = make_client([DEVICES_OUT])

        def cancel() -> None:
            raise DiagnosticCancelled()

        with self.assertRaises(DiagnosticCancelled):
            collect_diagnostic(client, cancel_check=cancel)


class ReadOnlyTest(unittest.TestCase):
    def test_scan_commands_are_whitelisted(self) -> None:
        from ovladac.safety import assert_readonly

        reset_run()
        client = make_client([DEVICES_OUT])
        scan_devices(client)
        self.assertTrue(RUN)
        for argv in RUN:
            assert_readonly(list(argv))

    def test_parse_devices_output(self) -> None:
        devices = parse_devices_output(DEVICES_OUT)
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].state, "device")


if __name__ == "__main__":
    unittest.main()
