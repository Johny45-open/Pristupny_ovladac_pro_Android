"""Testy čtení stavu přístupnosti (ovladac.accessibility).

Klíčová regrese z opravy Etapy 0: TalkBack je
com.google.android.marvin.talkback/.TalkBackService – balíček
com.google.android.accessibility.reader (Reading mode) se za TalkBack
nesmí označit.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from ovladac.accessibility import (
    READER_COMPONENT,
    SELECT_TO_SPEAK_COMPONENT,
    TALKBACK_COMPONENT,
    collect_state,
    is_package_installed,
    parse_bool_setting,
    parse_dumpsys_accessibility,
    parse_enabled_services,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class StubSettingsClient:
    """Náhrada AdbClient pro test collect_state – jen vrací připravené výstupy."""

    def __init__(self, settings_map: dict[tuple[str, str], str], dumpsys_text: str):
        self._settings = settings_map
        self._dumpsys = dumpsys_text

    def settings(self, namespace: str, key: str) -> str:
        return self._settings[(namespace, key)]

    def dumpsys(self, service: str) -> str:
        assert service == "accessibility"
        return self._dumpsys


class TestSettingsParsing(unittest.TestCase):
    def test_bool_setting(self):
        self.assertIs(parse_bool_setting("1"), True)
        self.assertIs(parse_bool_setting("0"), False)
        self.assertIsNone(parse_bool_setting("null"))
        self.assertIsNone(parse_bool_setting(""))

    def test_enabled_services_real_fixture(self):
        raw = load_fixture("settings_enabled_services.txt")
        services = parse_enabled_services(raw)
        self.assertEqual(len(services), 2)
        self.assertIn(READER_COMPONENT, services)
        self.assertIn(SELECT_TO_SPEAK_COMPONENT, services)
        # Regrese: hlavní TalkBack NENÍ povolený.
        self.assertNotIn(TALKBACK_COMPONENT, services)

    def test_enabled_services_null(self):
        self.assertEqual(parse_enabled_services("null\n"), ())

    def test_enabled_services_empty(self):
        self.assertEqual(parse_enabled_services(""), ())

    def test_normalize_component_short_and_full_form(self):
        from ovladac.accessibility import normalize_component

        short = "com.google.android.accessibility.reader/.ReaderService"
        full = "com.google.android.accessibility.reader/com.google.android.accessibility.reader.ReaderService"
        self.assertEqual(normalize_component(short), full)
        self.assertEqual(normalize_component(full), full)
        # Krátký tvar ze settings a plný tvar z dumpsys musí být stejné.
        self.assertEqual(
            parse_enabled_services(short)[0],
            normalize_component(full),
        )


class TestDumpsysParsing(unittest.TestCase):
    def setUp(self):
        self.state = parse_dumpsys_accessibility(
            load_fixture("dumpsys_accessibility.txt")
        )

    def test_touch_exploration_is_off(self):
        self.assertIs(self.state.touch_exploration_enabled, False)

    def test_installed_service_count(self):
        # Skutečný výstup zařízení: 15 (počet služeb, ne balíčků).
        self.assertEqual(self.state.installed_service_count, 15)

    def test_bound_services(self):
        self.assertEqual(self.state.bound_labels, ("Poslech vybraného textu",))

    def test_crashed_services(self):
        self.assertIn(READER_COMPONENT, self.state.crashed_services)
        self.assertNotIn(TALKBACK_COMPONENT, self.state.crashed_services)

    def test_enabled_services_from_dumpsys(self):
        self.assertIn(READER_COMPONENT, self.state.enabled_services)
        self.assertIn(SELECT_TO_SPEAK_COMPONENT, self.state.enabled_services)
        self.assertNotIn(TALKBACK_COMPONENT, self.state.enabled_services)

    def test_shortcut_candidates_include_talkback(self):
        self.assertEqual(len(self.state.shortcut_candidates), 4)
        self.assertIn(TALKBACK_COMPONENT, self.state.shortcut_candidates)
        self.assertIn(
            "com.nirenr.talkman/com.nirenr.talkman.TalkManAccessibilityService",
            self.state.shortcut_candidates,
        )


class TestStateProperties(unittest.TestCase):
    def setUp(self):
        self.state = parse_dumpsys_accessibility(
            load_fixture("dumpsys_accessibility.txt")
        )

    def test_talkback_not_enabled(self):
        self.assertFalse(self.state.talkback_enabled)

    def test_talkback_not_active(self):
        self.assertFalse(self.state.talkback_active)

    def test_select_to_speak_enabled(self):
        self.assertTrue(self.state.select_to_speak_enabled)

    def test_reader_service_enabled(self):
        self.assertTrue(self.state.reader_service_enabled)


class TestCollectState(unittest.TestCase):
    def test_collect_merges_settings_and_dumpsys(self):
        client = StubSettingsClient(
            settings_map={
                ("secure", "accessibility_enabled"): load_fixture(
                    "settings_accessibility_enabled.txt"
                ),
                ("secure", "touch_exploration_enabled"): load_fixture(
                    "settings_touch_exploration.txt"
                ),
                ("secure", "enabled_accessibility_services"): load_fixture(
                    "settings_enabled_services.txt"
                ),
            },
            dumpsys_text=load_fixture("dumpsys_accessibility.txt"),
        )
        state = collect_state(client)  # type: ignore[arg-type]
        self.assertIs(state.accessibility_enabled, True)
        self.assertIs(state.touch_exploration_enabled, False)
        self.assertEqual(len(state.enabled_services), 2)
        self.assertFalse(state.talkback_enabled)
        self.assertTrue(state.select_to_speak_enabled)
        self.assertEqual(state.installed_service_count, 15)


class TestPackageCheck(unittest.TestCase):
    def test_is_package_installed(self):
        packages = ["com.google.android.marvin.talkback", "com.example.app"]
        self.assertTrue(is_package_installed(packages, "com.google.android.marvin.talkback"))
        self.assertFalse(is_package_installed(packages, "com.not.here"))


if __name__ == "__main__":
    unittest.main()
