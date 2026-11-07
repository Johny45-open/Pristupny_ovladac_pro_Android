"""Klasifikace příkazů ADB pro režim READ-ONLY.

Etapa 1 projektu pracuje výhradně s čtením stavu zařízení. Tento modul
je jediné místo, které rozhoduje, který příkaz smí být spuštěn. Každý
příkaz prochází funkcí assert_readonly() dřív, než se cokoliv spustí –
kontrola probíhá před voláním runneru, takže zakázaný příkaz se na
zařízení ani nedostane.

Princip whitelistu: povolené jsou jen explicitně vyjmenované čtecí
příkazy. Cokoliv jiného (včetně neznámých příkazů) je odmítnuto.
"""

from __future__ import annotations

import os
from collections.abc import Sequence


class SafetyViolationError(RuntimeError):
    """Pokus o spuštění příkazu, který není v whitelistu read-only."""


# Příkazy shell, které jsou samy o sobě jen čtení.
_SHELL_READONLY_TOOLS = frozenset({"getprop", "dumpsys", "which", "ls"})

# Nástroje, které mají povolené jen konkrétní podpříkazy
# (např. settings get je čtení, settings put je změna stavu).
_SHELL_SUBCOMMANDS: dict[str, frozenset[str]] = {
    "settings": frozenset({"get"}),
    "pm": frozenset({"list", "path", "dump"}),
}

# Příkazy adb mimo shell, které jsou dovolené (jen čtení).
_ADB_READONLY_COMMANDS = frozenset({"devices", "version"})

# Globální volby adb, které jen vybírají cílové zařízení/server.
_ADB_GLOBAL_OPTIONS = frozenset({"-s", "-d", "-e", "-H", "-P", "-L"})

# Volby, které jen vypíší verzi (ekvivalent `adb version`).
_ADB_VERSION_FLAGS = frozenset({"-V", "--version"})

# Příklady zakázaných operací – jen pro srozumitelné chybové hlášky.
_DENIED_EXAMPLES = (
    "settings put",
    "input tap/text/keyevent",
    "pm grant/revoke/install",
    "am start/broadcast",
    "uiautomator dump",
    "adb install/pair/forward/reverse",
)


def _strip_adb_binary(argv: Sequence[str]) -> list[str]:
    """Odstraní z argv název binárky adb (může to být i cesta)."""
    if not argv:
        raise SafetyViolationError("Prázdný příkaz.")
    first = os.path.basename(str(argv[0])).lower()
    if first in {"adb", "adb.exe"}:
        return [str(token) for token in argv[1:]]
    return [str(token) for token in argv]


def assert_readonly(argv: Sequence[str]) -> None:
    """Ověří, že argv je read-only příkaz ADB. Jinak vyhodí SafetyViolationError.

    argv může začínat názvem binárky adb („adb“, „...\\adb.exe“) nebo
    rovnou příkazem („devices“, „shell“, ...).
    """
    args = _strip_adb_binary(argv)

    # Přeskočit globální volby (např. -s SERIAL).
    index = 0
    while index < len(args):
        token = args[index]
        if token in _ADB_GLOBAL_OPTIONS and index + 1 < len(args):
            index += 2
            continue
        if token in _ADB_VERSION_FLAGS:
            break
        if token.startswith("-"):
            raise SafetyViolationError(f"Neznámá globální volba adb: {token}")
        break

    rest = args[index:]
    if not rest:
        raise SafetyViolationError("Chybí příkaz adb.")

    command, command_args = rest[0], rest[1:]

    if command in _ADB_READONLY_COMMANDS or command in _ADB_VERSION_FLAGS:
        return

    if command == "shell":
        _assert_shell_readonly(command_args)
        return

    raise SafetyViolationError(
        f"Příkaz 'adb {command}' není v whitelistu read-only. "
        f"V Etapě 1 jsou povolené jen: {', '.join(sorted(_ADB_READONLY_COMMANDS))}, "
        f"shell (čtecí nástroje). Zakázané příklady: {', '.join(_DENIED_EXAMPLES)}."
    )


def _assert_shell_readonly(shell_args: Sequence[str]) -> None:
    if not shell_args:
        raise SafetyViolationError("Chybí příkaz uvnitř 'adb shell'.")

    tool = shell_args[0]
    subcommand = shell_args[1] if len(shell_args) > 1 else None

    if tool in _SHELL_READONLY_TOOLS:
        return

    if tool in _SHELL_SUBCOMMANDS:
        allowed = _SHELL_SUBCOMMANDS[tool]
        if subcommand in allowed:
            return
        shown = f"{tool} {subcommand}" if subcommand else tool
        raise SafetyViolationError(
            f"Příkaz 'shell {shown}' mění stav zařízení "
            f"a je v Etapě 1 zakázán. Povolené podpříkazy: {', '.join(sorted(allowed))}."
        )

    raise SafetyViolationError(
        f"Příkaz 'shell {tool}' není v whitelistu read-only. "
        f"Povolené nástroje: {', '.join(sorted(_SHELL_READONLY_TOOLS | set(_SHELL_SUBCOMMANDS)))}."
    )
