"""GUI test: run the exact interactive flow offscreen in a subprocess.

The subprocess creates the window in the same way the app does, runs the
lifecycle checks (scan, focus/Tab, Escape, close while busy, close when
idle, accessible tables) and prints a marker per milestone. The test
verifies the markers appear in order and the process exits 0 after a
full cooperative drain (Qt/Windows quirk: process must not exit while
the worker QThread is still running).
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    "import os, sys, time\n"
    "os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')\n"
    "sys.path.insert(0, r'{root}')\n"
    "from PyQt6.QtCore import Qt, QEvent\n"
    "from PyQt6.QtWidgets import QApplication\n"
    "from PyQt6.QtGui import QKeyEvent as QKE\n"
    "from ovladac.adb import AdbClient\n"
    "from ovladac.qtapp.main_window import MainWindow\n"
    "from tests.test_worker import RoutingRunner\n"
    "app = QApplication([])\n"
    "app.setQuitOnLastWindowClosed(False)\n"
    "def mark(m): print('MARKER ' + m, flush=True)\n"
    "def pump(pred, steps=500):\n"
    "    for _ in range(steps):\n"
    "        app.processEvents()\n"
    "        if pred(): return True\n"
    "        time.sleep(0.01)\n"
    "    app.processEvents(); return pred()\n"
    "def factory(s): return AdbClient(serial=s, runner=RoutingRunner())\n"
    "def tab(): return QKE(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)\n"
    "def esc(): return QKE(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)\n"
    "\n"
    "# --- window 1: scan, auto-select, tab order, diagnose, tables ---\n"
    "w = MainWindow(client_factory=factory)\n"
    "w.show()\n"
    "mark('W1_CREATED')\n"
    "ok = pump(lambda: w.device_combo.count() > 1)\n"
    "assert ok, 'scan never finished'\n"
    "assert w.device_combo.currentData() == 'KBYD9DJJJRVCVCI7'\n"
    "assert w.diagnose_button.isEnabled()\n"
    "mark('W1_SCAN_AUTOSELECT')\n"
    "\n"
    "# Tab order: combo -> refresh -> diagnose -> ident table -> services table\n"
    "chain = []\n"
    "w.device_combo.setFocus(); app.processEvents()\n"
    "fw = w.focusWidget(); assert fw is not None, 'combo did not take focus'\n"
    "for _ in range(5):\n"
    "    fw = w.focusWidget(); assert fw is not None\n"
    "    chain.append(fw)\n"
    "    QApplication.sendEvent(fw, tab())\n"
    "    app.processEvents()\n"
    "assert chain[0] is w.device_combo\n"
    "assert chain[1] is w.refresh_button\n"
    "assert chain[2] is w.diagnose_button\n"
    "assert chain[3] is w.ident_table\n"
    "assert chain[4] is w.services_table\n"
    "mark('W1_TAB_ORDER')\n"
    "\n"
    "# Escape must NOT close the main window\n"
    "QApplication.sendEvent(w, esc())\n"
    "QApplication.sendEvent(w.focusWidget() or w, esc())\n"
    "app.processEvents()\n"
    "assert w.isVisible(), 'Escape closed the main window'\n"
    "mark('W1_ESCAPE_OK')\n"
    "\n"
    "# Run the diagnostic and confirm the tables fill with accessible data\n"
    "w.diagnose_button.setFocus(); app.processEvents()\n"
    "w.diagnose_clicked()\n"
    "ok = pump(lambda: w._ident_sig != '')\n"
    "assert ok, 'diagnostic never filled tables'\n"
    "ok = pump(lambda: not w._busy)\n"
    "assert ok, 'worker still busy after diagnostic'\n"
    "item = w.ident_table.item(0, 0)\n"
    "assert item is not None\n"
    "assert item.data(Qt.ItemDataRole.AccessibleTextRole)\n"
    "assert item.data(Qt.ItemDataRole.AccessibleDescriptionRole)\n"
    "assert w.services_table.rowCount() > 0\n"
    "mark('W1_TABLES_ACCESSIBLE')\n"
    "\n"
    "# --- close contract: deferred until the worker thread drains ---\n"
    "w.close()\n"
    "stopped = pump(lambda: not w._thread.isRunning())\n"
    "assert stopped, 'worker thread never stopped after close'\n"
    "hidden = pump(lambda: not w.isVisible(), steps=300)\n"
    "assert hidden, 'window not closed after thread drain'\n"
    "mark('W1_CLOSED_AFTER_DRAIN')\n"
    "\n"
    "# --- window 2: a fresh instance closes through the same contract ---\n"
    "w2 = MainWindow(client_factory=factory)\n"
    "ok = pump(lambda: w2.device_combo.count() > 1)\n"
    "assert ok\n"
    "w2.show()\n"
    "w2.close()\n"
    "stopped2 = pump(lambda: not w2._thread.isRunning())\n"
    "hidden2 = pump(lambda: not w2.isVisible(), steps=300)\n"
    "assert stopped2 and hidden2, 'second window did not drain/close'\n"
    "mark('W2_CLOSED_AFTER_DRAIN')\n"
    "\n"
    "print('ALL_OK', flush=True)\n"
)


class GuiLifecycleSubprocessTest(unittest.TestCase):
    def test_gui_lifecycle_contract(self) -> None:
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        code = SCRIPT.format(root=str(ROOT))
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT), env=env,
        )
        tail = (proc.stdout or "") + "\n" + (proc.stderr or "")
        self.assertEqual(
            proc.returncode, 0,
            msg="GUI subprocess exited nonzero:\n" + tail[-3000:],
        )
        self.assertIn("ALL_OK", proc.stdout or "", tail[-2000:])
        for marker in (
            "MARKER W1_CREATED",
            "MARKER W1_SCAN_AUTOSELECT",
            "MARKER W1_TAB_ORDER",
            "MARKER W1_ESCAPE_OK",
            "MARKER W1_TABLES_ACCESSIBLE",
            "MARKER W1_CLOSED_AFTER_DRAIN",
            "MARKER W2_CLOSED_AFTER_DRAIN",
        ):
            self.assertIn(marker, proc.stdout or "", "missing marker " + marker)


class NoTerminateSourceCheck(unittest.TestCase):
    def test_no_terminate_no_waiting_call(self) -> None:
        import inspect

        from ovladac.qtapp import main_window as mw

        source = inspect.getsource(mw)
        self.assertNotIn(".terminate(", source)
        self.assertNotIn(".wait(", source)


if __name__ == "__main__":
    unittest.main()
