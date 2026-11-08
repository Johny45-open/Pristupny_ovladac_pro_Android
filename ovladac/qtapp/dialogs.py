"""Přístupné dialogové pomůcky.

run_dialog() vždy zachová widget, který měl před otevřením dialogu
fokus, a po zavření dialogu ho obnoví – NVDA se tak vrátí
na stejné místo.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QMessageBox,
    QWidget,
)


def run_dialog(parent: QWidget, dialog: QDialog) -> int:
    """Spustí dialog modálně a po zavření obnoví předchozí fokus.

    Vrací výsledek exec() dialogu (např. DialogCode.Accepted).
    """
    previous = parent.focusWidget()
    result = dialog.exec()
    if previous is not None and previous.isVisible():
        previous.setFocus()
    return result


def make_message(
    title: str,
    text: str,
    informative: str = "",
    icon: QMessageBox.Icon = QMessageBox.Icon.Critical,
    buttons: QMessageBox.StandardButtons = QMessageBox.StandardButton.Ok,
) -> QMessageBox:
    box = QMessageBox()
    box.setWindowTitle(title)
    box.setIcon(icon)
    box.setText(title)
    box.setInformativeText(text)
    if informative:
        box.setDetailedText(informative)
    box.setStandardButtons(buttons)
    box.setDefaultButton(QMessageBox.StandardButton.Ok)
    return box


def show_error_dialog(parent: QWidget, message: str, kind: str) -> QMessageBox.StandardButton:
    """Standardní chybový dialog dle druhu chyby workeru.

    Druhy: cancelled, no_device, ambiguous, timeout, adb, other.
    """
    icon = QMessageBox.Icon.Critical
    title = "Chyba"
    text = message
    buttons = QMessageBox.StandardButton.Ok

    if kind == "cancelled":
        title = "Zrušeno"
        text = "Diagnostika byla zrušena dle požadavku."
        icon = QMessageBox.Icon.Information
    elif kind == "no_device":
        title = "Zařízení nedostupné"
        text = (
            "Zařízení není v stavu 'device', nebo už není v seznamu.\n"
            "Zkontrolujte USB kabel, stav USB ladění a potvrzení RSA klíče v telefonu."
        )
        icon = QMessageBox.Icon.Warning
    elif kind == "ambiguous":
        title = "Více zařízení"
        text = "Připojeno je více telefonů. Vyberte, který diagnostikovat."
        icon = QMessageBox.Icon.Warning
    elif kind == "timeout":
        title = "Časový limit"
        text = "Telefon neodpověděl. Zkontrolujte připojení a stav USB ladění."
        icon = QMessageBox.Icon.Warning
    elif kind == "other":
        icon = QMessageBox.Icon.Critical

    box = make_message(
        title,
        text,
        informative=message,
        icon=icon,
        buttons=buttons,
    )
    return QMessageBox.StandardButton(run_dialog(parent, box))
