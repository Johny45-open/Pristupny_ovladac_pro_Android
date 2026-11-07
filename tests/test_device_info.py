"""Testy identifikace zařízení (ovladac.device_info)."""

from __future__ import annotations

import unittest
from pathlib import Path

from ovladac.adb import Device, parse_devices_output, parse_getprop_output
from ovladac.device_info import build_device_info

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class TestDeviceInfo(unittest.TestCase):
    def setUp(self):
        self.device = parse_devices_output(load_fixture("devices_l.txt"))[0]
        self.props = parse_getprop_output(load_fixture("getprop.txt"))
        self.info = build_device_info(self.device, self.props)

    def test_serial_and_state(self):
        self.assertEqual(self.info.serial, "KBYD9DJJJRVCVCI7")
        self.assertEqual(self.info.state, "device")

    def test_identity(self):
        self.assertEqual(self.info.model, "2306EPN60G")
        self.assertEqual(self.info.brand, "Xiaomi")
        self.assertEqual(self.info.manufacturer, "Xiaomi")
        self.assertEqual(self.info.device, "aristotle")
        self.assertEqual(self.info.abi, "arm64-v8a")

    def test_android_version(self):
        # Skutečný výstup zařízení: Android 16 / SDK 36.
        self.assertEqual(self.info.android_release, "16")
        self.assertEqual(self.info.sdk_int, 36)
        self.assertEqual(self.info.android_major, 16)

    def test_hyperos_version(self):
        self.assertEqual(self.info.incremental, "OS3.0.4.0.WMFEUXM")
        self.assertEqual(self.info.miui_version, "V816")
        self.assertTrue(self.info.is_hyperos)

    def test_display_and_security_patch(self):
        self.assertEqual(self.info.display_id, "BP2A.250605.031.A3")
        self.assertEqual(self.info.security_patch, "2026-08-01")

    def test_debuggable_is_false_for_retail_rom(self):
        self.assertIs(self.info.debuggable, False)

    def test_missing_properties_are_none(self):
        info = build_device_info(Device(serial="X", state="device"), {})
        self.assertIsNone(info.model)
        self.assertIsNone(info.sdk_int)
        self.assertIsNone(info.android_major)
        self.assertFalse(info.is_hyperos)
        self.assertIsNone(info.debuggable)

    def test_malformed_sdk_does_not_crash(self):
        info = build_device_info(
            Device(serial="X", state="device"),
            {"ro.build.version.sdk": "abc", "ro.debuggable": "0"},
        )
        self.assertIsNone(info.sdk_int)
        self.assertIs(info.debuggable, False)


if __name__ == "__main__":
    unittest.main()
