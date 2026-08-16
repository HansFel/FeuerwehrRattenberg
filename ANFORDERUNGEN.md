# Anforderungen an die App

<!-- Automatisch aus der App exportiert (Bereich Anforderungen).
     Von Administratoren gepflegt; hier NICHT von Hand editieren. -->

## Für andere KI-Assistenten (z.B. Codex) — Projekt-Kontext

_(Dieser Abschnitt wurde am 2026-08-15 manuell ergänzt, damit ein neu
hinzukommender KI-Assistent den aktuellen Stand versteht, ohne den ganzen
Chat-Verlauf zu kennen. Bei Widersprüchen zum aktuellen Code gilt der Code.)_

### Was ist das Projekt

Flask-Web-App zur Organisation des **Jubiläums-Wettbewerbs "120 Jahre
Feuerwehr Rattenberg"** (Österreich). Interner/Codename war "Silo-planen-
rennen" — hat nichts mit Agrar-Silos zu tun, sondern ist der Name der
Hauptdisziplin (Staffel-Wettbewerb mit Planen). Repo: lokal unter
`C:\dev\FeuerwehrRattenberg`, auf GitHub unter
**`HansFel/FeuerwehrRattenberg`** (privat).

### Tech-Stack

Flask + Flask-SQLAlchemy + Flask-Login, App-Factory-Pattern
(`app/__init__.py: create_app()`), Blueprints unter `app/blueprints/`,
Jinja2-Templates unter `app/templates/`, pytest-Tests unter `tests/`
(Stand: >100 Tests, alle sollen vor jedem Deploy grün sein). Produktions-DB:
PostgreSQL 17. Lokale Dev-DB: ebenfalls Postgres via Docker Compose (nicht
SQLite, um dieselbe DB wie Produktion zu testen).

### Rollensystem

`administrator`, `organisator`, `startrichter`, `punkterichter`, `kellner`,
`ausschank` (siehe `ROLLEN` in `app/models.py`). `darf(*rollen)` prüft ALLE
zugewiesenen Rollen einer Person; `dashboard_zeigt(*rollen)` bzw. die
Menüleiste in `base.html` richten sich nach der gerade AKTIVEN Rolle
(Personen mit mehreren Rollen können umschalten). Admin erfüllt implizit
jede Rollenprüfung.

### Produktions-Deployment

Eigener Ubuntu-Server "ffrattenberg" (Docker, Traefik-Reverse-Proxy,
DuckDNS: `ffrattenberg.duckdns.org`). Deploy-Ablauf: auf dem Server
`git pull`, `BUILD_TAG` in `deployment/.env` erhöhen (Image-Tag MUSS bei
jedem Code-Stand hochgezählt werden, sonst kein echter Rebuild!),
`docker compose -f deployment/docker-compose.ffrattenberg.yml up -d --build`.
`app/version.py` (`BUILD_NUMMER`/`BUILD_ZEIT`, im Footer sichtbar) bei jedem
für Deployment vorbereiteten Stand von Hand hochzählen — einziges
zuverlässiges Signal, ob ein Deployment den neuesten Code hat.

App ist zusätzlich **direkt im lokalen Netz auf Port 8000 erreichbar** (ohne
Traefik/TLS) — wichtig für Hardware im selben LAN wie der Server (z.B.
Zeitmessung), weil der Router kein zuverlässiges NAT-Hairpin für manche
Clients unterstützt.

Zwei Testinstanzen unter `/test1` und `/test2` (Pfad-Präfix, eigene DBs) für
Personal-Schulung, laufen mit demselben Image wie Produktion.

### Wichtige Architektur-Konventionen

- **Additive Schema-Migration**: `db.create_all()` legt neue Tabellen an,
  aber KEINE neuen Spalten an bestehenden Tabellen. Neue Modellfelder an
  existierenden Tabellen müssen in `app/__init__.py: _schema_migrieren()`
  über `_spalten_ergaenzen()` nachgetragen werden (funktioniert für
  Postgres UND SQLite).
