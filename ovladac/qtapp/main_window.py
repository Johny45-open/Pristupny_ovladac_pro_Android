"""Hlavní okno ADB ovladače – výhradně standardní přístupné widgety.

Pořadí fokusu (Tab): combo → Obnovit → Spustit → tabulka ident → tabulka služeb.
Escape v hlavním okně nic nedělá; v dialogu zavře jen dialog.
Zavírá se standardně (tlačítko / Alt+F4); QThread žije do posledního close().
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..accessibility import READER_COMPONENT, SELECT_TO_SPEAK_COMPONENT, TALKBACK_PACKAGE
from ..adb import AdbClient
from ..diagnostics import DeviceSelection, DiagnosticReport
from .dialogs import show_error_dialog
from .worker import AdbWorker

_ITEM_TEXT = Qt.ItemDataRole.AccessibleTextRole
_ITEM_DESC = Qt.ItemDataRole.AccessibleDescriptionRole


def _yn(value: bool | None) -> str:
    if value is None:
        return "neznámé"
    return "ANO" if value else "ne"


def _ident_rows(report: DiagnosticReport) -> list[tuple[str, str, str]]:
    info = report.device_info
    return [
        ("Serial a stav", f"{report.device.serial} ({report.device.state})",
         "Identifikátor a stav zařízení z adb devices."),
        ("Model", info.model or "—", "Model telefonu (ro.product.model)."),
        ("Výrobce", info.manufacturer or info.brand or "—", "Výrobce telefonu."),
        ("Kód zařízení", info.device or "—", "Interní kód zařízení (ro.product.device)."),
        ("Android", f"{info.android_release or '?'} (API {info.sdk_int if info.sdk_int is not None else '?'})",
         "Verze Androidu a číslo API."),
        ("HyperOS", f"{info.incremental or 'ne'}{('  ' + info.miui_version) if info.miui_version else ''}",
         "Verze HyperOS a verze MIUI."),
        ("Build", info.display_id or "—", "Identifikátor sestavení ROM."),
        ("Bezpečnostní patch", info.security_patch or "—", "Datum bezpečnostního patche."),
        ("ABI", info.abi or "—", "Cílová architektura procesoru."),
        ("Retail ROM", _yn(not info.debuggable), "Zda nejde o vyvíjenou (userdebug) sestavení."),
    ]


def _service_rows(report: DiagnosticReport) -> list[tuple[str, str, str]]:
    a11y = report.accessibility
    return [
        ("TalkBack – nainstalován", _yn(report.talkback_installed),
         f"Balíček {TALKBACK_PACKAGE}."),
        ("TalkBack – povolen", _yn(report.talkback_enabled),
         "Komponenta TalkBackService v seznamu povolených služeb."),
        ("TalkBack – funkční (odhad)", _yn(report.talkback_active),
         "Povolený a nehavarovaný; přímé vázání service dumpsys neoznamuje."),
        ("TalkBack – havaruje", _yn(report.talkback_crashed),
         "Komponenta v seznamu havarovaných služeb."),
        ("Select to Speak – povolená", _yn(report.select_to_speak_enabled),
         f"Komponenta {SELECT_TO_SPEAK_COMPONENT}."),
        ("Select to Speak – havaruje", _yn(report.select_to_speak_crashed),
         "Komponenta v seznamu havarovaných služeb."),
        ("Reading mode – povolená", _yn(report.reader_enabled),
         f"Komponenta {READER_COMPONENT}."),
        ("Reading mode – havaruje", _yn(report.reader_crashed),
         "Komponenta v seznamu havarovaných služeb."),
        ("Touch exploration", _yn(a11y.touch_exploration_enabled),
         "Globální stav touch exploration."),
        ("Nainstalované služby (počet)",
         str(a11y.installed_service_count if a11y.installed_service_count is not None else "—"),
         "installedServiceCount z dumpsys accessibility."),
        ("Připojené služby (popisy)", ", ".join(a11y.bound_labels) or "—",
         "Bound services z dumpsys accessibility."),
        ("Kandidáti na zkratku hlasitostí", ", ".join(a11y.shortcut_candidates) or "—",
         "Komponenty registrované na zkratku obou tlačítek hlasitosti."),
    ]


class MainWindow(QMainWindow):
    scan_requested = pyqtSignal()
    diagnose_requested = pyqtSignal(str)

    def __init__(self, client_factory: "Callable[[str | None], AdbClient] | None" = None) -> None:
        super().__init__()
        self.setWindowTitle("Přístupný ovladač Androidu – diagnostika")
        self._devices: list = []
        self._closing = False
        self._busy = False
        self._ident_sig = ""
        self._service_sig = ""

        self._worker = AdbWorker(client_factory=client_factory)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._connect_signals()
        self._build_ui()
        self._thread.start()
        self.scan_requested.emit()

    def _connect_signals(self) -> None:
        self.scan_requested.connect(self._worker.do_scan)
        self.diagnose_requested.connect(self._worker.do_diagnostic)
        self._worker.started.connect(self._on_started)
        self._worker.scan_done.connect(self._on_scan_done)
        self._worker.diagnostic_done.connect(self._on_diagnostic_done)
        self._worker.failed.connect(self._on_failed)
        self._thread.finished.connect(self._on_thread_finished)

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)

        top = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(340)
        self.device_combo.setAccessibleName("Zařízení")
        self.device_combo.setAccessibleDescription(
            "Vyber, který telefon bude diagnostikován. Šipky nahoru a dolů, Enter potvrdí.")
        self.refresh_button = QPushButton("Obnovit seznam")
        self.refresh_button.setAccessibleDescription(
            "Znovu načte telefony připojené k počítači.")
        self.diagnose_button = QPushButton("Spustit diagnostiku")
        self.diagnose_button.setAccessibleDescription(
            "Spustí read-only diagnostiku vybraného telefonu.")
        top.addWidget(self.device_combo, 1)
        top.addWidget(self.refresh_button)
        top.addWidget(self.diagnose_button)
        layout.addLayout(top)

        self.ident_group = self._make_table("Identifikace zařízení", "ident_table")
        self.services_group = self._make_table("Služby přístupnosti", "services_table")
        layout.addWidget(self.ident_group)
        layout.addWidget(self.services_group)

        self._status_label = QLabel("Zpracovávám…")
        self._status_label.setAccessibleName("Stav")
        bar = QHBoxLayout()
        bar.addStretch(1)
        bar.addWidget(self._status_label)
        status_bar = QStatusBar()
        status_bar.setLayout(bar)
        self.setStatusBar(status_bar)

        self.setCentralWidget(central)
        self.setTabOrder(self.device_combo, self.refresh_button)
        self.setTabOrder(self.refresh_button, self.diagnose_button)
        self.setTabOrder(self.diagnose_button, self.ident_table)
        self.setTabOrder(self.ident_table, self.services_table)
        self.resize(760, 640)

        self.refresh_button.clicked.connect(self.refresh_clicked)
        self.diagnose_button.clicked.connect(self.diagnose_clicked)
        self.device_combo.currentIndexChanged.connect(self._on_combo_changed)

    def _make_table(self, title: str, attr: str) -> QWidget:
        table = QTableWidget(0, 2)
        table.setAccessibleName(title)
        table.setHorizontalHeaderLabels(["Položka", "Stav"])
        table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        group = QGroupBox(title)
        g_layout = QVBoxLayout()
        g_layout.addWidget(table)
        group.setLayout(g_layout)
        setattr(self, attr, table)
        return group

    def _set_status(self, text: str) -> None:
        if self._status_label.text() == text:
            return
        self._status_label.setText(text)

    # -------------------------------------------------------------- akce

    def refresh_clicked(self) -> None:
        if self._busy:
            return
        self._set_status("Zpracovávám…")
        self.scan_requested.emit()

    def diagnose_clicked(self) -> None:
        if self._busy:
            return
        serial = self.device_combo.currentData()
        if not serial:
            self._set_status("Vyber zařízení.")
            return
        self._set_status("Zpracovávám…")
        self.diagnose_requested.emit(serial)

    def _on_combo_changed(self, _index: int) -> None:
        if self._busy:
            return
        serial = self.device_combo.currentData()
        if serial:
            self._set_status(f"Vybráno: {serial}")
            self.diagnose_button.setEnabled(
                any(d.serial == serial and d.is_ready for d in self._devices))
        else:
            self.diagnose_button.setEnabled(False)
            self._set_status("Zařízení není vybráno.")

    # ----------------------------------------------------------- sloty

    def _on_started(self) -> None:
        self._busy = True
        self.refresh_button.setEnabled(False)
        self.diagnose_button.setEnabled(False)

    def _on_scan_done(self, selection: DeviceSelection) -> None:
        self._busy = False
        self.refresh_button.setEnabled(True)
        self._devices = list(selection.devices)
        self._populate_combo(selection)

    def _on_diagnostic_done(self, report: DiagnosticReport) -> None:
        self._busy = False
        self.refresh_button.setEnabled(True)
        serial = self.device_combo.currentData()
        self.diagnose_button.setEnabled(
            bool(serial and any(d.serial == serial and d.is_ready for d in self._devices)))

        focus_before = self.focusWidget()
        ident_rows = _ident_rows(report)
        service_rows = _service_rows(report)
        ident_sig = repr(ident_rows)
        service_sig = repr(service_rows)
        changed = False
        if ident_sig != self._ident_sig:
            self._fill_table(self.ident_table, ident_rows)
            self._ident_sig = ident_sig
            changed = True
        if service_sig != self._service_sig:
            self._fill_table(self.services_table, service_rows)
            self._service_sig = service_sig
            changed = True
        self._set_status("Pronto. Diagnostika hotova.")
        if changed and focus_before is self.diagnose_button:
            self.ident_table.setFocus()
            self.ident_table.setCurrentCell(0, 0)

    def _on_failed(self, message: str, kind: str) -> None:
        self._busy = False
        self.refresh_button.setEnabled(True)
        serial = self.device_combo.currentData()
        self.diagnose_button.setEnabled(
            bool(serial and any(d.serial == serial and d.is_ready for d in self._devices)))
        if self._closing:
            self._set_status("Zavírám…")
            return
        if kind == "cancelled":
            self._set_status("Zrušeno.")
            return
        show_error_dialog(self, message, kind)
        self._set_status("Chyba.")

    # ---------------------------------------------------- close / thread

    def closeEvent(self, event) -> None:
        if self._thread.isRunning():
            event.ignore()
            self._closing = True
            self._worker.request_cancel()
            self._thread.requestInterruption()
            self._thread.quit()
            return
        # QThread je už ukončené; zavření přijmeme.

    def _on_thread_finished(self) -> None:
        if self._closing:
            self.close()

    # ------------------------------------------------------------- tabulky

    def _populate_combo(self, selection: DeviceSelection) -> None:
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self.device_combo.addItem("— zvol telefon —", None)
        for dev in selection.devices:
            self.device_combo.addItem(f"{dev.serial}  ({dev.state})", dev.serial)
        if selection.selected_serial is not None:
            idx = self.device_combo.findData(selection.selected_serial)
            if idx >= 0:
                self.device_combo.setCurrentIndex(idx)
        else:
            self.device_combo.setCurrentIndex(0)
        self.device_combo.blockSignals(False)
        self._on_combo_changed(self.device_combo.currentIndex())

    @staticmethod
    def _fill_table(table: QTableWidget, rows: list[tuple[str, str, str]]) -> None:
        table.setRowCount(len(rows))
        for row, (label, value, desc) in enumerate(rows):
            item_label = QTableWidgetItem(label)
            item_label.setData(_ITEM_TEXT, label)
            item_label.setData(_ITEM_DESC, desc)
            item_value = QTableWidgetItem(value)
            item_value.setData(_ITEM_TEXT, value)
            item_value.setData(_ITEM_DESC, desc)
            table.setItem(row, 0, item_label)
            table.setItem(row, 1, item_value)
        for col in (0, 1):
            header = table.horizontalHeaderItem(col)
            if header is not None:
                header.setData(_ITEM_TEXT, header.text())
                header.setData(_ITEM_DESC, "Sloupec: " + header.text())
