"""PySide6-Hauptfenster: Verbindungsstatus (seriell/Webapp/Sicherung),
Einstellungsdialog und Live-Liste der letzten Ereignisse - bewusst auch
ohne Netzverbindung nutzbar, damit vor Ort sichtbar bleibt, dass die
Zeitmessung läuft, selbst wenn der Sync gerade nicht durchkommt."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from . import datenbank, einstellungen as einstellungen_modul
from .seriell_worker import SeriellWorker
from .sicherung import SicherungWorker
from .sync_worker import SyncWorker


class EinstellungenDialog(QDialog):
    def __init__(self, aktuelle: einstellungen_modul.Einstellungen, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self._felder: dict[str, QLineEdit | QSpinBox] = {}

        layout = QFormLayout(self)
        self._feld_hinzufuegen(layout, "com_port", "COM-Port", aktuelle.com_port)
        self._feld_hinzufuegen(layout, "baudrate", "Baudrate", aktuelle.baudrate)
        self._feld_hinzufuegen(layout, "webapp_url", "Webapp-URL", aktuelle.webapp_url)
        self._feld_hinzufuegen(layout, "api_key", "API-Key", aktuelle.api_key)
        self._feld_hinzufuegen(layout, "instance_name", "Instanzname", aktuelle.instance_name)
        self._feld_hinzufuegen(layout, "sync_intervall_s", "Sync-Intervall (s)",
                               aktuelle.sync_intervall_s)
        self._feld_hinzufuegen(layout, "backup_intervall_min", "Backup-Intervall (Min)",
                               aktuelle.backup_intervall_min)
        self._feld_hinzufuegen(layout, "backup_ordner", "Backup-Ordner", aktuelle.backup_ordner)

        knopfzeile = QHBoxLayout()
        speichern_knopf = QPushButton("Speichern")
        speichern_knopf.clicked.connect(self.accept)
        abbrechen_knopf = QPushButton("Abbrechen")
        abbrechen_knopf.clicked.connect(self.reject)
        knopfzeile.addWidget(speichern_knopf)
        knopfzeile.addWidget(abbrechen_knopf)
        layout.addRow(knopfzeile)

    def _feld_hinzufuegen(self, layout: QFormLayout, name: str, beschriftung: str, wert) -> None:
        if isinstance(wert, int):
            feld = QSpinBox()
            feld.setRange(1, 86400)
            feld.setValue(wert)
        else:
            feld = QLineEdit(str(wert))
        self._felder[name] = feld
        layout.addRow(beschriftung, feld)

    def werte(self) -> dict:
        ergebnis = {}
        for name, feld in self._felder.items():
            ergebnis[name] = feld.value() if isinstance(feld, QSpinBox) else feld.text()
        return ergebnis


class Hauptfenster(QMainWindow):
    ereignis_empfangen = Signal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zeitmessung Siloplanen-Race – Desktop")
        self.resize(720, 480)

        self.einstellungen = einstellungen_modul.laden()
        self.db = datenbank.verbinden(self.einstellungen.db_pfad)

        self._seriell_worker: SeriellWorker | None = None
        self._sync_worker: SyncWorker | None = None
        self._sicherung_worker: SicherungWorker | None = None

        self._aufbauen()
        self.ereignis_empfangen.connect(self._auf_ereignis)
        self._worker_starten()

        self._aktualisierungs_timer = QTimer(self)
        self._aktualisierungs_timer.timeout.connect(self._status_aktualisieren)
        self._aktualisierungs_timer.start(1000)

    def _aufbauen(self) -> None:
        zentral = QWidget()
        self.setCentralWidget(zentral)
        layout = QVBoxLayout(zentral)

        statuszeile = QHBoxLayout()
        self.seriell_status_label = QLabel("Seriell: –")
        self.sync_status_label = QLabel("Webapp: –")
        self.sicherung_status_label = QLabel("Sicherung: –")
        for label in (self.seriell_status_label, self.sync_status_label,
                     self.sicherung_status_label):
            statuszeile.addWidget(label)
        einstellungen_knopf = QPushButton("Einstellungen…")
        einstellungen_knopf.clicked.connect(self._einstellungen_oeffnen)
        statuszeile.addWidget(einstellungen_knopf)
        layout.addLayout(statuszeile)

        self.ereignis_tabelle = QTableWidget(0, 3)
        self.ereignis_tabelle.setHorizontalHeaderLabels(["Bahn", "Empfangen", "Sync-Status"])
        self.ereignis_tabelle.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.ereignis_tabelle)

        self._tabelle_neu_laden()

    def _worker_starten(self) -> None:
        for worker in (self._seriell_worker, self._sync_worker, self._sicherung_worker):
            if worker is not None:
                worker.stoppen()

        self._seriell_worker = SeriellWorker(
            self.db, self.einstellungen.com_port, self.einstellungen.baudrate,
            auf_status_geaendert=lambda status: self.ereignis_empfangen.emit(status),
        )
        self._seriell_worker.start()

        self._sync_worker = SyncWorker(
            self.db, self.einstellungen.webapp_url, self.einstellungen.api_key,
            self.einstellungen.instance_name, self.einstellungen.sync_intervall_s,
        )
        self._sync_worker.start()

        self._sicherung_worker = SicherungWorker(
            self.einstellungen.db_pfad, self.einstellungen.backup_ordner,
            self.einstellungen.instance_name, self.einstellungen.backup_intervall_min,
        )
        self._sicherung_worker.start()

    def _einstellungen_oeffnen(self) -> None:
        dialog = EinstellungenDialog(self.einstellungen, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            werte = dialog.werte()
            werte["baudrate"] = int(werte["baudrate"])
            werte["sync_intervall_s"] = int(werte["sync_intervall_s"])
            werte["backup_intervall_min"] = int(werte["backup_intervall_min"])
            self.einstellungen = einstellungen_modul.Einstellungen(
                **{**self.einstellungen.als_dict(), **werte})
            einstellungen_modul.speichern(self.einstellungen)
            self._worker_starten()

    def _auf_ereignis(self, status: dict) -> None:
        if "verbunden" in status:
            self.seriell_status_label.setText(
                f"Seriell: {'verbunden' if status['verbunden'] else 'getrennt'}")
        if status.get("neues_ereignis"):
            self._tabelle_neu_laden()

    def _status_aktualisieren(self) -> None:
        ausstehend = datenbank.anzahl_ausstehend(self.db)
        self.sync_status_label.setText(f"Webapp: {ausstehend} ausstehend")

    def _tabelle_neu_laden(self) -> None:
        zeilen = datenbank.letzte_ereignisse(self.db, limit=50)
        self.ereignis_tabelle.setRowCount(len(zeilen))
        for row, zeile in enumerate(zeilen):
            self.ereignis_tabelle.setItem(row, 0, QTableWidgetItem(str(zeile["bahn"])))
            self.ereignis_tabelle.setItem(row, 1, QTableWidgetItem(zeile["empfangen_um"]))
            self.ereignis_tabelle.setItem(row, 2, QTableWidgetItem(zeile["sync_status"]))

    def closeEvent(self, event) -> None:
        for worker in (self._seriell_worker, self._sync_worker, self._sicherung_worker):
            if worker is not None:
                worker.stoppen()
        super().closeEvent(event)
