"""Testy ADB vrstvy (ovladac.adb) – běží bez připojeného zařízení."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from ovladac.adb import (
    AdbClient,
    AdbError,
    AdbTimeoutError,
    AmbiguousDeviceError,
    NoDeviceError,
    default_runner,
    parse_devices_output,
    parse_getprop_output,
    parse_pm_list_output,
)
from ovladac.safety import SafetyViolationError

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeRunner:
    """Runner, který nic nespouští – jen zaznamená volání a vrací připravený výstup."""

    def __init__(self, response: str = "") -> None:
        self.response = response
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def __call__(self, argv, timeout: float) -> str:
        self.calls.append((tuple(argv), timeout))
        return self.response


class TestParsers(unittest.TestCase):
    def test_parse_devices_output_real_fixture(self):
        devices = parse_devices_output(load_fixture("devices_l.txt"))
        self.assertEqual(len(devices), 1)
        device = devices[0]
        self.assertEqual(device.serial, "KBYD9DJJJRVCVCI7")
        self.assertEqual(device.state, "device")
        self.assertTrue(device.is_ready)
        self.assertEqual(device.extras.get("model"), "2306EPN60G")
        self.assertEqual(device.extras.get("device"), "aristotle")

    def test_parse_devices_output_states(self):
        text = (
            "List of devices attached\n"
            "SERIAL1\toffline\n"
            "SERIAL2\tunauthorized usb:1-1\n"
            "* daemon started successfully\n"
        )
        devices = parse_devices_output(text)
        self.assertEqual([d.state for d in devices], ["offline", "unauthorized"])
        self.assertFalse(any(d.is_ready for d in devices))

    def test_parse_getprop_output_real_fixture(self):
        props = parse_getprop_output(load_fixture("getprop.txt"))
        self.assertEqual(props["ro.product.model"], "2306EPN60G")
        self.assertEqual(props["ro.build.version.release"], "16")
        self.assertEqual(props["ro.build.version.sdk"], "36")
        self.assertEqual(props["ro.build.version.incremental"], "OS3.0.4.0.WMFEUXM")
        self.assertEqual(len(props), 12)

    def test_parse_pm_list_output(self):
        text = "package:com.b\npackage:com.a\npackage:com.a\n"
        self.assertEqual(parse_pm_list_output(text), ["com.a", "com.b"])


class TestClientWithFakeRunner(unittest.TestCase):
    def test_settings_builds_correct_argv(self):
        runner = FakeRunner(response="1\n")
        client = AdbClient(serial="ABC123", runner=runner)
        result = client.settings("secure", "accessibility_enabled")
        self.assertEqual(result, "1")
        self.assertEqual(len(runner.calls), 1)
        argv, timeout = runner.calls[0]
        self.assertEqual(
            argv,
            ("adb", "-s", "ABC123", "shell", "settings", "get",
             "secure", "accessibility_enabled"),
        )
        self.assertEqual(timeout, 15.0)

    def test_state_changing_command_rejected_before_runner_is_called(self):
        runner = FakeRunner(response="nemelo by se volat")
        client = AdbClient(serial="ABC123", runner=runner)
        with self.assertRaises(SafetyViolationError):
            client.run_readonly("shell", "settings", "put", "secure", "x", "1")
        self.assertEqual(runner.calls, [], "Zakázaný příkaz se nesmí dostat k runneru.")

    def test_history_records_only_approved_commands(self):
        runner = FakeRunner(response="")
        client = AdbClient(serial="ABC123", runner=runner)
        client.settings("secure", "accessibility_enabled")
        client.dumpsys("accessibility")
        with self.assertRaises(SafetyViolationError):
            client.run_readonly("shell", "input", "tap", "1", "1")
        self.assertEqual(len(client.history), 2)
        self.assertTrue(all("input" not in " ".join(cmd) for cmd in client.history))

    def test_getprop_returns_parsed_dict(self):
        runner = FakeRunner(response=load_fixture("getprop.txt"))
        client = AdbClient(serial="ABC123", runner=runner)
        props = client.getprop()
        self.assertEqual(props["ro.product.model"], "2306EPN60G")
        argv, _ = runner.calls[0]
        self.assertEqual(argv, ("adb", "-s", "ABC123", "shell", "getprop"))

    def test_getprop_value(self):
        runner = FakeRunner(response="2306EPN60G\n")
        client = AdbClient(serial="ABC123", runner=runner)
        self.assertEqual(client.getprop_value("ro.product.model"), "2306EPN60G")


class TestDeviceSelection(unittest.TestCase):
    def _client(self, response: str) -> AdbClient:
        return AdbClient(runner=FakeRunner(response=response))

    def test_pick_single_ready_device(self):
        client = self._client(load_fixture("devices_l.txt"))
        device = client.pick_device()
        self.assertEqual(device.serial, "KBYD9DJJJRVCVCI7")

    def test_ensure_device_sets_serial(self):
        client = self._client(load_fixture("devices_l.txt"))
        device = client.ensure_device()
        self.assertEqual(client.serial, device.serial)

    def test_no_device_raises(self):
        client = self._client("List of devices attached\n")
        with self.assertRaises(NoDeviceError):
            client.pick_device()

    def test_unauthorized_device_raises(self):
        client = self._client(
            "List of devices attached\nSERIAL1\tunauthorized\n"
        )
        with self.assertRaises(NoDeviceError):
            client.pick_device()

    def test_multiple_devices_raise(self):
        client = self._client(
            "List of devices attached\nA\tdevice\nB\tdevice\n"
        )
        with self.assertRaises(AmbiguousDeviceError):
            client.pick_device()

    def test_ensure_device_with_explicit_serial_missing_raises(self):
        client = AdbClient(
            serial="NEEXISTUJE",
            runner=FakeRunner(response=load_fixture("devices_l.txt")),
        )
        with self.assertRaises(NoDeviceError):
            client.ensure_device()


class TestDefaultRunner(unittest.TestCase):
    """Testy skutečného subprocess runneru (na pythonu, ne na telefonu)."""

    def test_timeout_raises(self):
        with self.assertRaises(AdbTimeoutError):
            default_runner(
                [sys.executable, "-c", "import time; time.sleep(5)"],
                timeout=0.3,
            )

    def test_nonzero_exit_raises_adb_error(self):
        with self.assertRaises(AdbError) as ctx:
            default_runner(
                [sys.executable, "-c", "import sys; sys.exit(3)"],
                timeout=10,
            )
        self.assertIn("3", str(ctx.exception))

    def test_utf8_output_is_decoded(self):
        code = "import sys; sys.stdout.buffer.write('Přístroj: café'.encode('utf-8'))"
        output = default_runner([sys.executable, "-c", code], timeout=10)
        self.assertEqual(output, "Přístroj: café")

    def test_missing_binary_raises(self):
        from ovladac.adb import AdbNotFoundError

        with self.assertRaises(AdbNotFoundError):
            default_runner(["neexistujici_program_xyz", "arg"], timeout=5)


if __name__ == "__main__":
    unittest.main()
