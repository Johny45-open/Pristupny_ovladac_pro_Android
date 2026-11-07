#!/usr/bin/env python3
"""READ-ONLY diagnostika připojeného zařízení (Etapa 1).

Spouštěj z kořene projektu:

    python scripts\\run_diagnostics.py

Skript provádí VÝHRADNĚ čtecí příkazy (whitelist v ovladac.safety):
version, devices -l, getprop, settings get, pm list packages,
dumpsys accessibility. Nic nemění na telefonu ani v projektu.

Po spuštění vypíše seznam skutečně spuštěných příkazů, takže si
můžeš ověřit, že proběhlo jen čtení.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Umožní spuštění skriptu bez instalace balíčku (kořen projektu do sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ovladac import (  # noqa: E402
    READER_COMPONENT,
    SELECT_TO_SPEAK_COMPONENT,
    TALKBACK_COMPONENT,
    TALKBACK_PACKAGE,
    AdbClient,
    AdbError,
    build_device_info,
    collect_state,
    is_package_installed,
)

READER_PACKAGE = "com.google.android.accessibility.reader"


def _yes_no(value: bool | None) -> str:
    if value is None:
        return "neznámé"
    return "ANO" if value else "ne"


def main() -> int:
    client = AdbClient()

    print("=== Etapa 1: READ-ONLY diagnostika ===\n")

    # 1) Verze ADB
    try:
        first_line = client.version().strip().splitlines()[0]
        print(f"ADB: {first_line}")
    except AdbError as exc:
        print(f"CHYBA: {exc}")
        return 1

    # 2) Zařízení
    try:
        device = client.ensure_device()
    except AdbError as exc:
        print(f"CHYBA: {exc}")
        print("Zkontroluj USB kabel a povolené USB ladění v telefonu.")
        return 1
    print(f"Zařízení: {device.serial} (stav: {device.state})")

    # 3) Identifikace
    info = build_device_info(device, client.getprop())
    print("\n--- Identifikace zařízení ---")
    print(f"Model:            {info.model}")
    print(f"Výrobce:          {info.manufacturer} ({info.brand})")
    print(f"Kód zařízení:     {info.device}")
    print(f"Android:          {info.android_release} (API {info.sdk_int})")
    print(f"HyperOS:          {info.incremental} (MIUI verze: {info.miui_version})")
    print(f"Build:            {info.display_id}")
    print(f"Bezpeč. patch:    {info.security_patch}")
    print(f"ABI:              {info.abi}")
    print(f"Retail ROM:       {_yes_no(not info.debuggable)}")

    # 4) Balíčky čteček
    packages = client.pm_list_packages()
    print("\n--- Balíčky čteček / přístupnosti ---")
    for package in (
        TALKBACK_PACKAGE,
        READER_PACKAGE,
        "com.google.android.accessibility.switchaccess",
        "com.google.android.apps.accessibility.reveal",
        "com.nirenr.talkman",
        "fyi.quin.backtalk",
        "eu.appsuite.talkforward",
        "com.xiaomi.aicr",
    ):
        mark = "ANO  " if is_package_installed(packages, package) else "ne   "
        print(f"  [{mark}] {package}")

    # 5) Stav přístupnosti
    state = collect_state(client)
    print("\n--- Stav přístupnosti ---")
    print(f"accessibility_enabled:            {_yes_no(state.accessibility_enabled)}")
    print(f"touch_exploration_enabled:        {_yes_no(state.touch_exploration_enabled)}")
    print(f"installedServiceCount:            {state.installed_service_count}")

    print("\nPovolené služby (settings):")
    for service in state.enabled_services or ("(žádné)",):
        print(f"  - {service}")

    print("\nSkutečně připojené (bound, dumpsys):")
    for label in state.bound_labels or ("(žádné)",):
        print(f"  - {label}")

    print("\nHavarované (crashed, dumpsys):")
    for service in state.crashed_services or ("(žádné)",):
        print(f"  - {service}")

    print("\nKandidáti na zkratku hlasitostí (dumpsys):")
    for candidate in state.shortcut_candidates or ("(žádné)",):
        print(f"  - {candidate}")

    # 6) Shrnutí
    talkback_installed = is_package_installed(packages, TALKBACK_PACKAGE)
    print("\n--- Shrnutí ---")
    print(f"TalkBack ({TALKBACK_COMPONENT}):")
    print(f"  nainstalovaný:  {_yes_no(talkback_installed)}")
    print(f"  povolený:       {_yes_no(state.talkback_enabled)}")
    print(f"  aktivní (odhad):{_yes_no(state.talkback_active)}")
    print(f"Select to Speak povolený: {_yes_no(state.select_to_speak_enabled)}")
    print(f"Reading mode povolený:    {_yes_no(state.reader_service_enabled)}")
    print(f"  (komponenta {READER_COMPONENT})")

    # 7) Kontrola bezpečnosti: co přesně běželo
    print("\n--- Provedené příkazy (read-only kontrola) ---")
    for command in client.history:
        print(f"  {' '.join(command)}")
    print("\nHotovo. Nic se na telefonu neměnilo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