- **Snapshot-Pattern**: Bestellpositionen, Startplätze etc. frieren Preise/
  Namen zum Zeitpunkt der Erfassung ein, damit spätere Änderungen an
  Stammdaten (z.B. Artikelpreis) historische Daten nicht rückwirkend
  verändern.
- **Vor jedem Deploy**: `pytest` komplett grün, `BUILD_NUMMER` erhöht,
  lokal in Docker Desktop verifiziert (`deployment/docker-compose.local.yml`),
  dann erst Production-Deploy.
- Backup-Dateinamen müssen den Instanznamen enthalten (siehe
  `INSTANCE_NAME`), nicht generisch "backup_..." — projektübergreifende
  Konvention.

### Wichtige, teils noch offene fachliche Fragen

- Turnierformat Siloplanen-Race: 4 Bahnen, Vorrunde (jedes Team läuft 2×
  gegen wechselnde Gegner), danach Halbfinale (Plätze 1-8), Platzierungsläufe
  in 4er-Gruppen (Plätze 9-44), Kleines Finale (5-8), Großes Finale (1-4).
  **Wie genau das Halbfinale aus der Vorrunden-Rangliste gesetzt wird
  (zufällig oder z.B. 1-4-5-8 gegen 2-3-6-7), ist bewusst NICHT fest
  programmiert** — der Organisator wählt das manuell über die
  Rangliste-Ansicht unter `/zeitplan/`.
- Zeitmessung: nur noch 1 Öffner-Kontakt pro Bahn (nicht mehr Start+Ziel
  getrennt), siehe Firmware-README unten. Die Zuordnung "welche der 5
  Auslösungen pro Bahn war welcher Läufer" ist noch nicht automatisiert
  (passiert bisher nur visuell über die laufende Nummer in der
  Zeitmessung-Übersicht).
- Startfreigabe-Button für den Startrichter (offiziellen Start-Zeitpunkt
  eines Laufs markieren) wurde angefragt, ist noch nicht gebaut.

### Datenschutz/Rechtliches

Impressum/Datenschutz-Seiten sind bewusst als **Entwurf mit Platzhaltern**
markiert (App verarbeitet echte Personendaten, teils Minderjährige) — vor
echtem Einsatz durch eine verantwortliche Person / ggf. Rechtsberatung
prüfen lassen, nicht einfach als fertig annehmen.

---

## ESP32-Zeitmessung-Firmware (vollständige README, Stand 2026-08-15)

_(Eingefügt auf Anfrage, damit eine andere KI ohne Zugriff auf
`firmware/zeitmessung/README.md` denselben Stand kennt. Bei Widersprüchen
gilt die tatsächliche Datei im Repo.)_

# Zeitmessung Siloplanen-Race (ESP32)

Liest 4 Kontakte (einer pro Bahn) und meldet jede Auslösung per HTTP an die
FeuerwehrRattenberg-App (`/api/zeitmessung/event`). Ablauf pro Bahn: Läufer 1
löst den Kontakt beim Loslaufen aus, bei der Übergabe löst jeweils der
nächste Läufer denselben Kontakt erneut aus, der letzte (vierte) Läufer
löst ihn zusätzlich noch einmal am Ziel aus - macht 5 Auslösungen pro Bahn
über den gesamten Lauf. Die Firmware selbst kennt keine Läufe/Runden oder
Läufer-Zuordnung und unterscheidet auch nicht mehr zwischen "Start" und
"Ziel" (dafür gibt es nur noch einen Kontakt pro Bahn, keinen separaten
Ziel-Kontakt) - die App muss die Zuordnung "welche Auslösung war was"
später anhand der Reihenfolge (1.–4. = Läufer-Start, 5. = Ziel) treffen.

## Verkabelung

