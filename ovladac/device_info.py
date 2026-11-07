"""Identifikace zařízení z výstupů ADB – jen čtení."""

from __future__ import annotations

from dataclasses import dataclass

from .adb import Device, parse_getprop_output

# Vlastnosti, které pro nás mají význam (nic víc z getprop nečteme).
_MODEL = "ro.product.model"
_BRAND = "ro.product.brand"
_MANUFACTURER = "ro.product.manufacturer"
_DEVICE = "ro.product.device"
_RELEASE = "ro.build.version.release"
_SDK = "ro.build.version.sdk"
_DISPLAY_ID = "ro.build.display.id"
_INCREMENTAL = "ro.build.version.incremental"
_MIUI_VERSION = "ro.miui.ui.version.name"
_ABI = "ro.product.cpu.abi"
_SECURITY_PATCH = "ro.build.version.security_patch"
_DEBUGGABLE = "ro.debuggable"


@dataclass(frozen=True)
class DeviceInfo:
    """Základní identifikace připojeného zařízení."""

    serial: str
    state: str
    model: str | None
    brand: str | None
    manufacturer: str | None
    device: str | None
    android_release: str | None
    sdk_int: int | None
    display_id: str | None
    incremental: str | None
    miui_version: str | None
    abi: str | None
    security_patch: str | None
    debuggable: bool | None

    @property
    def android_major(self) -> int | None:
        if not self.android_release:
            return None
        try:
            return int(self.android_release.split(".", 1)[0])
        except ValueError:
            return None

    @property
    def is_hyperos(self) -> bool:
        """HyperOS poznáme podle incrementálu (začíná „OS“)."""
        return bool(self.incremental and self.incremental.startswith("OS"))


def build_device_info(device: Device, props: dict[str, str]) -> DeviceInfo:
    """Sestaví DeviceInfo z Device + slovníku z getprop."""
    sdk_raw = props.get(_SDK)
    debuggable_raw = props.get(_DEBUGGABLE)

    sdk_int: int | None = None
    if sdk_raw is not None:
        try:
            sdk_int = int(sdk_raw)
        except ValueError:
            sdk_int = None

    debuggable: bool | None = None
    if debuggable_raw is not None:
        debuggable = debuggable_raw == "1"

    return DeviceInfo(
        serial=device.serial,
        state=device.state,
        model=props.get(_MODEL),
        brand=props.get(_BRAND),
        manufacturer=props.get(_MANUFACTURER),
        device=props.get(_DEVICE),
        android_release=props.get(_RELEASE),
        sdk_int=sdk_int,
        display_id=props.get(_DISPLAY_ID),
        incremental=props.get(_INCREMENTAL),
        miui_version=props.get(_MIUI_VERSION),
        abi=props.get(_ABI),
        security_patch=props.get(_SECURITY_PATCH),
        debuggable=debuggable,
    )


__all__ = ["DeviceInfo", "build_device_info", "parse_getprop_output"]
