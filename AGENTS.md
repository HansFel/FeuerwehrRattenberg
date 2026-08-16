# Projekt-Kontext für KI-Assistenten (Claude, Codex, ...)

Diese Datei wird **nur von KI-Assistenten gepflegt** (nicht von der App
generiert, nicht von Hand durch Admins). Sie ist der feste Ort für
Projektüberblick, Architektur-Konventionen und Kontext, der über einzelne
Chat-Sessions hinaus erhalten bleiben soll.

Für den aktuellen **Aufgaben-/Wunschzettel der Administratoren** siehe
stattdessen `ANFORDERUNGEN.md` (wird automatisch aus der App exportiert,
ändert sich bei jeder Admin-Aktion im Bereich "Anforderungen").

_(Stand 2026-08-15. Bei Widersprüchen zum aktuellen Code gilt der Code -
diese Datei kann veralten.)_

## Aktuell in Bearbeitung

**Vor größeren/mehrschrittigen Änderungen** (neues Feature, Refactoring,
Datenmodell-Änderung) hier einen Eintrag ergänzen, damit eine andere KI
nicht gleichzeitig an derselben Stelle arbeitet und sich die Änderungen
nicht gegenseitig überschreiben. **Nach Abschluss** (oder wenn die Session
endet) den eigenen Eintrag wieder entfernen. Format:

```
- [KI-Name] [Datum/Uhrzeit] – [Kurzbeschreibung, betroffene Dateien/Bereiche]
```

Vor dem Start eigener größerer Änderungen: diese Liste lesen. Steht dort
ein Eintrag mit Überschneidung zum eigenen Vorhaben, NICHT einfach
weitermachen, sondern den User informieren und abstimmen, statt parallel
an derselben Stelle zu arbeiten.

## Was ist das Projekt

Flask-Web-App zur Organisation des **Jubiläums-Wettbewerbs "120 Jahre
Feuerwehr Rattenberg"** (Österreich). Interner/Codename war "Silo-planen-
rennen" — hat nichts mit Agrar-Silos zu tun, sondern ist der Name der
Hauptdisziplin (Staffel-Wettbewerb mit Planen). Repo: lokal unter
`C:\dev\FeuerwehrRattenberg`, auf GitHub unter
**`HansFel/FeuerwehrRattenberg`** (privat).

## Tech-Stack

Flask + Flask-SQLAlchemy + Flask-Login, App-Factory-Pattern
(`app/__init__.py: create_app()`), Blueprints unter `app/blueprints/`,
Jinja2-Templates unter `app/templates/`, pytest-Tests unter `tests/`
(Stand: >100 Tests, alle sollen vor jedem Deploy grün sein). Produktions-DB:
PostgreSQL 17. Lokale Dev-DB: ebenfalls Postgres via Docker Compose (nicht
SQLite, um dieselbe DB wie Produktion zu testen).

## Rollensystem

`administrator`, `organisator`, `startrichter`, `punkterichter`, `kellner`,
`ausschank`, `moderator` (siehe `ROLLEN` in `app/models.py`). `darf(*rollen)` prüft ALLE
zugewiesenen Rollen einer Person; `dashboard_zeigt(*rollen)` bzw. die
Menüleiste in `base.html` richten sich nach der gerade AKTIVEN Rolle
(Personen mit mehreren Rollen können umschalten). Admin erfüllt implizit
jede Rollenprüfung.

## Produktions-Deployment

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

Dritte Instanz unter `/generalprobe` (gleiches Muster, eigene DB) für die
Generalprobe vor der Veranstaltung – einmalig mit einer vollständigen Kopie
der echten Produktionsdaten befüllt (`pg_dump --clean --if-exists` aus
`db-ffrattenberg`, restored in `db-ffrattenberg-generalprobe`), danach
unabhängig. Existiert auf BEIDEN Servern (ffrattenberg + Standby), jeweils
mit dem lokalen `db-ffrattenberg`-Stand dieses Servers befüllt. Alle drei
Test-Instanzen liegen in `deployment/docker-compose.ffrattenberg-test.yml`
+ `deployment/.env.test` (BUILD_TAG dort unabhängig von der Produktion,
muss beim Update mit hochgezogen werden, sonst laufen sie auf altem Code).

**Achtung Compose-Falle:** `docker-compose.ffrattenberg.yml` (Produktion)
und `docker-compose.ffrattenberg-test.yml` (test1/test2/generalprobe)
laufen im SELBEN Verzeichnis und teilen sich daher denselben
Docker-Compose-Projektnamen. `docker compose ... up -d --remove-orphans`
auf der EINEN Datei hält die Container der ANDEREN Datei für "verwaist"
und entfernt sie! `--remove-orphans` deshalb bei diesen beiden Dateien
NIE verwenden (oder `-p <eigener-projektname>` bzw. `--remove-orphans`
nur mit vorherigem `docker compose -f <richtige-datei> ps` zur Kontrolle).

### Ersatzserver / Standby während der Veranstaltung

