"""Testy whitelistu read-only (ovladac.safety)."""

from __future__ import annotations

import unittest

from ovladac.safety import SafetyViolationError, assert_readonly


class TestAllowedCommands(unittest.TestCase):
    """Povolené = jen čtení."""

    def test_devices(self):
        assert_readonly(["adb", "devices"])
        assert_readonly(["adb", "devices", "-l"])

    def test_version(self):
        assert_readonly(["adb", "version"])
        assert_readonly(["adb", "--version"])

    def test_shell_getprop(self):
        assert_readonly(["adb", "shell", "getprop"])
        assert_readonly(["adb", "shell", "getprop", "ro.product.model"])

    def test_shell_settings_get(self):
        assert_readonly(
            ["adb", "-s", "ABC123", "shell", "settings", "get",
             "secure", "accessibility_enabled"]
        )

    def test_shell_pm_read_only_subcommands(self):
        assert_readonly(["adb", "shell", "pm", "list", "packages"])
        assert_readonly(["adb", "shell", "pm", "path", "com.example"])
        assert_readonly(["adb", "shell", "pm", "dump", "com.example"])

    def test_shell_dumpsys(self):
        assert_readonly(["adb", "shell", "dumpsys", "accessibility"])

    def test_shell_which_and_ls(self):
        assert_readonly(["adb", "shell", "which", "uiautomator"])
        assert_readonly(["adb", "shell", "ls", "/system/bin"])

    def test_adb_binary_as_full_path(self):
        assert_readonly([r"C:\Sdk\platform-tools\adb.exe", "devices", "-l"])


class TestDeniedCommands(unittest.TestCase):
    """Zakázané = cokoliv, co mění stav (nebo není v whitelistu)."""

    DENIED = [
        # změny nastavení
        ["adb", "shell", "settings", "put", "secure", "accessibility_enabled", "1"],
        ["adb", "shell", "settings", "put", "system", "screen_off_timeout", "60000"],
        # vstupy
        ["adb", "shell", "input", "tap", "100", "100"],
        ["adb", "shell", "input", "text", "ahoj"],
        ["adb", "shell", "input", "keyevent", "4"],
        # oprávnění a balíčky
        ["adb", "shell", "pm", "grant", "com.example", "android.permission.X"],
        ["adb", "install", "app.apk"],
        ["adb", "shell", "pm", "uninstall", "com.example"],
        ["adb", "shell", "pm", "clear", "com.example"],
        # změny spojení / párování
        ["adb", "pair", "192.168.1.5:37123"],
        ["adb", "forward", "tcp:5039", "tcp:5039"],
        ["adb", "reverse", "tcp:5039", "tcp:5039"],
        ["adb", "connect", "192.168.1.5:5555"],
        # UI Automator (zapisuje soubor na zařízení – zakázán do schválení)
        ["adb", "shell", "uiautomator", "dump"],
        # ostatní změny stavu
        ["adb", "shell", "am", "start", "-a", "android.intent.action.VIEW"],
        ["adb", "shell", "reboot"],
        ["adb", "shell", "setprop", "debug.foo", "1"],
        ["adb", "shell", "wm", "size", "1080x2400"],
        # neznámé příkazy jsou odmítnuty také (whitelist)
        ["adb", "shell", "neco_uplne_jineho"],
        ["adb", "neco_uplne_jineho"],
    ]

    def test_denied_commands_raise(self):
        for argv in self.DENIED:
            with self.subTest(argv=argv):
                with self.assertRaises(SafetyViolationError):
                    assert_readonly(argv)

    def test_error_message_mentions_readonly(self):
        with self.assertRaises(SafetyViolationError) as ctx:
            assert_readonly(["adb", "shell", "settings", "put", "secure", "x", "1"])
        self.assertIn("zakázán", str(ctx.exception))

    def test_empty_argv_rejected(self):
        with self.assertRaises(SafetyViolationError):
            assert_readonly([])

    def test_shell_without_command_rejected(self):
        with self.assertRaises(SafetyViolationError):
            assert_readonly(["adb", "shell"])


if __name__ == "__main__":
    unittest.main()
