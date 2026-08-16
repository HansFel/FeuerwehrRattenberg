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

App ist zusätzlich **direkt im lokalen Netz erreichbar** (ohne Traefik/TLS):
Produktion Port 8000, test1/test2/generalprobe Port 8001/8002/8003. Wichtig
für (a) Hardware im selben LAN wie der Server (z.B. Zeitmessung, Router
unterstützt kein zuverlässiges NAT-Hairpin für manche Clients) und (b) seit
2026-08-16: `ffrattenberg.duckdns.org` wird von Google Safe Browsing
fälschlich als "gefährlich" gemeldet (generisches Login-Formular auf
duckdns.org-Subdomain löst Googles Heuristik aus) - Personal vor Ort kann
die Instanzen bis zur Google-Überprüfung über diese LAN-Ports nutzen.
Überprüfung anstoßen: https://safebrowsing.google.com/safebrowsing/report_error/
oder Google Search Console (Property + Sicherheitsprobleme).

**Wichtige Falle dabei gefunden und gefixt:** `PrefixMiddleware`
(`app/__init__.py`) reagiert seit Build 22 NUR noch auf den
`X-Script-Name`-Header von Traefik, nicht mehr zusätzlich auf eine statische
`APPLICATION_PREFIX`-Umgebungsvariable (die es dafür nicht mehr gibt).
Vorher erzeugte z.B. test1 beim direkten Port-Zugriff (ohne Traefik davor,
also ohne Header) trotzdem Links mit `/test1`-Präfix, die ins Leere liefen.
Test dafür: `tests/test_prefix_middleware.py`.

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

### ⚠️ 2026-08-16 (Nachmittag): Rollentausch aktiv/Standby

Der User hat einen **echten, dauerhaften Wechsel** bestätigt: **das ThinkPad
(`192.168.1.34`) ist ab jetzt der aktive Server**, `ffrattenberg`
(`192.168.1.238`) wird zum Standby. Die Rollenbezeichnungen im Abschnitt
unten ("aktiver Server" = ffrattenberg, "Standby" = ThinkPad) sind seitdem
NICHT mehr aktuell und wurden bewusst nicht überall nachgezogen (Domain/
SSH-Alias-Namen bleiben unverändert, nur wer tatsächlich Live-Traffic
bekommt hat sich geändert). **Vor jeder Aktion, die "den aktiven Server"
betrifft, den User fragen, welcher gerade gemeint ist**, bis dieser
Abschnitt vollständig aktualisiert ist. Insbesondere:
- Router-Portweiterleitung 80/443 auf `.34` wurde vom User bereits
  umgestellt und bestätigt funktionsfähig (2026-08-16).
- Der ESP32 spricht wegen des Hairpin-NAT-Workarounds eine FEST
  eingestellte lokale App-URL (nicht die Domain) an - die muss beim User
  vor Ort auf `http://192.168.1.34:8000/api/zeitmessung/event` umgestellt
  werden (seriell: `appurl <url>`, oder `http://<esp32-ip>/wlan-wechseln`
  im Browser im selben LAN) - kann NICHT remote per SSH erledigt werden.
- **Hairpin-NAT betrifft bestätigt auch normale Handy-Browser, nicht nur
  das ESP32** (2026-08-16): `curl` gegen die öffentliche Domain von BEIDEN
  Servern aus (selbst im Veranstaltungs-WLAN) schlägt mit "Connection
  refused" fehl - identischer Fehler wie beim User im Handy-Browser
  (`net::ERR_CONNECTION_REFUSED`, getestet mit DuckDuckGo-Browser) beim
  Aufruf von `https://ffrattenberg.duckdns.org/` aus demselben WLAN.
  Fix: Geräte IM Veranstaltungs-WLAN müssen die lokalen Adressen nutzen,
  nicht die öffentliche Domain (siehe LAN-Ports oben, Produktion `:8000`,
  test1/test2/generalprobe `:8001`-`:8003`).

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

