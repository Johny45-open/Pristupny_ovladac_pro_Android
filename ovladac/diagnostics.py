"""Společné diagnostické jádro – čisté Python bez Qt.

Používají ho jak GUI (ovladac.qtapp.worker), tak CLI
(scripts/run_diagnostics.py). Veškeré ADB operace běží výhradně
přes AdbClient.run_readonly, takže whitelist read-only platí vždy.

Kontakováním diagnostika se ukončí mezi jednotlivými ADB příkazy;
běžící subprocess se dokončí, nebo vyprší timeout AdbClient.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .adb import (
    AmbiguousDeviceError,
    AdbClient,
    Device,
    NoDeviceError,
)
from .accessibility import AccessibilityState, collect_state
from .device_info import DeviceInfo, build_device_info

# Kontrola úkazu: vrátí, má-li se diagnostika zastavit.
CancelCheck = Callable[[], None]


class DiagnosticCancelled(RuntimeError):
    """Požadavek na zrušení diagnostiky (ne klasická chyba)."""


# Balíčky, které GUI sleduje (výběr dle Etapy 0).
TALKBACK_PACKAGE = "com.google.android.marvin.talkback"
READER_PACKAGE = "com.google.android.accessibility.reader"
WATCHED_PACKAGES: tuple[str, ...] = (
    TALKBACK_PACKAGE,
    READER_PACKAGE,
    "com.nirenr.talkman",
    "fyi.quin.backtalk",
    "eu.appsuite.talkforward",
    "com.google.android.apps.accessibility.reveal",
)


@dataclass(frozen=True)
class DeviceSelection:
    """Výsledek skenu zařízení.

    selected_serial je nastaven pouze tehdy, je-li připravené
    (state == "device") přesně jedno zařízení.
    """

    devices: tuple[Device, ...]
    selected_serial: str | None
    reason: str  # "single", "multiple" nebo "none"

    @property
    def ready(self) -> tuple[Device, ...]:
        return tuple(d for d in self.devices if d.is_ready)


def _maybe_cancel(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None:
        cancel_check()


def scan_devices(client: AdbClient, cancel_check: CancelCheck | None = None) -> DeviceSelection:
    """Načte `adb devices -l` a rozhodne o automatickém výběru."""
    _maybe_cancel(cancel_check)
    devices = client.devices()
    _maybe_cancel(cancel_check)
    ready = [d for d in devices if d.is_ready]
    if len(ready) == 1:
        return DeviceSelection(tuple(devices), ready[0].serial, "single")
    if len(ready) > 1:
        return DeviceSelection(tuple(devices), None, "multiple")
    return DeviceSelection(tuple(devices), None, "none")


def select_device(client: AdbClient, serial: str) -> Device:
    """Pouze explicitně zvolené zařízení v stavu „device“.

    Offline / unauthorized zařízení se nediagnostikují – vyhodí NoDeviceError.
    """
    for device in client.devices():
        if device.serial == serial:
            if not device.is_ready:
                raise NoDeviceError(
                    f"Zařízení {serial} není v stavu 'device' (skutečný stav: {device.state})."
                )
            return device
    raise NoDeviceError(f"Zařízení {serial} v seznamu připojených zařízení nenalezeno.")


@dataclass(frozen=True)
class DiagnosticReport:
    """Koncečný výsledek diagnostiky; GUI i CLI ho jen zobrazi."""

    device: Device
    device_info: DeviceInfo
    packages: tuple[str, ...]
    accessibility: AccessibilityState

    # ---- přehled pro jednotlivé čtečky ----

    @property
    def talkback_installed(self) -> bool:
        return TALKBACK_PACKAGE in self.packages

    @property
    def talkback_enabled(self) -> bool:
        return self.accessibility.talkback_enabled

    @property
    def talkback_active(self) -> bool:
        return self.accessibility.talkback_active

    @property
    def talkback_crashed(self) -> bool:
        return self.accessibility.talkback_crashed

    @property
    def select_to_speak_enabled(self) -> bool:
        return self.accessibility.select_to_speak_enabled

    @property
    def select_to_speak_crashed(self) -> bool:
        return self.accessibility.select_to_speak_crashed

    @property
    def reader_enabled(self) -> bool:
        return self.accessibility.reader_service_enabled

    @property
    def reader_crashed(self) -> bool:
        return self.accessibility.reader_service_crashed

    @property
    def touch_exploration(self) -> bool | None:
        return self.accessibility.touch_exploration_enabled

    @property
    def installed_service_count(self) -> int | None:
        return self.accessibility.installed_service_count


def collect_diagnostic(client: AdbClient, cancel_check: CancelCheck | None = None) -> DiagnosticReport:
    """Celá diagnostika jednoho zvoleného zařízení.

    Každý krok je předchází kontrolou zrušení; běžící subprocess se
    dokončí, nebo vyprší timeout AdbClient.
    """
    _maybe_cancel(cancel_check)
    device = select_device(client, client.serial or "")
    _maybe_cancel(cancel_check)
    props = client.getprop()
    _maybe_cancel(cancel_check)
    packages = client.pm_list_packages()
    _maybe_cancel(cancel_check)
    accessibility = collect_state(client)
    _maybe_cancel(cancel_check)

    return DiagnosticReport(
        device=device,
        device_info=build_device_info(device, props),
        packages=tuple(packages),
        accessibility=accessibility,
    )


__all__ = [
    "CancelCheck",
    "DeviceSelection",
    "DiagnosticCancelled",
    "DiagnosticReport",
    "READER_PACKAGE",
    "TALKBACK_PACKAGE",
    "WATCHED_PACKAGES",
    "collect_diagnostic",
    "scan_devices",
    "select_device",
]
