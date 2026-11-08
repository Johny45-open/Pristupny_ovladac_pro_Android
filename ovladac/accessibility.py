"""Čtení stavu přístupnosti (TalkBack a související služby) – jen čtení.

Důležité rozlišení (z opravy Etapy 0):

- TalkBack = com.google.android.marvin.talkback/.TalkBackService
  (hlavní čtečka obrazovky s touch exploration).
- Select to Speak = samostatná služba, NENÍ to TalkBack.
- com.google.android.accessibility.reader = Google Reading mode,
  NENÍ to hlavní TalkBack.

Stavy rozlišujeme podle toho, kde jsou údaje skutečně uvedeny:

- nainstalované: výstup `pm list packages` (volá volající),
- povolené: `settings get secure enabled_accessibility_services`,
- připojené (bound) + havarované: `dumpsys accessibility`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from .adb import AdbClient

# ---- Známé komponenty (ověřeno výstupem Package Manageru na zařízení) ----

TALKBACK_PACKAGE = "com.google.android.marvin.talkback"
TALKBACK_COMPONENT = f"{TALKBACK_PACKAGE}/{TALKBACK_PACKAGE}.TalkBackService"
SELECT_TO_SPEAK_COMPONENT = (
    f"{TALKBACK_PACKAGE}/"
    "com.google.android.accessibility.selecttospeak.SelectToSpeakService"
)
READER_COMPONENT = (
    "com.google.android.accessibility.reader/"
    "com.google.android.accessibility.reader.ReaderService"
)

# ---- Parsování Settings ----


def parse_bool_setting(text: str) -> bool | None:
    """`settings get` vrací '1'/'0', u neexistujícího klíče 'null'."""
    value = text.strip().lower()
    if value in {"1", "true"}:
        return True
    if value in {"0", "false"}:
        return False
    return None


def normalize_component(component: str) -> str:
    """Ujednotí zápis komponenty na plný tvar `balíček/třída`.

    Settings ukládají komponenty i ve zkráceném tvaru
    `com.example/.Služba`, zatímco dumpsys používá plný zápis.
    Obojí musíme porovnávat stejně.
    """
    if "/" not in component:
        return component
    package, _, cls = component.partition("/")
    if cls.startswith("."):
        cls = package + cls
    return f"{package}/{cls}"


def parse_enabled_services(text: str) -> tuple[str, ...]:
    """Zparsuje `settings get secure enabled_accessibility_services`.

    Formát: komponenta1:komponenta2:... (oddělovač je dvojtečka,
    názvy komponent dvojtečku neobsahují). Komponenty normalizuje
    na plný tvar.
    """
    value = text.strip()
    if not value or value.lower() == "null":
        return ()
    return tuple(
        normalize_component(part.strip())
        for part in value.split(":")
        if part.strip()
    )


# ---- Parsování dumpsys accessibility ----

_RE_TOUCH_EXPLORATION = re.compile(r"touchExplorationEnabled=(true|false)")
_RE_INSTALLED_COUNT = re.compile(r"installedServiceCount=(\d+)")
_RE_BRACED_GROUP = re.compile(r"\{([^{}]*)\}")
_RE_BOUND_SERVICE = re.compile(r"Service\[label=([^,\]]+)")


def _extract_braced_groups(text: str) -> tuple[str, ...]:
    return tuple(
        normalize_component(match.group(1).strip())
        for match in _RE_BRACED_GROUP.finditer(text)
    )


def _split_components(text: str) -> tuple[str, ...]:
    value = text.strip()
    if value.startswith("{") and value.endswith("}"):
        value = value[1:-1]
    return tuple(
        normalize_component(part.strip())
        for part in value.split(",")
        if part.strip()
    )


@dataclass(frozen=True)
class AccessibilityState:
    """Stav přístupnosti – složený z Settings a dumpsys."""

    # ze settings
    accessibility_enabled: bool | None = None
    touch_exploration_enabled: bool | None = None
    enabled_services: tuple[str, ...] = ()
    # z dumpsys
    bound_labels: tuple[str, ...] = ()
    crashed_services: tuple[str, ...] = ()
    shortcut_candidates: tuple[str, ...] = ()
    installed_service_count: int | None = None

    @property
    def talkback_enabled(self) -> bool:
        """Je hlavní TalkBackService v seznamu povolených služeb?"""
        return TALKBACK_COMPONENT in self.enabled_services

    @property
    def talkback_active(self) -> bool:
        """Přibližný stav „skutečně běží“: povolený a nev seznamu havarovaných.

        Poznámka: dumpsys uvádí u bound služeb jen textový popisek (label),
        ne komponentu, takže přesné přiřazení label -> komponenta z výstupu
        nelze získat. Proto jde o heuristic, ne o přímý důkaz.
        """
        return self.talkback_enabled and TALKBACK_COMPONENT not in self.crashed_services

    @property
    def select_to_speak_enabled(self) -> bool:
        return SELECT_TO_SPEAK_COMPONENT in self.enabled_services

    @property
    def reader_service_enabled(self) -> bool:
        return READER_COMPONENT in self.enabled_services

    @property
    def reader_service_crashed(self) -> bool:
        return READER_COMPONENT in self.crashed_services

    @property
    def select_to_speak_crashed(self) -> bool:
        return SELECT_TO_SPEAK_COMPONENT in self.crashed_services

    @property
    def talkback_crashed(self) -> bool:
        return TALKBACK_COMPONENT in self.crashed_services


def parse_dumpsys_accessibility(text: str) -> AccessibilityState:
    """Zparsuje relevantní řádky z výstupu `dumpsys accessibility`."""
    touch_exploration: bool | None = None
    installed_count: int | None = None
    enabled: tuple[str, ...] = ()
    bound: tuple[str, ...] = ()
    crashed: tuple[str, ...] = ()
    shortcuts: tuple[str, ...] = ()

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if "touchExplorationEnabled=" in line:
            match = _RE_TOUCH_EXPLORATION.search(line)
            if match:
                touch_exploration = match.group(1) == "true"

        if "installedServiceCount=" in line:
            match = _RE_INSTALLED_COUNT.search(line)
            if match:
                installed_count = int(match.group(1))

        if line.startswith("Enabled services:"):
            enabled = _extract_braced_groups(line[len("Enabled services:"):])
        elif line.startswith("Crashed services:"):
            crashed = _extract_braced_groups(line[len("Crashed services:"):])
        elif line.startswith("Bound services:"):
            bound = tuple(
                match.group(1).strip()
                for match in _RE_BOUND_SERVICE.finditer(line)
            )
        elif line.startswith("shortcut key:"):
            shortcuts = _split_components(line[len("shortcut key:"):])

    return AccessibilityState(
        touch_exploration_enabled=touch_exploration,
        enabled_services=enabled,
        bound_labels=bound,
        crashed_services=crashed,
        shortcut_candidates=shortcuts,
        installed_service_count=installed_count,
    )


def is_package_installed(packages: list[str], package_name: str) -> bool:
    """Je balíček v seznamu z `pm list packages`?"""
    return package_name in packages


def collect_state(client: AdbClient) -> AccessibilityState:
    """Načte kompletní stav přístupnosti přes read-only příkazy.

    Provede 4 příkazy: 3× settings get + 1× dumpsys accessibility.
    """
    from_settings = AccessibilityState(
        accessibility_enabled=parse_bool_setting(
            client.settings("secure", "accessibility_enabled")
        ),
        touch_exploration_enabled=parse_bool_setting(
            client.settings("secure", "touch_exploration_enabled")
        ),
        enabled_services=parse_enabled_services(
            client.settings("secure", "enabled_accessibility_services")
        ),
    )
    from_dumpsys = parse_dumpsys_accessibility(client.dumpsys("accessibility"))
    return replace(
        from_dumpsys,
        accessibility_enabled=from_settings.accessibility_enabled,
        touch_exploration_enabled=from_settings.touch_exploration_enabled,
        enabled_services=from_settings.enabled_services,
    )


__all__ = [
    "READER_COMPONENT",
    "SELECT_TO_SPEAK_COMPONENT",
    "TALKBACK_COMPONENT",
    "TALKBACK_PACKAGE",
    "AccessibilityState",
    "collect_state",
    "is_package_installed",
    "normalize_component",
    "parse_bool_setting",
    "parse_dumpsys_accessibility",
    "parse_enabled_services",
]
