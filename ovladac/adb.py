"""Komunikační vrstva ADB – výhradně read-only.

Všechny příkazy prochází přes assert_readonly() ze modulu safety, takže
zakázaný příkaz se nikdy nedostane k subprocess. Pro testování lze
předat vlastní runner (funkce argv -> výstup), takže unit testy běží
bez připojeného zařízení.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from .safety import assert_readonly

# Typ pro funkci, která skutečně spouští proces a vrací výstup.
Runner = Callable[[Sequence[str], float], str]


class AdbError(RuntimeError):
    """Obecná chyba ADB (nenalezená binárka, nenulový návrat, ...)."""


class AdbTimeoutError(AdbError):
    """Příkaz překročil časový limit."""


class AdbNotFoundError(AdbError):
    """Binárka adb nebyla nalezena."""


class NoDeviceError(AdbError):
    """Žádné připravené zařízení (žádné, offline nebo unauthorized)."""


class AmbiguousDeviceError(AdbError):
    """Připojeno více zařízení a nebylo vybráno konkrétní (-s)."""


@dataclass(frozen=True)
class Device:
    """Jeden řádek z výstupu `adb devices -l`."""

    serial: str
    state: str
    extras: dict[str, str] = field(default_factory=dict)

    @property
    def is_ready(self) -> bool:
        return self.state == "device"


def default_runner(argv: Sequence[str], timeout: float) -> str:
    """Výchozí runner: spustí proces, dekóduje UTF-8 a řídí se návratovou hodnotou."""
    try:
        proc = subprocess.run(list(argv), capture_output=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise AdbNotFoundError(f"ADB nebyl nalezen: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise AdbTimeoutError(
            f"Příkaz překročil časový limit {timeout} s: {' '.join(argv)}"
        ) from exc

    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = proc.stderr.decode("utf-8", errors="replace")

    if proc.returncode != 0:
        detail = stderr.strip() or stdout.strip()
        raise AdbError(
            f"adb vrátil návratovou hodnotu {proc.returncode}: {detail or '(bez výstupu)'}"
        )
    return stdout


def parse_devices_output(text: str) -> list[Device]:
    """Zparsuje výstup `adb devices -l` na seznam Device."""
    devices: list[Device] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        extras: dict[str, str] = {}
        for token in parts[2:]:
            key, sep, value = token.partition(":")
            if sep:
                extras[key] = value
        devices.append(Device(serial=serial, state=state, extras=extras))
    return devices


_GETPROP_LINE = re.compile(r"^\[(.+?)\]: \[(.*)\]$")


def parse_getprop_output(text: str) -> dict[str, str]:
    """Zparsuje výstup `adb shell getprop` (formát `[klíč]: [hodnota]`)."""
    props: dict[str, str] = {}
    for raw_line in text.splitlines():
        match = _GETPROP_LINE.match(raw_line.strip())
        if match:
            props[match.group(1)] = match.group(2)
    return props


def parse_pm_list_output(text: str) -> list[str]:
    """Zparsuje výstup `pm list packages` na seznam názvů balíčků."""
    packages: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("package:"):
            packages.append(line[len("package:"):])
    return sorted(set(packages))


class AdbClient:
    """Read-only klient ADB.

    Parametry:
        adb_path: cesta k binárce adb (výchozí „adb“ z PATH).
        serial: cílové zařízení; když není zadáno, vybere se samo.
        timeout: výchozí časový limit na příkaz v sekundách.
        runner: funkce (argv, timeout) -> výstup; pro testy.
    """

    def __init__(
        self,
        adb_path: str = "adb",
        serial: str | None = None,
        timeout: float = 15.0,
        runner: Runner | None = None,
    ) -> None:
        self.adb_path = adb_path
        self.serial = serial
        self.timeout = timeout
        self._runner = runner or default_runner
        # Historie spuštěných (schválených) příkazů – pro ověření bezpečnosti.
        self.history: list[tuple[str, ...]] = []

    def _argv(self, *args: str) -> list[str]:
        argv = [self.adb_path]
        if self.serial:
            argv += ["-s", self.serial]
        argv += list(args)
        return argv

    def run_readonly(self, *args: str) -> str:
        """Sestaví argv, ověří read-only whitelist a teprve pak spustí runner."""
        argv = self._argv(*args)
        assert_readonly(argv)
        self.history.append(tuple(argv))
        return self._runner(argv, self.timeout)

    # ---- základní diagnostika ----

    def version(self) -> str:
        return self.run_readonly("version")

    def devices(self) -> list[Device]:
        return parse_devices_output(self.run_readonly("devices", "-l"))

    def pick_device(self) -> Device:
        """Vybere jediné připravené zařízení; jinak vyhodí výjimku."""
        devices = self.devices()
        ready = [device for device in devices if device.is_ready]
        if not ready:
            states = (
                ", ".join(f"{d.serial} ({d.state})" for d in devices)
                or "žádná zařízení"
            )
            raise NoDeviceError(f"Žádné připravené zařízení: {states}")
        if len(ready) > 1:
            serials = ", ".join(d.serial for d in ready)
            raise AmbiguousDeviceError(
                f"Připojeno více zařízení ({serials}); zadaj serial přes -s."
            )
        return ready[0]

    def ensure_device(self) -> Device:
        """Vybere zařízení a zapamatuje si serial pro další příkazy."""
        devices = self.devices()
        ready = [device for device in devices if device.is_ready]
        if self.serial:
            for device in ready:
                if device.serial == self.serial:
                    return device
            states = (
                ", ".join(f"{d.serial} ({d.state})" for d in devices)
                or "žádná zařízení"
            )
            raise NoDeviceError(f"Zařízení {self.serial} není připravené: {states}")
        device = self.pick_device()
        self.serial = device.serial
        return device

    # ---- čtení stavu zařízení ----

    def shell_readonly(self, *args: str) -> str:
        return self.run_readonly("shell", *args)

    def getprop(self) -> dict[str, str]:
        """Všechny vlastnosti zařízení (jeden příkaz, lokální parsování)."""
        return parse_getprop_output(self.shell_readonly("getprop"))

    def getprop_value(self, key: str) -> str | None:
        value = self.shell_readonly("getprop", key).strip()
        return value or None

    def settings(self, namespace: str, key: str) -> str:
        """Čtení hodnoty ze Settings (jen `settings get`)."""
        return self.shell_readonly("settings", "get", namespace, key).strip()

    def pm_list_packages(self, name_filter: str | None = None) -> list[str]:
        args = ["pm", "list", "packages"]
        if name_filter:
            args.append(name_filter)
        return parse_pm_list_output(self.shell_readonly(*args))

    def dumpsys(self, service: str) -> str:
        return self.shell_readonly("dumpsys", service)
