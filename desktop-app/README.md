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

## Tests

```bash
.venv/Scripts/python -m pytest
```

19 Tests für Protokoll-Parsing, lokale Datenbank, Sicherung und
Sync-Payload-Aufbau (GUI selbst nicht mit pytest getestet, siehe
"Getestet" unten für den manuellen End-to-End-Nachweis).

## Architektur

| Modul | Zweck |
|---|---|
| `seriell_protokoll.py` | Reine Parser-Funktion für das Mega-Zeilenprotokoll (`READY`/`HEARTBEAT`/`EVENT`) |
| `seriell_worker.py` | Hintergrund-Thread: liest COM-Port, schreibt Ereignisse sofort in SQLite, Auto-Reconnect |
| `datenbank.py` | Lokaler SQLite-Puffer (WAL-Modus) |
| `sync_worker.py` | Hintergrund-Thread: sendet ausstehende Ereignisse an die Webapp, idempotent per `client_event_id` |
| `sicherung.py` | Zyklische Sicherung nach der projektweiten Namenskonvention `<instanz>_sicherung_<zeitstempel>.sqlite` |
| `einstellungen.py` | Konfiguration (JSON) |
| `hauptfenster.py` | PySide6-GUI: Verbindungsstatus, Einstellungsdialog, Live-Ereignisliste |

## Getestet (2026-08-16)

End-to-End auf echter Hardware durchgespielt:
- Arduino Mega (COM3) → `SeriellWorker` → lokale SQLite: 4 Ereignisse
  korrekt erkannt und gepuffert (Kontakte waren zu diesem Zeitpunkt noch
  nicht verkabelt - jeder Pin löst beim ersten Verbinden einmalig aus, siehe
  `firmware/zeitmessung-mega/README.md`, identisches Verhalten wie beim
  ESP32 bei unverkabelten Pins, kein Bug).
- `SyncWorker` → lokal laufende Webapp (`python run.py`) → echte
  `zeitereignis`-Tabelle: alle 4 gepufferten Ereignisse erfolgreich
  gesendet, als `gesendet` markiert, Wiederholung des Sync-Zyklus erzeugte
  korrekt KEINEN erneuten Sendeversuch (bereits synced).

## Offene Punkte

- Echte Kontakte am Mega anschließen und ein vollständiges 5-Auslösungen-
  Bahn-Ereignis (inkl. automatischer Zuordnung in `NotfallLauf`) end-to-end
  testen.
- GUI selbst nur per Headless-Smoketest (offscreen-Plattform) geprüft, noch
  nicht mit echtem Display/Maus vor Ort getestet.
- PyInstaller/Auto-Start-Einrichtung auf `felferlinuxlab` (Linux) noch
  offen - aktuell nur `python -m zeitmessung_desktop` manuell.