Zweiter Server: **`hans@hans-ThinkPad-E590`**, Linux Mint 22.3, statische
WLAN-Adresse **`192.168.1.34/24`**, Gateway/DNS `192.168.1.1`, WLAN-MAC
`20:79:18:b8:de:bd`. SSH vom Entwicklungs-PC erfolgt mit
`~/.ssh/id_ed25519_ffrattenberg` (Schlüssel ist hinterlegt). Docker läuft;
Docker Compose wurde benutzerspezifisch unter
`~/.docker/cli-plugins/docker-compose` installiert.

Der Standby ist als eigenständiger Docker-Host vorbereitet. Unter
`~/apps/FeuerwehrRattenberg` und `~/apps/traefik` liegen Kopien der aktiven
Konfiguration. Produktion, `/test1`, `/test2`, drei PostgreSQL-Container und
Traefik starten automatisch und wurden lokal über die Standby-IP mit HTTP 200
geprüft. Datenstand der initialen Kopie: **2026-08-16**, jeweils 7 Benutzer;
Prüfsummen und Dumps liegen unter `~/backups/standby-20260816`. Der sichtbare
App-Stand ist Build 18; neuere Builds müssen auf BEIDE Server ausgerollt und
die Daten vor einem tatsächlichen Failover erneut synchronisiert werden.

Git-Deploy auf dem Standby: eigener Read-only-Deploy-Key
`~/.ssh/id_ed25519_github_deploy` (separat vom Deploy-Key des aktiven
Servers, als eigener Eintrag "ffrattenberg-standby-readonly" bei den
Repo-Deploy-Keys auf GitHub hinterlegt) + `~/.ssh/config` mit
`Host github.com`-Eintrag; ohne das schlägt `git pull` mit
"Permission denied (publickey)" fehl.

Standby-spezifische Traefik-Ergänzung:
`~/apps/traefik/docker-compose.standby.yml` setzt `DOCKER_API_VERSION=1.52`,
weil die Docker Engine des ThinkPads maximal API 1.52 unterstützt. Traefik
wird dort mit beiden Dateien gestartet:
`docker compose -f docker-compose.yml -f docker-compose.standby.yml up -d`.

**Noch offen:** Die native Nextcloud-Snap-Installation des aktiven Servers
muss konsistent exportiert und auf dem ThinkPad in einen Docker-Stack migriert
werden. Das vorbereitete Exportskript liegt auf dem aktiven Server unter
`/home/hans/export-nextcloud-standby.sh` und benötigt einmalig `sudo`.
Domains und Router-Portweiterleitungen zeigen im Normalbetrieb weiterhin auf
`ffrattenberg` (`192.168.1.238`). Im Ausfall müssen die TCP-Regeln 80/443 auf
`192.168.1.34` umgestellt und unmittelbar zuvor aktuelle App-/Nextcloud-Daten
auf den Standby synchronisiert werden. Im TCL-Router sollte `.34` zusätzlich
für die genannte WLAN-MAC reserviert bzw. aus dem DHCP-Pool ausgeschlossen
sein.

## Wichtige Architektur-Konventionen

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
  Konvention (gilt für alle Apps des Users, nicht nur dieses Projekt).

## Wichtige, teils noch offene fachliche Fragen

- Turnierformat Siloplanen-Race: 4 Bahnen, Vorrunde (jedes Team läuft 2×
  gegen wechselnde Gegner), danach Halbfinale (Plätze 1-8), Platzierungsläufe
  in 4er-Gruppen (Plätze 9-44), Kleines Finale (5-8), Großes Finale (1-4).
  **Wie genau das Halbfinale aus der Vorrunden-Rangliste gesetzt wird
  (zufällig oder z.B. 1-4-5-8 gegen 2-3-6-7), ist bewusst NICHT fest
  programmiert** — der Organisator wählt das manuell über die
  Rangliste-Ansicht unter `/zeitplan/`.
- Zeitmessung: nur noch 1 Öffner-Kontakt pro Bahn (nicht mehr Start+Ziel
  getrennt), siehe `firmware/zeitmessung/README.md`. Die Zuordnung "welche
  der 5 Auslösungen pro Bahn war welcher Läufer" ist noch nicht
  automatisiert (passiert bisher nur visuell über die laufende Nummer in
  der Zeitmessung-Übersicht `/zeitmessung/`).
- Startfreigabe-Button für den Startrichter (offiziellen Start-Zeitpunkt
  eines Laufs markieren) wurde angefragt, ist noch nicht gebaut.

## Datenschutz/Rechtliches

Impressum/Datenschutz-Seiten sind bewusst als **Entwurf mit Platzhaltern**
markiert (App verarbeitet echte Personendaten, teils Minderjährige) — vor
echtem Einsatz durch eine verantwortliche Person / ggf. Rechtsberatung
prüfen lassen, nicht einfach als fertig annehmen.

## Firmware-Doku

Für die ESP32-Zeitmessung immer zuerst `firmware/zeitmessung/README.md`
lesen (sehr ausführlich: Verkabelung, serielle Konsole, OTA-Updates,
bekannte Stolperfallen beim Flashen). Diese Entwicklungsumgebung hat
PlatformIO nicht vorinstalliert (`pip install platformio` nötig), COM4 ist
aber direkt verfügbar.