**Öffner-Kontakte** (NC/Break-Kontakte) am internen Pullup: Ruhezustand =
Kontakt geschlossen = gegen GND kurzgeschlossen = LOW. Auslösung = Kontakt
öffnet = Pin wird vom internen Pullup auf HIGH gezogen. Die Firmware
erkennt eine Auslösung an der Flanke LOW → HIGH (nicht umgekehrt - ein
Schließer/NO-Kontakt würde hier falsch erkannt).

| Bahn | Kontakt-Pin (GPIO) |
|------|---------------------|
| 1    | 32                  |
| 2    | 33                  |
| 3    | 25                  |
| 4    | 26                  |

Pins sind bewusst so gewählt, dass sie `INPUT_PULLUP` unterstützen und keine
Boot-Strapping-/Flash-Pins sind (GPIO34–39 fallen deshalb raus – die haben
keinen internen Pullup). Anpassbar in `include/config.h`.

## Erstinbetriebnahme

1. Firmware flashen (siehe unten).
2. Der ESP32 startet einen eigenen WLAN-Access-Point `Zeitmessung-esp32-zeitmessung-1`
   (Captive Portal, 3 Minuten Timeout). Damit verbinden, im Portal das
   Veranstaltungs-WLAN auswählen und zusätzlich eintragen:
   - **App-URL**: vollständige Adresse des Endpoints, z.B.
     `http://192.168.1.10:8000/api/zeitmessung/event`
   - **API-Key**: muss mit `ZEITMESSUNG_API_KEY` der App übereinstimmen
   - **Zeitserver**: z.B. `pool.ntp.org`, oder eine lokale NTP-Adresse, falls
     am Veranstaltungsort kein Internet verfügbar ist