**USB-Sicherung (seit 2026-08-16, auf dem ThinkPad):** `deployment/usb-backup-mount-einrichten.sh`
(einmalig, sudo, fstab-Eintrag per USB-UUID nach `/mnt/usb-backups`) +
`deployment/usb-instanz-backup.sh` (Cron alle 5 Min., `pg_dump` je Instanz
nach `<instanz>_sicherung_<zeitstempel>.sql.gz`, überspringt unveränderte
DBs anhand `pg_stat_database`, sha256-Prüfsumme, Rotation auf die letzten
288 Sicherungen je Instanz). Läuft nachweislich (verifiziert 2026-08-16).
Noch NICHT auf `ffrattenberg` (.238) eingerichtet - dortiger USB-Stick hat
eine andere UUID als in `usb-backup-mount-einrichten.sh` hinterlegt, Skript
müsste dafür angepasst werden.

**Deckel/Sleep-Schutz (seit 2026-08-16, auf dem ThinkPad):**
`deployment/thinkpad-kein-standby.sh` (einmalig, sudo) deaktiviert
Suspend/Hibernate/Lid-Switch-Aktionen systemweit - wichtig, seit das
ThinkPad der aktive Server ist (siehe Rollentausch-Hinweis oben). Bereits
angewendet, verifiziert 2026-08-16.

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

Der USB-Speicher am Standby (`FELFERTRANS`, UUID `B483-A120`) dient für
automatische Datenbank-Sicherungen. `/home/hans/usb-instanz-backup.sh` läuft
alle 5 Minuten per Benutzer-Cronjob und sichert bei tatsächlichen
Datenbankänderungen `ffrattenberg`,
`ffrattenberg-generalprobe`, `ffrattenberg-test1` und `ffrattenberg-test2`.
Jeder Dateiname enthält zwingend den Instanznamen, z.B.
`ffrattenberg-test1_sicherung_YYYYMMDD_HHMMSS.sql.gz`; daneben liegt jeweils
eine SHA-256-Datei. Pro Instanz werden 288 Sicherungen aufbewahrt (mindestens
24 Stunden bei durchgehenden Änderungen im 5-Minuten-Takt). Für einen
stabilen Mount nach Neustarts muss einmalig
`sudo /home/hans/usb-backup-mount-einrichten.sh` ausgeführt werden; Ziel ist
danach `/mnt/usb-backups/ffrattenberg-backups`.

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
- Zeitmessung-Weiterleitung an mehrere Instanzen (seit Build 20): Der ESP32
  kennt weiterhin nur EIN Ziel (keine Firmware-Änderung). Stattdessen
  melden sich test1/test2/generalprobe beim Start selbst bei der
  Produktions-Instanz an (`POST /api/zeitmessung/abonnieren`, erreichbar
  über das gemeinsame Docker-Netz `traefik` als `app-ffrattenberg:8000`)
  und erneuern das Abonnement alle 60s (Ablauf nach 180s ohne Erneuerung -
  heilt sich nach einem Neustart der Produktion oder des Abonnenten von
  selbst, kein manuelles Aufräumen nötig). Jedes eingehende ESP32-Ereignis
  wird serverseitig per Fire-and-forget an alle aktiven Abonnenten
  weitergereicht. Siehe `app/blueprints/zeitmessung.py`
  (`abonnieren`/`_an_abonnenten_weiterleiten`, Abonnentenliste bewusst nur
  im Prozessspeicher) und `app/__init__.py` (`_bei_quelle_anmelden`,
  Konfiguration über `ZEITMESSUNG_QUELLE_URL`/`ZEITMESSUNG_QUELLE_API_KEY`).
  Je Server unabhängig (Standby-Instanzen melden sich nur bei der
  Produktion DES EIGENEN Servers an, keine serverübergreifende
  Weiterleitung).
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
