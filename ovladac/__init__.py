"""Přístupný vzdálený ovladač Androidu – ADB jádro (Etapa 1).

Modul poskytuje výhradně READ-ONLY přístup k zařízení přes ADB:
detekci zařízení, čtení vlastností, čtení nastavení přístupnosti
a čtení výpisu dumpsys. Žádná funkce modulu nemění stav telefonu.
"""

from .accessibility import (
    READER_COMPONENT,
    SELECT_TO_SPEAK_COMPONENT,
    TALKBACK_COMPONENT,
    TALKBACK_PACKAGE,
    AccessibilityState,
    collect_state,
    is_package_installed,
    parse_bool_setting,
    parse_dumpsys_accessibility,
    parse_enabled_services,
)
from .adb import (
    AdbClient,
    AdbError,
    AdbNotFoundError,
    AdbTimeoutError,
    AmbiguousDeviceError,
    Device,
    NoDeviceError,
    default_runner,
    parse_devices_output,
    parse_getprop_output,
    parse_pm_list_output,
)
from .device_info import DeviceInfo, build_device_info
from .diagnostics import (
    READER_PACKAGE as DIAG_READER_PACKAGE,
    DeviceSelection,
    DiagnosticCancelled,
    DiagnosticReport,
    TALKBACK_PACKAGE as DIAG_TALKBACK_PACKAGE,
    WATCHED_PACKAGES,
    collect_diagnostic,
    scan_devices,
    select_device,
)
from .safety import SafetyViolationError, assert_readonly

__all__ = [
    "AccessibilityState",
    "AdbClient",
    "AdbError",
    "AdbNotFoundError",
    "AdbTimeoutError",
    "AmbiguousDeviceError",
    "DeviceInfo",
    "Device",
    "DeviceSelection",
    "DiagnosticCancelled",
    "DiagnosticReport",
    "NoDeviceError",
    "READER_COMPONENT",
    "SELECT_TO_SPEAK_COMPONENT",
    "SafetyViolationError",
    "TALKBACK_COMPONENT",
    "TALKBACK_PACKAGE",
    "WATCHED_PACKAGES",
    "assert_readonly",
    "build_device_info",
    "collect_diagnostic",
    "collect_state",
    "default_runner",
    "is_package_installed",
    "parse_bool_setting",
    "parse_devices_output",
    "parse_dumpsys_accessibility",
    "parse_enabled_services",
    "parse_getprop_output",
    "parse_pm_list_output",
    "scan_devices",
    "select_device",
]
