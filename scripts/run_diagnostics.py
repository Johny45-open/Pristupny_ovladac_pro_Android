#!/usr/bin/env python3
"""READ-ONLY diagnostika připojeného zařízení (společné jádro s GUI).

Spouštěj z kořene projektu:

    python scripts\\run_diagnostics.py

Výhradně čtecí ADB příkazy (whitelist v ovladac.safety.py).
Na telefonu i v projektu se nic nemění.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ovladac import (  # noqa: E402
    AdbClient,
    AdbError,
    collect_diagnostic,
    scan_devices,
)


def _yn(value: bool | None) -> str:
    if value is None:
        return "neznámé"
    return "ANO" if value else "ne"


def main() -> int:
    client = AdbClient()

    print("=== READ-ONLY diagnostika (Etapa 2A) ===\n")

    try:
        first_line = client.version().strip().splitlines()[0]
        print(f"ADB: {first_line}")
    except AdbError as exc:
        print(f"CHYBA: {exc}")
        return 1

    try:
        selection = scan_devices(client)
    except AdbError as exc:
        print(f"CHYBA: {exc}")
        return 1

    if selection.reason == "none":
        print("Žádné připojené zařízení. Zkontroluj USB kabel a USB ladění.")
        return 1
    if selection.reason == "multiple":
        print("Připojeno více telefonů; diagnostiku nespouštím (bez automatického výběru).")
        for dev in selection.devices:
            print(f"  {dev.serial}  ({dev.state})")
        return 1

    serial = selection.selected_serial
    client = AdbClient(serial=serial)
    print(f"Zařízení: {serial} (stav: {selection.devices[0].state})")

    try:
        report = collect_diagnostic(client)
    except AdbError as exc:
        print(f"CHYBA: {exc}")
        return 1

    info = report.device_info
    print("\n--- Identifikace zařízení ---")
    print(f"Model:            {info.model}")
    print(f"Výrobce:          {info.manufacturer} ({info.brand})")
    print(f"Kód zařízení:     {info.device}")
    print(f"Android:          {info.android_release} (API {info.sdk_int})")
    print(f"HyperOS:          {info.incremental} (MIUI: {info.miui_version})")
    print(f"Build:            {info.display_id}")
    print(f"Bezpečný patch:   {info.security_patch}")
    print(f"ABI:              {info.abi}")
    print(f"Retail ROM:       {_yn(not info.debuggable)}")

    print("\n--- Služby přístupnosti ---")
    print(f"TalkBack nainstalovaný:   {_yn(report.talkback_installed)}")
    print(f"TalkBack povolený:        {_yn(report.talkback_enabled)}")
    print(f"TalkBack funkční (odhad): {_yn(report.talkback_active)}")
    print(f"Select to Speak povolená: {_yn(report.select_to_speak_enabled)}")
    print(f"Reading mode povolená:    {_yn(report.reader_enabled)}")
    print(f"Touch exploration:        {_yn(report.touch_exploration)}")
    print(f"Nainstalované služby:     {report.installed_service_count}")
    print(f"Připojené služby:         {', '.join(report.accessibility.bound_labels) or '—'}")
    crashed = ", ".join(report.accessibility.crashed_services) or "—"
    print(f"Havarované služby:        {crashed}")

    print("\n--- Provedené příkazy (read-only kontrola) ---")
    for command in client.history:
        print(f"  {' '.join(command)}")
    print("\nHotovo. Nic se na telefonu neměnilo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
