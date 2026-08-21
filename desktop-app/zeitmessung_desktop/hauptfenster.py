"""PySide6-Hauptfenster: Verbindungsstatus (seriell/Webapp/Sicherung),
Einstellungsdialog und Live-Liste der letzten Ereignisse - bewusst auch
ohne Netzverbindung nutzbar, damit vor Ort sichtbar bleibt, dass die
Zeitmessung läuft, selbst wenn der Sync gerade nicht durchkommt."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import datenbank, einstellungen as einstellungen_modul, licht_zustand
from .bahnbeleuchtung import Bahnbeleuchtung
from .seriell_ports import kollision_aufloesen, port_auswahl
from .lauf_import_worker import LaufImportWorker
from .lauf_worker import LaufWorker
from .seriell_worker import SeriellWorker
from .sicherung import SicherungWorker
from .sync_worker import SyncWorker


class EinstellungenDialog(QDialog):
    def __init__(self, aktuelle: einstellungen_modul.Einstellungen, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self._felder: dict[str, QLineEdit | QSpinBox | QComboBox] = {}

        layout = QFormLayout(self)
        self._seriell_port_feld_hinzufuegen(layout, "com_port",
                                            "COM-Port Mega (Zeitmessung)",
                                            aktuelle.com_port)
        self._feld_hinzufuegen(layout, "baudrate", "Baudrate", aktuelle.baudrate,
                               bereich=(1200, 2_000_000))
        self._seriell_port_feld_hinzufuegen(
            layout, "dmx_port",
            "COM-Port 2. Arduino (DMX-Bahnbeleuchtung, leer = aus)",
            aktuelle.dmx_port, leer_option=True)
        # Beide Port-Dropdowns gegenseitig synchronisieren - siehe
        # _ports_synchronisieren. Muss NACH dem Anlegen beider Felder
        # einmal laufen, damit eine in der gespeicherten Konfiguration
        # bereits vorhandene Kollision sofort aufgeloest wird.
        self._ports_synchronisieren()
        self._feld_hinzufuegen(layout, "webapp_url", "Webapp-URL", aktuelle.webapp_url)
        self._feld_hinzufuegen(layout, "api_key", "API-Key", aktuelle.api_key)
        self._feld_hinzufuegen(layout, "instance_name", "Instanzname", aktuelle.instance_name)
        self._feld_hinzufuegen(layout, "sync_intervall_s", "Sync-Intervall (s)",
                               aktuelle.sync_intervall_s, bereich=(1, 86400))
        self._feld_hinzufuegen(layout, "backup_intervall_min", "Backup-Intervall (Min)",
                               aktuelle.backup_intervall_min, bereich=(1, 86400))
        self._feld_hinzufuegen(layout, "backup_ordner", "Backup-Ordner", aktuelle.backup_ordner)

        knopfzeile = QHBoxLayout()
        speichern_knopf = QPushButton("Speichern")
        speichern_knopf.clicked.connect(self.accept)
        abbrechen_knopf = QPushButton("Abbrechen")
        abbrechen_knopf.clicked.connect(self.reject)
        knopfzeile.addWidget(speichern_knopf)
        knopfzeile.addWidget(abbrechen_knopf)
        layout.addRow(knopfzeile)

    def _feld_hinzufuegen(self, layout: QFormLayout, name: str, beschriftung: str, wert,
                          bereich: tuple[int, int] = (1, 86400)) -> None:
        if isinstance(wert, int):
            feld = QSpinBox()
            feld.setRange(*bereich)
            feld.setValue(wert)
        else:
            feld = QLineEdit(str(wert))
        self._felder[name] = feld
        layout.addRow(beschriftung, feld)

    def _seriell_port_feld_hinzufuegen(self, layout: QFormLayout, feld_name: str,
                                       beschriftung: str, wert: str,
                                       leer_option: bool = False) -> None:
        """Dropdown der aktuell erkannten seriellen Schnittstellen, statt
        eines Freitextfelds - der COM-Port driftet bei USB-Neuerkennung
        erfahrungsgemaess haeufig (siehe firmware/*/platformio.ini). Bleibt
        trotzdem editierbar, falls das Geraet beim Oeffnen des Dialogs
        gerade nicht angeschlossen ist. Wiederverendet fuer Mega- UND
        DMX-Port - zwei unabhaengige Geraete, siehe bahnbeleuchtung.py.

        `leer_option` (nur fuer das DMX-Feld) fuegt einen auswaehlbaren
        leeren Eintrag ("aus/deaktiviert") hinzu. Beide Port-Dropdowns sind
        ueber _ports_synchronisieren gekoppelt: der in einem gewaehlte Port
        wird im anderen ausgeblendet, damit derselbe Arduino nicht beiden
        Geraeten zugeordnet wird (Mega + DMX-Uno sind beides CH340 und an
        den Ports nicht unterscheidbar - siehe AGENTS.md "DMX-Bahnbeleuchtung").
        """
        feld = QComboBox()
        feld.setEditable(True)
        self._felder[feld_name] = feld
        self._com_ports_aktualisieren(feld, wert, leer_option=leer_option)

        aktualisieren_knopf = QPushButton("⟳")
        aktualisieren_knopf.setToolTip("Schnittstellen neu einlesen")
        aktualisieren_knopf.setFixedWidth(28)
        # Gemeinsame Aktualisierung BEIDER Port-Dropdowns (siehe
        # _ports_synchronisieren) - neu eingelesene Ports und der
        # Kollisionsschutz greifen dann fuer beide gleichzeitig.
        aktualisieren_knopf.clicked.connect(self._ports_synchronisieren)
        # Bei jeder Aenderung den jeweils ANDEREN Port-Dropdown neu
        # aufbauen, damit derselbe Port nicht beiden Arduino-Geraeten
        # zugeordnet werden kann.
        feld.currentTextChanged.connect(self._ports_synchronisieren)

        zeile = QHBoxLayout()
        zeile.addWidget(feld, 1)
        zeile.addWidget(aktualisieren_knopf)
        layout.addRow(beschriftung, zeile)

    def _ports_synchronisieren(self) -> None:
        """Baut BEIDE Port-Dropdowns neu auf und blendet jeweils den im
        ANDEREN gewaehlten Port aus - verhindert, dass derselbe Arduino
        (Mega und DMX-Uno sind beides CH340, an den Ports nicht
        unterscheidbar) versehentlich beiden Geraeten zugeordnet und damit
        zweimal geoeffnet wird (Kollision, siehe AGENTS.md
        "DMX-Bahnbeleuchtung").

        Kollisionsaufloesung: derselbe Port darf nicht beiden Geraeten
        gehoeren. Der Mega (Zeitmessung) hat Vorrang - der DMX-Port wird
        in diesem Fall auf "" (aus) zurueckgesetzt. Bewusst nicht
        umgekehrt: die Zeitmessung ist pflicht, die Beleuchtung optional.
        """
        com_feld = self._felder.get("com_port")
        dmx_feld = self._felder.get("dmx_port")
        if com_feld is None or dmx_feld is None:
            return
        com_wert = com_feld.currentText().strip()
        dmx_wert = dmx_feld.currentText().strip()
        dmx_wert = kollision_aufloesen(com_wert, dmx_wert)
        if dmx_wert != dmx_feld.currentText().strip():
            dmx_feld.blockSignals(True)
            dmx_feld.setCurrentText(dmx_wert)
            dmx_feld.blockSignals(False)
        # Mega-Dropdown: DMX-Port ausblenden (ausser er ist gerade Megas
        # eigener Wert); DMX-Dropdown: Mega-Port ausblenden (ausser er ist
        # DMXs eigener Wert).
        self._com_ports_aktualisieren(com_feld, com_wert,
                                      gesperrt=({dmx_wert} - {com_wert}))
        self._com_ports_aktualisieren(dmx_feld, dmx_wert, leer_option=True,
                                      gesperrt=({com_wert} - {dmx_wert}))

    def _com_ports_aktualisieren(self, feld: QComboBox, aktueller_wert: str,
                                 *, leer_option: bool = False,
                                 gesperrt: set[str] | None = None) -> None:
        """Füllt das Dropdown neu. Die eigentliche Eintrags-Logik liegt
        Qt-frei in seriell_ports.port_auswahl (dort getestet); hier nur
        noch das Anwenden auf die ComboBox - blockSignals verhindert
        Rekursion ueber currentTextChanged → _ports_synchronisieren."""
        feld.blockSignals(True)
        feld.clear()
        feld.addItems(port_auswahl(aktueller_wert, leer_option=leer_option,
                                   gesperrt=gesperrt))
        feld.setCurrentText(aktueller_wert)
        feld.blockSignals(False)

    def werte(self) -> dict:
        ergebnis = {}
        for name, feld in self._felder.items():
            if isinstance(feld, QSpinBox):
                ergebnis[name] = feld.value()
            elif isinstance(feld, QComboBox):
                ergebnis[name] = feld.currentText()
            else:
                ergebnis[name] = feld.text()
        return ergebnis


class Hauptfenster(QMainWindow):
    ereignis_empfangen = Signal(dict)
    lauf_aktualisiert = Signal(dict)
    lauf_status_geaendert = Signal(dict)

    # Start-Fenster: nach der ersten Kontaktausloesung haben andere
    # Bahnen diese Zeit, um ihren eigenen 1. Kontakt zu setzen. Danach
    # wird fehlenden Bahnen automatisch der 1. Kontakt gesetzt (mit dem
    # Zeitpunkt des ersten Kontakts) – verhindert taktisches Nicht-Ausloesen.
    START_FENSTER_SEKUNDEN = 5.0

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zeitmessung Siloplanen-Race – Desktop")
        self.resize(760, 820)
        self._start_fenster_aktiv = False
        self._start_fenster_zeitpunkt = None

        self.einstellungen = einstellungen_modul.laden()
        self.db = datenbank.verbinden(self.einstellungen.db_pfad)

        self._seriell_worker: SeriellWorker | None = None
        self._sync_worker: SyncWorker | None = None
        self._sicherung_worker: SicherungWorker | None = None
        self._lauf_worker: LaufWorker | None = None
        self._lauf_import_worker: LaufImportWorker | None = None

        # Bahnbeleuchtung (DMX) - optional, siehe bahnbeleuchtung.py und
        # licht_zustand.py. self._letzter_server_lauf haelt die zuletzt von
        # /notfall/api/aktiv gemeldeten Rohdaten, damit _beleuchtung_
        # aktualisieren() sie mit dem lokalen Kontakt-Zaehler kombinieren
        # kann, ohne dass lauf_worker.py selbst etwas ueber Licht wissen muss.
        self.beleuchtung: Bahnbeleuchtung | None = None
        self._letzter_server_lauf: dict | None = None
        self._beleuchtung_starten()

        self._aufbauen()
        self.ereignis_empfangen.connect(self._auf_ereignis)
        self.lauf_aktualisiert.connect(self._lauf_anzeigen)
        self.lauf_status_geaendert.connect(self._lauf_status_anzeigen)
        self._worker_starten()

        self._aktualisierungs_timer = QTimer(self)
        self._aktualisierungs_timer.timeout.connect(self._status_aktualisieren)
        self._aktualisierungs_timer.start(1000)

        self._start_fenster_timer = QTimer(self)
        self._start_fenster_timer.setSingleShot(True)
        self._start_fenster_timer.timeout.connect(self._start_fenster_abgelaufen)

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
        loeschen_knopf = QPushButton("Alle löschen")
        loeschen_knopf.clicked.connect(self._alle_loeschen)
        statuszeile.addWidget(loeschen_knopf)
        layout.addLayout(statuszeile)

        zustandszeile = QHBoxLayout()
        zustandszeile.addWidget(QLabel("Live-Zustand:"))
        self.zustand_labels: list[QLabel] = []
        for bahn in range(1, 5):
            label = QLabel(f"Bahn {bahn}: –")
            label.setMinimumWidth(110)
            self.zustand_labels.append(label)
            zustandszeile.addWidget(label)
        zustandszeile.addStretch()
        layout.addLayout(zustandszeile)

        lauf_kopfzeile = QHBoxLayout()
        self.lauf_label = QLabel("Aktiver Lauf: –")
        self.lauf_status_label = QLabel("Lauf-Abfrage: –")
        lauf_kopfzeile.addWidget(self.lauf_label)
        lauf_kopfzeile.addWidget(self.lauf_status_label)
        lauf_kopfzeile.addStretch()
        layout.addLayout(lauf_kopfzeile)

        self.lauf_tabelle = QTableWidget(0, 4)
        self.lauf_tabelle.setHorizontalHeaderLabels(
            ["Bahn", "Team", "Läuferzeiten (s, ms)", "Summe"])
        self.lauf_tabelle.horizontalHeader().setStretchLastSection(True)
        self.lauf_tabelle.setMaximumHeight(160)
        layout.addWidget(self.lauf_tabelle)

        # Gemeinsamer Start: 1. Kontakt fuer alle 4 Bahnen gleichzeitig
        start_box = QGroupBox("Gemeinsamer Start (Startrichter-Startkommando)")
        start_layout = QHBoxLayout(start_box)
        self.gemeinsamer_start_knopf = QPushButton("🏁 GEMEINSAMER START\n(1. Kontakt fuer alle 4 Bahnen)")
        self.gemeinsamer_start_knopf.setMinimumHeight(55)
        self.gemeinsamer_start_knopf.setStyleSheet(
            "font-size: 1.1rem; font-weight: bold; "
            "background-color: #2e7d32; color: white; border: 2px solid #1b5e20;")
        self.gemeinsamer_start_knopf.clicked.connect(self._gemeinsamer_start)
        start_layout.addWidget(self.gemeinsamer_start_knopf)
        layout.addWidget(start_box)

        # Manuelle Tasten (Fallback wenn Hardware-Kontakt aussetzt)
        manuell_tasten_box = QGroupBox("Manuelle Zeitnahme (pro Bahn)")
        manuell_tasten_layout = QVBoxLayout(manuell_tasten_box)
        start_zeile = QHBoxLayout()
        stopp_zeile = QHBoxLayout()
        start_label = QLabel("START (1. Kontakt)")
        start_label.setStyleSheet("font-weight: bold; color: #1a7a1a;")
        stopp_label = QLabel("STOPP (letzer Kontakt)")
        stopp_label.setStyleSheet("font-weight: bold; color: #b30000;")
        start_zeile.addWidget(start_label)
        stopp_zeile.addWidget(stopp_label)
        self.stopp_knoepfe: list[QPushButton] = []
        self.start_knoepfe: list[QPushButton] = []
        for bahn in range(1, 5):
            # START Button (gruen)
            start_knopf = QPushButton(f"Bahn {bahn}\nSTART")
            start_knopf.setMinimumHeight(50)
            start_knopf.setStyleSheet(
                "font-size: 1rem; font-weight: bold; "
                "background-color: #4caf50; color: white;")
            start_knopf.clicked.connect(
                lambda checked=False, b=bahn: self._manuelles_event(b))
            self.start_knoepfe.append(start_knopf)
            start_zeile.addWidget(start_knopf)
            # STOPP Button (rot)
            stopp_knopf = QPushButton(f"Bahn {bahn}\nSTOPP")
            stopp_knopf.setMinimumHeight(50)
            stopp_knopf.setStyleSheet(
                "font-size: 1rem; font-weight: bold; "
                "background-color: #f44336; color: white;")
            stopp_knopf.clicked.connect(
                lambda checked=False, b=bahn: self._manuelles_event(b))
            self.stopp_knoepfe.append(stopp_knopf)
            stopp_zeile.addWidget(stopp_knopf)
        start_zeile.addStretch()
        stopp_zeile.addStretch()
        manuell_tasten_layout.addLayout(start_zeile)
        manuell_tasten_layout.addLayout(stopp_zeile)

        # Notfall-Stopp: bricht den kompletten Lauf ab (Verletzung etc.)
        abort_zeile = QHBoxLayout()
        self.abort_knopf = QPushButton("🚨 LAUF ABBRECHEN (Notfall / Verletzung)")
        self.abort_knopf.setMinimumHeight(50)
        self.abort_knopf.setStyleSheet(
            "font-size: 1.1rem; font-weight: bold; "
            "background-color: #d32f2f; color: white; border: 2px solid #b71c1c;")
        self.abort_knopf.clicked.connect(self._lauf_abbrechen)
        abort_zeile.addWidget(self.abort_knopf)
        manuell_tasten_layout.addLayout(abort_zeile)
        layout.addWidget(manuell_tasten_box)

        manuell_box = QGroupBox("Manueller Modus (offline, ohne Webapp-Verbindung)")
        manuell_layout = QVBoxLayout(manuell_box)
        eingabe_zeile = QHBoxLayout()
        self.team_nummer_felder: list[QLineEdit] = []
        for bahn in range(1, 5):
            eingabe_zeile.addWidget(QLabel(f"Bahn {bahn} Team-Nr.:"))
            feld = QLineEdit()
            feld.setMaximumWidth(60)
            feld.setPlaceholderText("–")
            self.team_nummer_felder.append(feld)
            eingabe_zeile.addWidget(feld)
        start_knopf = QPushButton("Lokalen Lauf starten")
        start_knopf.clicked.connect(self._lokalen_lauf_starten)
        eingabe_zeile.addWidget(start_knopf)
        eingabe_zeile.addStretch()
        manuell_layout.addLayout(eingabe_zeile)

        self.lokaler_lauf_label = QLabel("Kein lokaler Lauf aktiv.")
        manuell_layout.addWidget(self.lokaler_lauf_label)

        self.lokale_lauf_tabelle = QTableWidget(0, 4)
        self.lokale_lauf_tabelle.setHorizontalHeaderLabels(
            ["Bahn", "Team-Nr.", "Läuferzeiten (s, ms)", "Sync"])
        self.lokale_lauf_tabelle.horizontalHeader().setStretchLastSection(True)
        self.lokale_lauf_tabelle.setMaximumHeight(120)
        manuell_layout.addWidget(self.lokale_lauf_tabelle)
        layout.addWidget(manuell_box)

        self.ereignis_tabelle = QTableWidget(0, 3)
        self.ereignis_tabelle.setHorizontalHeaderLabels(["Bahn", "Empfangen", "Sync-Status"])
        self.ereignis_tabelle.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.ereignis_tabelle)

        self._tabelle_neu_laden()

    def _worker_starten(self) -> None:
        for worker in (self._seriell_worker, self._sync_worker, self._sicherung_worker,
                      self._lauf_worker, self._lauf_import_worker):
            if worker is not None:
                worker.stoppen()

        self._seriell_worker = SeriellWorker(
            self.db, self.einstellungen.com_port, self.einstellungen.baudrate,
            auf_status_geaendert=lambda status: self.ereignis_empfangen.emit(status),
            auf_event_verarbeitet=lambda bahn: self._arduino_event_verarbeitet(bahn),
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

        self._lauf_worker = LaufWorker(
            self.einstellungen.webapp_url, self.einstellungen.api_key,
            self.einstellungen.sync_intervall_s,
            auf_lauf_aktualisiert=lambda daten: self.lauf_aktualisiert.emit(daten),
            auf_status_geaendert=lambda status: self.lauf_status_geaendert.emit(status),
        )
        self._lauf_worker.start()

        self._lauf_import_worker = LaufImportWorker(
            self.db, self.einstellungen.webapp_url, self.einstellungen.api_key,
            self.einstellungen.sync_intervall_s,
        )
        self._lauf_import_worker.start()

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
            self._beleuchtung_starten()

    def _beleuchtung_starten(self) -> None:
        """(Neu-)Verbindet die Bahnbeleuchtung, falls ein Port eingetragen
        ist - wird beim Start UND nach jeder Einstellungsaenderung
        aufgerufen (der Port kann sich aendern). Fehlt der Port oder ist er
        nicht erreichbar, bleibt self.beleuchtung nutzbar (verbunden=False),
        alle Aufrufe werden dann folgenlos ignoriert - siehe
        bahnbeleuchtung.py."""
        if self.beleuchtung is not None:
            self.beleuchtung.schliessen()
            self.beleuchtung = None
        if self.einstellungen.dmx_port:
            self.beleuchtung = Bahnbeleuchtung(self.einstellungen.dmx_port)
            self._beleuchtung_aktualisieren()

    def _beleuchtung_aktualisieren(self) -> None:
        """Leitet aus dem aktuellen Lauf-Zustand (lokal priorisiert, siehe
        unten) den Beleuchtungs-Zustand ab und setzt ihn, falls er sich
        geaendert hat. Wird nach jedem Server- ODER Lokal-Lauf-Update sowie
        direkt nach jedem verarbeiteten Kontaktereignis aufgerufen, damit
        der Uebergang zu "start" ohne spuerbare Verzoegerung kommt."""
        if self.beleuchtung is None:
            return
        lokaler_lauf = datenbank.aktiver_lokaler_lauf(self.db)
        if lokaler_lauf is not None:
            # Lokaler Offline-Modus hat Vorrang: er existiert nur, wenn der
            # Server gerade NICHT erreichbar ist (siehe README "Manueller
            # Modus") - die Lichter sollen auch dann sinnvoll reagieren.
            aktiviert_um = lokaler_lauf["aktiviert_um"]
            zustand = licht_zustand.zustand_bestimmen(
                lauf_aktiv=True, aktiviert=True,
                hat_kontakt=self._hat_kontakt_seit(aktiviert_um))
        elif self._letzter_server_lauf and self._letzter_server_lauf.get("aktiv"):
            aktiviert_um = self._letzter_server_lauf.get("aktiviert_um")
            zustand = licht_zustand.zustand_bestimmen(
                lauf_aktiv=True, aktiviert=aktiviert_um is not None,
                hat_kontakt=bool(aktiviert_um) and self._hat_kontakt_seit(aktiviert_um))
        else:
            zustand = licht_zustand.zustand_bestimmen(False, False, False)
        if zustand != self.beleuchtung.zustand:
            self.beleuchtung.zustand_setzen(zustand)

    def _hat_kontakt_seit(self, aktiviert_um: str) -> bool:
        """Nutzt denselben lokalen Ereignis-Puffer wie _partial_zeiten/
        _start_fenster_pruefen - Ereignisse landen dort unabhaengig davon,
        ob sie vom Mega, manuell oder ueber den gemeinsamen Start kommen,
        daher keine separate Buchfuehrung noetig."""
        zeile = self.db.execute(
            "SELECT COUNT(*) AS n FROM ereignis WHERE empfangen_um >= ?",
            (aktiviert_um,),
        ).fetchone()
        return zeile["n"] > 0

    def _auf_ereignis(self, status: dict) -> None:
        if "verbunden" in status:
            self.seriell_status_label.setText(
                f"Seriell: {'verbunden' if status['verbunden'] else 'getrennt'}")
        if status.get("neues_ereignis"):
            self._tabelle_neu_laden()
        if status.get("zustaende") is not None:
            self._zustaende_anzeigen(status["zustaende"])

    def _zustaende_anzeigen(self, zustaende: list[int]) -> None:
        for bahn0, (label, zustand) in enumerate(zip(self.zustand_labels, zustaende)):
            bahn = bahn0 + 1
            if zustand:
                label.setText(f"Bahn {bahn}: AUSGELÖST")
                label.setStyleSheet("color: #b30000; font-weight: bold;")
            else:
                label.setText(f"Bahn {bahn}: bereit")
                label.setStyleSheet("color: #1a7a1a;")

    def _lauf_anzeigen(self, daten: dict) -> None:
        self._letzter_server_lauf = daten
        self._beleuchtung_aktualisieren()
        if not daten.get("aktiv"):
            self.lauf_label.setText("Aktiver Lauf: –")
            self.lauf_tabelle.setRowCount(0)
            return
        self.lauf_label.setText(f"Aktiver Lauf: {daten.get('bezeichnung') or daten['lauf_id']}")
        aktiviert_um = daten.get("aktiviert_um")
        bahnen = daten.get("bahnen", [])
        self.lauf_tabelle.setRowCount(len(bahnen))
        for row, bahn in enumerate(bahnen):
            bahn_nr = bahn["bahn_nr"]
            # Server-Zeiten (komplett wenn alle 5 Events da)
            server_zeiten = {l["nummer"]: l["zeit"] for l in bahn.get("laeufer", []) if l["zeit"] is not None}
            # Lokale Zwischenzeiten aus Events seit Lauf-Start
            lokale_zeiten = {}
            kontakt_count = 0
            if aktiviert_um:
                lokale_zeiten, kontakt_count = self._partial_zeiten(bahn_nr, aktiviert_um)
            zeiten_text = "  ".join(
                (f"L{l['nummer']}: {lokale_zeiten.get(l['nummer'], l['zeit']):.3f}"
                 if l["nummer"] in lokale_zeiten or l["zeit"] is not None
                 else f"L{l['nummer']}: –")
                for l in bahn.get("laeufer", [])
            )
            summe = bahn.get("gesamtzeit")
            if summe is not None:
                summe_text = f"{summe:.3f} s"
            elif lokale_zeiten:
                summe_text = f"{sum(lokale_zeiten.values()):.3f} s *"
            else:
                summe_text = "–"
            # Kontakt-Zaehler anzeigen
            kontakt_info = f"({kontakt_count}/5)" if kontakt_count > 0 else ""
            self.lauf_tabelle.setItem(row, 0, QTableWidgetItem(f"Bahn {bahn_nr} {kontakt_info}"))
            self.lauf_tabelle.setItem(row, 1, QTableWidgetItem(bahn.get("team_name") or "–"))
            self.lauf_tabelle.setItem(row, 2, QTableWidgetItem(zeiten_text or "–"))
            self.lauf_tabelle.setItem(row, 3, QTableWidgetItem(summe_text))

    def _partial_zeiten(self, bahn: int, aktiviert_um: str) -> tuple[dict, int]:
        """Berechnet Zwischenzeiten aus lokalen Events seit Lauf-Start.
        Liefert (zeiten_dict, kontakt_count). zeiten_dict = {laeufer_nr: sekunden}.
        Nach 2 Events: L1 fertig; nach 3: L1+L2; nach 4: L1+L2+L3; nach 5: alle."""
        from datetime import datetime
        zeilen = self.db.execute(
            "SELECT empfangen_um FROM ereignis WHERE bahn = ? AND empfangen_um >= ? "
            "ORDER BY id ASC LIMIT 5",
            (bahn, aktiviert_um),
        ).fetchall()
        n = len(zeilen)
        if n < 2:
            return {}, n
        zeitstempel = [datetime.fromisoformat(z["empfangen_um"]) for z in zeilen]
        zeiten = {}
        for i in range(min(n - 1, 4)):
            delta = (zeitstempel[i + 1] - zeitstempel[i]).total_seconds()
            zeiten[i + 1] = delta
        return zeiten, n

    def _lauf_status_anzeigen(self, status: dict) -> None:
        jetzt = datetime.now().strftime("%H:%M:%S")
        if status.get("erfolgreich"):
            self.lauf_status_label.setText(f"Lauf-Abfrage: OK ({jetzt})")
            self.lauf_status_label.setStyleSheet("")
        else:
            grund = status.get("fehler") or f"HTTP {status.get('status_code')}"
            self.lauf_status_label.setText(f"Lauf-Abfrage: Fehler ({jetzt}) – {grund}")
            self.lauf_status_label.setStyleSheet("color: #b30000;")

    def _alle_loeschen(self) -> None:
        """Löscht NUR den lokalen Puffer (z.B. nach einem Testlauf) - bereits
        synchronisierte Ereignisse in der Webapp-Datenbank bleiben davon
        unberührt, dafür den Knopf unter /zeitmessung/ in der Webapp
        verwenden."""
        antwort = QMessageBox.question(
            self, "Alle löschen",
            "Wirklich ALLE lokal gepufferten Ereignisse löschen?\n"
            "Betrifft nur diesen Rechner, nicht die Webapp-Datenbank.",
        )
        if antwort != QMessageBox.StandardButton.Yes:
            return
        anzahl = datenbank.alle_loeschen(self.db)
        self._tabelle_neu_laden()
        QMessageBox.information(self, "Alle löschen", f"{anzahl} Ereignis(se) gelöscht.")

    def _lokalen_lauf_starten(self) -> None:
        """Startet einen Lauf OHNE Webapp-Verbindung: Team-Nummern werden
        eingetippt statt aus der Webapp geladen, die Zuordnung passiert
        lokal (siehe lokale_zuordnung.py). Wird automatisch in die Webapp
        nachgereicht, sobald sie wieder erreichbar ist (siehe
        lauf_import_worker.py)."""
        team_nummern = {
            bahn: feld.text().strip()
            for bahn, feld in enumerate(self.team_nummer_felder, start=1)
            if feld.text().strip()
        }
        if not team_nummern:
            QMessageBox.warning(self, "Lokalen Lauf starten",
                                "Bitte mindestens eine Team-Nummer eintragen.")
            return
        aktiviert_um = datetime.now(timezone.utc).isoformat()
        datenbank.lokalen_lauf_starten(
            self.db, bezeichnung=f"Offline {aktiviert_um}",
            team_nummern=team_nummern, aktiviert_um=aktiviert_um,
        )
        for feld in self.team_nummer_felder:
            feld.clear()
        self._lokalen_lauf_anzeigen()

    def _lokalen_lauf_anzeigen(self) -> None:
        lauf = datenbank.aktiver_lokaler_lauf(self.db)
        if lauf is None:
            self.lokaler_lauf_label.setText("Kein lokaler Lauf aktiv.")
            self.lokale_lauf_tabelle.setRowCount(0)
            return
        self.lokaler_lauf_label.setText(
            f"Lokaler Lauf seit {lauf['aktiviert_um']} "
            f"({'noch nicht' if lauf['sync_status'] == 'ausstehend' else 'bereits'} "
            f"an Webapp gemeldet)")
        bahnen = datenbank.lokale_bahnen(self.db, lauf["id"])
        self.lokale_lauf_tabelle.setRowCount(len(bahnen))
        for row, bahn in enumerate(bahnen):
            zeiten_text = "  ".join(
                f"L{i}: {bahn[f'zeit_laeufer{i}']:.3f}" if bahn[f"zeit_laeufer{i}"] is not None
                else f"L{i}: –"
                for i in range(1, 5)
            )
            self.lokale_lauf_tabelle.setItem(row, 0, QTableWidgetItem(str(bahn["bahn_nr"])))
            self.lokale_lauf_tabelle.setItem(row, 1, QTableWidgetItem(bahn["team_nummer"]))
            self.lokale_lauf_tabelle.setItem(row, 2, QTableWidgetItem(zeiten_text))
            self.lokale_lauf_tabelle.setItem(row, 3, QTableWidgetItem(lauf["sync_status"]))

    def _status_aktualisieren(self) -> None:
        ausstehend = datenbank.anzahl_ausstehend(self.db)
        self.sync_status_label.setText(f"Webapp: {ausstehend} ausstehend")
        self._lokalen_lauf_anzeigen()
        self._beleuchtung_aktualisieren()

    def _tabelle_neu_laden(self) -> None:
        zeilen = datenbank.letzte_ereignisse(self.db, limit=50)
        self.ereignis_tabelle.setRowCount(len(zeilen))
        for row, zeile in enumerate(zeilen):
            self.ereignis_tabelle.setItem(row, 0, QTableWidgetItem(str(zeile["bahn"])))
            self.ereignis_tabelle.setItem(row, 1, QTableWidgetItem(zeile["empfangen_um"]))
            self.ereignis_tabelle.setItem(row, 2, QTableWidgetItem(zeile["sync_status"]))

    def _event_verarbeiten(self, bahn: int, geraet_millis: int) -> None:
        """Zentrale Event-Verarbeitung fuer manuelle Kontakte: erzeugt ein
        Event, prueft das Start-Fenster und loest die Zuordnung aus."""
        from .lokale_zuordnung import zuordnung_pruefen
        empfangen_um = datetime.now(timezone.utc).isoformat()
        datenbank.ereignis_hinzufuegen(
            self.db, bahn=bahn, geraet_millis=geraet_millis,
            empfangen_um=empfangen_um, client_event_id=uuid.uuid4().hex,
        )
        zuordnung_pruefen(self.db, bahn)
        self._start_fenster_pruefen(empfangen_um)
        self._tabelle_neu_laden()
        self._auf_ereignis({"neues_ereignis": {"bahn": bahn},
                           "zustaende": [0, 0, 0, 0]})
        if self.beleuchtung is not None:
            self.beleuchtung.blitzen(bahn)
        self._beleuchtung_aktualisieren()

    def _start_fenster_pruefen(self, empfangen_um: str) -> None:
        """Prueft ob das Start-Fenster gestartet werden muss (1. Kontakt
        fuer den aktiven Lauf). Wird sowohl von manuellen als auch von
        Arduino-Events aufgerufen."""
        if not self._start_fenster_aktiv:
            lauf = datenbank.aktiver_lokaler_lauf(self.db)
            if lauf is not None:
                count = self.db.execute(
                    "SELECT COUNT(*) AS n FROM ereignis WHERE empfangen_um >= ?",
                    (lauf["aktiviert_um"],),
                ).fetchone()["n"]
                if count == 1:
                    self._start_fenster_aktiv = True
                    self._start_fenster_zeitpunkt = empfangen_um
                    self._start_fenster_timer.start(
                        int(self.START_FENSTER_SEKUNDEN * 1000))

    def _arduino_event_verarbeitet(self, bahn: int) -> None:
        """Callback vom SeriellWorker: Arduino hat bereits Event+Zuordnung
        erledigt, wir muessen nur das Start-Fenster pruefen und ggf. die
        Bahnbeleuchtung blitzen lassen/aktualisieren."""
        empfangen_um = datetime.now(timezone.utc).isoformat()
        self._start_fenster_pruefen(empfangen_um)
        if self.beleuchtung is not None:
            self.beleuchtung.blitzen(bahn)
        self._beleuchtung_aktualisieren()

    def _start_fenster_abgelaufen(self) -> None:
        """Wenn das Start-Fenster ablaeuft: alle Bahnen, die noch 0 Kontakte
        haben, bekommen automatisch den 1. Kontakt mit dem Zeitpunkt des
        ersten Kontakts gesetzt. Verhindert taktisches Nicht-Ausloesen."""
        from .lokale_zuordnung import zuordnung_pruefen
        lauf = datenbank.aktiver_lokaler_lauf(self.db)
        if lauf is None or not self._start_fenster_zeitpunkt:
            self._start_fenster_aktiv = False
            return
        start_zeit = self._start_fenster_zeitpunkt
        for bahn in range(1, 5):
            count = self.db.execute(
                "SELECT COUNT(*) AS n FROM ereignis "
                "WHERE bahn = ? AND empfangen_um >= ?",
                (bahn, lauf["aktiviert_um"]),
            ).fetchone()["n"]
            if count == 0:
                datenbank.ereignis_hinzufuegen(
                    self.db, bahn=bahn, geraet_millis=0,
                    empfangen_um=start_zeit,
                    client_event_id=uuid.uuid4().hex,
                )
                zuordnung_pruefen(self.db, bahn)
                if self.beleuchtung is not None:
                    self.beleuchtung.blitzen(bahn)
        self._start_fenster_aktiv = False
        self._tabelle_neu_laden()
        self._auf_ereignis({"neues_ereignis": {"bahn": 0},
                           "zustaende": [0, 0, 0, 0]})
        self._beleuchtung_aktualisieren()

    def _gemeinsamer_start(self) -> None:
        """Setzt den 1. Kontakt fuer ALLE 4 Bahnen gleichzeitig – der
        offizielle Startzeitpunkt. Danach braucht es nur noch 4 physische
        Kontakte pro Bahn (statt 5). Verhindert, dass ein Team durch
        Nicht-Ausloesen des 1. Kontakts taktisch Vorteile erlangt."""
        antwort = QMessageBox.question(
            self, "Gemeinsamer Start",
            "Gemeinsamen Start fuer alle 4 Bahnen ausloesen?\n"
            "Dies setzt den 1. Kontakt (Startzeitpunkt) fuer alle Bahnen.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if antwort != QMessageBox.StandardButton.Yes:
            return
        from .lokale_zuordnung import zuordnung_pruefen
        empfangen_um = datetime.now(timezone.utc).isoformat()
        geraet_millis = int(time.time() * 1000) % 1_000_000
        for bahn in range(1, 5):
            client_event_id = uuid.uuid4().hex
            datenbank.ereignis_hinzufuegen(
                self.db, bahn=bahn, geraet_millis=geraet_millis,
                empfangen_um=empfangen_um, client_event_id=client_event_id,
            )
            zuordnung_pruefen(self.db, bahn)
            if self.beleuchtung is not None:
                self.beleuchtung.blitzen(bahn)
        self._tabelle_neu_laden()
        self._auf_ereignis({"neues_ereignis": {"bahn": 0},
                           "zustaende": [1, 1, 1, 1]})
        self._beleuchtung_aktualisieren()
        QMessageBox.information(self, "Gemeinsamer Start",
                                "Start fuer alle 4 Bahnen gesetzt!\n"
                                "Jetzt 4 weitere Kontakte pro Bahn abwarten.")

    def _lauf_abbrechen(self) -> None:
        """Bricht den aktiven Lauf ab - serverseitig (online) und lokal
        (offline). Bereits erfasste Teilzeiten bleiben erhalten."""
        antwort = QMessageBox.warning(
            self, "Lauf abbrechen",
            "Den aktuell aktiven Lauf WIRKLICH abbrechen?\n"
            "Already erfasste Teilzeiten bleiben erhalten.\n"
            "Dies ist fuer Notfaelle (Verletzung, Abbruch).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if antwort != QMessageBox.StandardButton.Yes:
            return

        # 1. Lokalen Lauf deaktivieren (falls offline-Modus aktiv)
        datenbank.verbindung.execute(
            "UPDATE lokaler_lauf SET aktiv = 0 WHERE aktiv = 1")
        datenbank.verbindung.commit()

        # 2. Server-Call: aktiven NotfallLauf deaktivieren
        import requests
        try:
            url = self.einstellungen.webapp_url.replace(
                "/api/zeitmessung/event", "") + "/notfall/api/abrechen"
            requests.post(url, headers={
                "X-API-Key": self.einstellungen.api_key,
            }, timeout=5)
        except Exception:
            pass  # Server nicht erreichbar - lokaler Abbruch reicht

        self._lokalen_lauf_anzeigen()
        self._letzter_server_lauf = None
        self._beleuchtung_aktualisieren()
        QMessageBox.information(self, "Lauf abgebrochen",
                                "Der Lauf wurde abgebrochen.\n"
                                "Teilzeiten sind erhalten geblieben.")

    def _manuelles_event(self, bahn: int) -> None:
        """Erzeugt ein manuelles Kontaktereignis fuer die angegebene Bahn."""
        self._event_verarbeiten(bahn, int(time.time() * 1000) % 1_000_000)

    def closeEvent(self, event) -> None:
        for worker in (self._seriell_worker, self._sync_worker, self._sicherung_worker,
                      self._lauf_worker, self._lauf_import_worker):
            if worker is not None:
                worker.stoppen()
        if self.beleuchtung is not None:
            self.beleuchtung.schliessen()
        super().closeEvent(event)