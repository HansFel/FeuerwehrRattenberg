# Zeitmessung Desktop-App

Lokale PySide6-App für den Zeitnehmungs-PC beim Event (aktuell:
`hans@felferlinuxlab`). Liest den Arduino Mega 2560
(`../firmware/zeitmessung-mega/`) über USB-Seriell aus und reicht jede
Kontaktauslösung an den bestehenden `/api/zeitmessung/event`-Endpoint der
Webapp weiter - identisch zum bisherigen ESP32-Weg, nur über USB statt WLAN.

**Kernidee für Ausfallsicherheit:** Jedes Ereignis wird SOFORT lokal in
SQLite gespeichert, bevor überhaupt ein Sync-Versuch unternommen wird. Ein
Strom- oder WLAN-Ausfall am Veranstaltungsort verliert dadurch keine
Zeitmessung - ausstehende Ereignisse werden einfach nachgereicht, sobald die
Webapp wieder erreichbar ist. Ein Retry nach einem Sync-Timeout erzeugt kein
Duplikat (`client_event_id`, siehe `app/blueprints/zeitmessung.py`).

## Netzwerk: Webapp-URL richtig setzen

**Standard/empfohlen:** direkte LAN-IP des aktiven Servers + Port 8000, z.B.
`http://192.168.1.14:8000/api/zeitmessung/event` (kein Traefik/TLS, kein
DNS nötig) - siehe `einstellungen.py` für die Begründung. Der TCL-Router
unterstützt kein zuverlässiges NAT-Hairpin, und selbst mit dem
AdGuard-Split-DNS-Workaround (siehe `AGENTS.md`, Abschnitt "Netzwerk:
Split-DNS") hängt der Domain-Weg von korrekter Client-DNS-Konfiguration ab.

**Vor jedem Event-Einsatz prüfen:**
1. Aktuelle IP des aktiven Servers per SSH verifizieren (`hostname -I` o.ä.)
   - sie ist NICHT stabil, keine DHCP-Reservierung eingerichtet.
2. `webapp_url` im Einstellungsdialog entsprechend anpassen, falls die IP
   sich geändert hat.
3. Echten `api_key` eintragen (kommt aus `ZEITMESSUNG_API_KEY` auf dem
   Server, NICHT der lokale Dev-Default `dev-nur-lokal-zeitmessung`).

## Setup

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # Windows
# .venv/bin/pip install -e ".[dev]"       # Linux (Zeitnehmungs-PC)
```

## Starten

```bash
.venv/Scripts/python -m zeitmessung_desktop
```

Einstellungen (COM-Port, Webapp-URL, API-Key, Instanzname, Sync-/
Backup-Intervall) über den Knopf "Einstellungen…" im Hauptfenster - werden
unter `~/.zeitmessung_desktop/einstellungen.json` gespeichert.

**Buzzer-Sperrzeit:** In den Einstellungen begrenzt „Buzzer-Sperrzeit je
Bahn (Sekunden)“ versehentliche Doppelimpulse desselben physischen Kontakts.
Der Standardwert ist 1 Sekunde, einstellbar von 0 bis 60 Sekunden; 0 deaktiviert nur
diese zusätzliche Software-Sperre. Die Sperrzeit gilt getrennt pro Bahn und
greift vor lokaler Speicherung, Zuordnung und Web-App-Synchronisierung.
Manuelle START-/STOPP-Tasten bleiben als bewusster Fallback ungesperrt.
Auf `felferlinuxlab` sind aktuell **20 Sekunden** gespeichert (verifiziert
2026-08-21 nach dem produktiven Neustart).

### Autostart auf dem Zeitnehmungs-PC

Nach dem einmaligen Setup kann die App als systemd-Benutzerdienst eingerichtet
werden:

```bash
chmod +x autostart-installieren.sh
./autostart-installieren.sh
systemctl --user status zeitmessung-desktop.service
```

Der Installer verwendet immer die `.venv` dieses Ordners, aktiviert den Dienst
sofort und startet ihn nach künftigen grafischen Anmeldungen automatisch neu.
Logs zeigt `journalctl --user -u zeitmessung-desktop.service -f`.

## Manueller Modus (offline, ohne Webapp-Verbindung)

Falls die LAN-Verbindung zur Webapp während des Wettkampfs ausfällt, lässt
sich ein Lauf trotzdem messen: im Bereich "Manueller Modus" die
**Team-Startnummer** je Bahn eintippen (kein Team-Lookup nötig, funktioniert
komplett offline) und "Lokalen Lauf starten" klicken. Die App ordnet die
eingehenden Mega-Kontaktereignisse ab diesem Zeitpunkt lokal derselben
5-Auslösungen-Logik zu wie der Server (siehe `lokale_zuordnung.py`) - die
Zeitmessung selbst bleibt also gleich genau, nur die Team-Zuordnung passiert
lokal statt über die Webapp.

Sobald die Webapp wieder erreichbar ist, meldet `LaufImportWorker`
automatisch im Hintergrund alle noch offenen lokalen Läufe nach
(`/notfall/api/importieren` auf dem Server, matcht die Startnummer gegen
`Team.startnummer`) - kein manuelles Nachtragen nötig.

## Tests

```bash
.venv/Scripts/python -m pytest
```

83 Tests für Protokoll-Parsing, lokale Datenbank, lokale Zuordnung, Sicherung,
Sync, Import, DMX-Beleuchtung und Licht-Zustandslogik (GUI selbst nicht mit
pytest getestet, siehe "Getestet" unten für den manuellen End-to-End-Nachweis).

## Architektur

| Modul | Zweck |
|---|---|
| `seriell_protokoll.py` | Reine Parser-Funktion für das Mega-Zeilenprotokoll (`READY`/`HEARTBEAT`/`STATE`/`EVENT`) |
| `seriell_worker.py` | Hintergrund-Thread: liest COM-Port, schreibt Ereignisse sofort in SQLite, Auto-Reconnect (inkl. Zombie-Verbindungs-Timeout), löst lokale Zuordnung aus |
| `lokale_zuordnung.py` | Lokale Nachbildung der Server-5-Auslösungen-Logik für den manuellen Offline-Modus |
| `datenbank.py` | Lokaler SQLite-Puffer (WAL-Modus) - Ereignisse + lokale Läufe/Bahnen |
| `sync_worker.py` | Hintergrund-Thread: sendet ausstehende Ereignisse an die Webapp, idempotent per `client_event_id` |
| `lauf_worker.py` | Hintergrund-Thread: pollt `/notfall/api/aktiv`, Live-Anzeige des von der Webapp verwalteten Laufs |
| `lauf_import_worker.py` | Hintergrund-Thread: meldet lokal (offline) gemessene Läufe nach, sobald die Webapp erreichbar ist |
| `webapp_urls.py` | Leitet weitere Endpunkt-URLs aus der bekannten Event-URL ab (Instanz-Pfadpräfix-sicher) |
| `sicherung.py` | Zyklische Sicherung nach der projektweiten Namenskonvention `<instanz>_sicherung_<zeitstempel>.sqlite` |
| `einstellungen.py` | Konfiguration (JSON) |
| `hauptfenster.py` | PySide6-GUI: Verbindungsstatus, Einstellungsdialog, Live-Zustand, Ereignisliste, aktiver/lokaler Lauf, manueller Modus |

## Getestet

**2026-08-16/17, End-to-End auf echter Hardware:**
- Arduino Mega → `SeriellWorker` → lokale SQLite → `SyncWorker` → echte
  Webapp-Datenbank, komplett durchgespielt (inkl. Pin-Wechsel wegen
  Board-Eigenheit, siehe `firmware/zeitmessung-mega/README.md`).
- Deployment auf `felferlinuxlab` (Linux Mint, echter Zeitnehmungs-PC)
  verifiziert: X11-Fernstart per SSH (`DISPLAY=:0`), `dialout`-Gruppe für
  `/dev/ttyUSB0`, `libxcb-cursor0` als zusätzliche Abhängigkeit.

**2026-08-17, manueller Offline-Modus (End-to-End gegen echte Webapp-DB):**
Lokale Zuordnung (5 simulierte Ereignisse, korrekte Delta-Berechnung
2.0/3.0/4.0/5.0s) → `LaufImportWorker` → echte `notfall_lauf`/`notfall_bahn`-
Tabellen: Team korrekt über `team_nummer`↔`Team.startnummer` verknüpft,
Zeiten korrekt übernommen, lokaler Lauf danach korrekt als `gesendet`
markiert.

**2026-08-21, produktiver Linux-PC und DMX-Lichtlogik:**

- Zeitnehmungs-PC: `felferlinuxlab`, Tailscale `100.78.51.89`, SSH-Benutzer
  `hans`. Installation: `/home/hans/zeitmessung-desktop`, Start über
  `./start.sh` in der X11-Sitzung mit `DISPLAY=:0`.
- Aktualisierung über Tailscale-SSH verifiziert; die Desktop-Tests direkt auf
  `felferlinuxlab` bestanden. Vor dem Update wurde die vorherige Installation
  unter `/home/hans/zeitmessung-desktop-backup-20260821-185020` gesichert.
- Der frühere Button **„Gemeinsamer Start“** wurde vollständig aus Oberfläche
  und Handler-Code entfernt. Die einzelnen Bahn-START-/STOPP-Tasten bleiben
  als manueller Hardware-Fallback erhalten.
- Lichtfolge: aktiver, vom Organisator freigegebener Serverlauf = **GRÜN**;
  vollständig gemessener Lauf = **ROT**, bis der nächste Lauf freigegeben
  wird. Ein aktiver Serverlauf hat immer Vorrang vor einem alten lokalen
  Offline-Lauf. Dadurch kann ein vollständig gemessener Offline-Lauf den
  nächsten Serverlauf nicht mehr fälschlich auf Rot halten.
- Praxisprüfung nach dem Update: `/notfall/api/aktiv` lieferte einen aktiven,
  freigegebenen und nicht vollständigen Lauf; beide seriellen Geräte waren
  gleichzeitig geöffnet (`/dev/ttyUSB0` und `/dev/ttyUSB1`) und die
  Beleuchtung schaltete wie vorgesehen. Vom User anschließend als
  funktionierend bestätigt.

## Vor-Ort-Prüfungen

- Manueller Offline-Modus noch nicht mit echten Mega-Kontaktauslösungen vor
  Ort getestet (nur simulierte Ereignisse, siehe oben).
- Mega-USB-Erkennung auf dem Windows-Entwicklungsrechner zeitweise
  ausgefallen (kein COM-Port, kein "Unbekanntes Gerät" trotz Kabel/LED) -
  Ursache noch nicht abschließend geklärt.