3. Diese Werte werden im NVS gespeichert und bleiben nach einem Neustart
   erhalten – kein erneutes Flashen nötig, wenn sich z.B. die Server-IP
   ändert (dazu über die Geräte-Weboberfläche "WLAN wechseln" bzw. "Alles
   zurücksetzen" und das Portal erneut durchlaufen, siehe unten).

## WLAN wechseln (z.B. Umzug zwischen Netzwerken)

Über die Geräte-Weboberfläche (`/`) gibt es zwei Knöpfe:

- **"WLAN wechseln"** – öffnet das Konfigurationsportal erneut (3 Minuten
  Timeout), **ohne** vorher etwas zu löschen. App-URL/API-Key bleiben
  erhalten und sind im Portal vorausgefüllt; wird das Portal nicht
  ausgefüllt oder läuft es in den Timeout, verbindet sich das Gerät
  automatisch wieder mit dem bisherigen WLAN. Das ist der übliche Weg,
  wenn nur das Netzwerk wechselt (z.B. Testbetrieb zu Hause → echtes WLAN
  am Veranstaltungsort).
- **"Alles zurücksetzen"** – löscht WLAN-Zugangsdaten UND App-URL/API-Key
  unwiderruflich und startet neu; nur nötig, wenn wirklich bei Null
  begonnen werden soll.

Während des Konfigurationsportals ist die normale Geräte-Weboberfläche
nicht erreichbar (das Gerät spannt währenddessen einen eigenen
Access-Point auf) – mit Handy/Laptop kurz mit `Zeitmessung-<Geräte-ID>`
verbinden, neues Netzwerk wählen, danach ist das Gerät wieder unter seiner
(neuen) WLAN-IP erreichbar.

## Lokale Weboberfläche

Nach dem Verbinden ist der ESP32 unter seiner WLAN-IP erreichbar (im Router
oder Serial-Monitor ablesen):

- `/` – Status (WLAN, Zeit-Sync, App-URL) und die letzten ~25 Kontaktereignisse
  mit Sendestatus (gesendet/wartend/fehlgeschlagen) – zum Testen vor Ort, ob
  die Kontakte sauber auslösen, ohne die Haupt-App zu öffnen
- `/status` – dieselben Daten als JSON
- `/wlan-wechseln` – startet neu ins Konfigurationsportal, OHNE etwas zu
  löschen (App-URL/API-Key bleiben, altes WLAN bleibt als Fallback)
- `/wlan-zuruecksetzen` – löscht WLAN-Zugangsdaten UND App-URL/API-Key und
  startet neu (Captive Portal erscheint wieder, alle Felder leer)

## Bauen und Flashen (PlatformIO)

```bash
pio run                    # kompilieren
pio run -t upload          # auf COM4 flashen (siehe platformio.ini)
pio device monitor         # Serial-Ausgabe (115200 Baud)
```

`upload_port`/`monitor_port` in `platformio.ini` ggf. anpassen, falls der
ESP32 an einem anderen COM-Port hängt.

**Aktuelle IP schnell herausfinden, ohne etwas zu ändern:** `pio device
monitor` öffnen (das Öffnen des Monitors selbst löst durch DTR/RTS der
USB-Bridge einen Neustart des ESP32 aus – der Boot-Log zeigt dann u.a. die
WLAN-IP). Alternativ nach dem Boot einfach `status` eintippen.

## Serielle Konsole (Einrichtung/Diagnose per USB-Kabel)

Mit `pio device monitor` (oder jedem anderen seriellen Terminal, 115200
Baud, Zeilenende „Newline"/`\n`) verbunden, stehen folgende Befehle zur
Verfügung – nützlich, wenn kein Handy/Laptop im selben WLAN verfügbar ist
oder man nicht erst den Konfigurations-Access-Point durchlaufen will:

| Befehl | Wirkung |
|---|---|
| `hilfe` | Befehlsübersicht anzeigen |
| `status` bzw. `ip` | Aktueller Status: WLAN verbunden ja/nein, SSID, **IP-Adresse**, RSSI, Zeit-Sync, App-URL, NTP-Server, Laufzeit |
| `scan` | WLAN-Netzwerke in der Umgebung auflisten (SSID, RSSI, Kanal, offen/verschlüsselt) |
| `wifi <SSID>\|<Passwort>` | Mit neuem WLAN verbinden und speichern (Trennzeichen **`\|`** – Pipe-Zeichen, da SSID/Passwort Leerzeichen enthalten dürfen, z.B. `wifi FRITZ!Box 6670 GN\|MeinPasswort123`) |
| `apiurl <URL>` | App-URL setzen (siehe "App-URL wählen" unten) |
| `apikey <Schlüssel>` | API-Key setzen (muss mit `ZEITMESSUNG_API_KEY` der App übereinstimmen) |
| `ntp <Server>` | Zeitserver setzen (z.B. `ntp pool.ntp.org`) |
| `testsenden` | Test-Ereignis an die aktuelle App-URL senden, ohne einen echten Kontakt auszulösen - zeigt bei Fehlern den genauen Fehlercode/-text und den freien Heap |
| `neustart` | Gerät neu starten |

Beispiel-Ablauf für die Ersteinrichtung komplett über USB (ohne Captive
Portal): Gerät per USB anschließen, `pio device monitor` öffnen, dann
nacheinander:
```
wifi Veranstaltungs-WLAN|GeheimesPasswort
apiurl http://192.168.1.10:8000/api/zeitmessung/event
apikey dein-api-key
ntp pool.ntp.org
testsenden
```

## App-URL wählen: lokale IP vs. öffentliche Domain

**Wenn der ESP32 im selben lokalen Netz wie der Server steht** (typischer
Fall am Veranstaltungsort): lokale IP:Port des Servers verwenden, z.B.
`http://192.168.1.238:8000/api/zeitmessung/event` (Port 8000 ist am
ffrattenberg-Server extra für diesen Zweck direkt freigegeben, umgeht
Traefik/TLS komplett). **Nicht** die öffentliche HTTPS-Domain verwenden,
wenn Server und ESP32 im selben Netz stehen - manche Router (z.B. der
hier verwendete TCL-LTE-Router) unterstützen kein zuverlässiges
NAT-Hairpin/Loopback für das ESP32 spezifisch, obwohl andere Geräte im
selben Netz (PC-Browser) über die öffentliche Domain trotzdem
funktionieren. Symptom bei diesem Problem: `testsenden` liefert
`connect failed: -1` / "connection refused", obwohl die App über einen
Browser im selben Netz erreichbar ist.

**Wenn der ESP32 in einem ANDEREN Netz als der Server steht:** die
öffentliche HTTPS-Domain verwenden (z.B.
`https://ffrattenberg.duckdns.org/api/zeitmessung/event`) - die Firmware
unterstützt HTTPS (Zertifikatsprüfung wird bewusst übersprungen,
`setInsecure()`, unproblematisch für diese interne Zeitmessdaten).

## OTA-Updates (Firmware-Updates übers WLAN)

Sobald einmal eine OTA-fähige Firmware per USB installiert ist (aktueller
Stand, `partitions_ota.csv`), können weitere Updates übers WLAN erfolgen -
kein USB-Kabel/Boot-Taste mehr nötig:

```bash
pio run -e esp32dev_ota -t upload --upload-port <IP-des-ESP32>
```

Das Passwort ist der aktuelle API-Key (siehe `status`); PlatformIO liest
ihn über die Umgebungsvariable `ZEITMESSUNG_OTA_PASS` (in `platformio.ini`
als `${sysenv.ZEITMESSUNG_OTA_PASS}` referenziert, damit kein Geheimnis im
Repo landet):

```bash
# Bash/Linux/macOS
ZEITMESSUNG_OTA_PASS="<api-key>" pio run -e esp32dev_ota -t upload --upload-port <IP>
# PowerShell
$env:ZEITMESSUNG_OTA_PASS="<api-key>"; pio run -e esp32dev_ota -t upload --upload-port <IP>
```

OTA-Uploads sind in der Praxis manchmal weniger zuverlässig als USB (v.a.
wenn das Gerät gerade mit anderen Netzwerkzugriffen beschäftigt ist) -
bei "No Answer to our Authentication" oder ähnlichen Fehlern 2-3x erneut
versuchen, danach notfalls per USB flashen.

## Getestet (2026-08-15)

Kompletter Ablauf (Compile, USB-Flash inkl. Boot-Taste-Prozedur, WLAN-
Verbindung, OTA-Update, HTTPS- und HTTP-Versand, End-zu-End bis in die
Zeitereignis-Tabelle der Produktions-App) auf echter Hardware
durchgespielt und funktionsfähig. Bekannte Stolperfallen dabei:
- Manche ESP32-Boards gehen beim Flashen nicht zuverlässig automatisch in
  den Download-Modus - dann manuell: BOOT-Taste halten, EN kurz drücken,
  BOOT weiter halten bis der Upload startet.
- Serielles Rauschen/"Wrong boot mode"-Fehler beim ersten Versuch sind
  normal, meist hilft ein sofortiger erneuter Versuch.
- Ein durch einen unterbrochenen Flash-Vorgang korrumpierter App-Bereich
  äußert sich als Boot-Schleife ("No bootable app partitions") - ein
  vollständiger, nicht unterbrochener Neu-Flash behebt das.

## Offene Punkte

- Bei mehreren ESP32-Geräten (z.B. eines pro Bahn statt eines für alle 4)
  `GERAETE_ID` in `include/config.h` je Gerät eindeutig setzen.
- Entprellzeit (`ENTPRELL_MS`, aktuell 30 ms) ggf. nach ersten Tests mit der
  echten Mechanik der Kontakte anpassen.

---

## Offen (0)

_(keine offenen Einträge)_

## Erledigt (0)

_(keine)_
