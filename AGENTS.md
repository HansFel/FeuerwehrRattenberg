# Projekt-Kontext für KI-Assistenten (Claude, Codex, ...)

Diese Datei wird **nur von KI-Assistenten gepflegt** (nicht von der App
generiert, nicht von Hand durch Admins). Sie ist der feste Ort für
Projektüberblick, Architektur-Konventionen und Kontext, der über einzelne
Chat-Sessions hinaus erhalten bleiben soll.

Für den aktuellen **Aufgaben-/Wunschzettel der Administratoren** siehe
stattdessen `ANFORDERUNGEN.md` (wird automatisch aus der App exportiert,
ändert sich bei jeder Admin-Aktion im Bereich "Anforderungen").

_(Stand 2026-08-19. Bei Widersprüchen zum aktuellen Code gilt der Code -
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

## Verbindliches fachliches Regelwerk

Das Turnierschema steht zentral in **`TURNIERREGELN.md`**. Diese Datei ist für
alle Änderungen an Auslosung, Zeitplan, Moderation, Zeitmessungszuordnung,
Wertung, Ranglisten und PDF-Ausgaben verbindlich. Jede Änderung in diesen
Bereichen muss damit kompatibel sein. Bei einem Widerspruch nicht eigenständig
eine fachliche Regel verändern, sondern zuerst die ausdrückliche Entscheidung
der Veranstalter einholen und danach Regelwerk, Implementierung und Tests
gemeinsam aktualisieren.

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

Die aktive Rolle `ausschank` wird von der allgemeinen Startseite direkt auf
`/ausschank/` weitergeleitet. Dieses bewusst reduzierte Dashboard zeigt
Gruppenauswahl, Getränke-Tippbuttons, eine reine Pfandrückgabe-Berechnung ohne
Tisch-/Gruppenzuordnung sowie eine Rückgeldberechnung. „Bestellung und Bezahlung" erzeugt
eine bereits bezahlte Bestellung mit `tisch_nummer=0`, ordnet alle
Getränkepunkte der gewählten Gruppe zu und kehrt sofort zur leeren
Ausschankmaske zurück. Die allgemeine Bestellübersicht und Tischsuche gehören
nicht in dieses Dashboard; die dort eingegebene Pfandrückgabe ist nur ein
Rechenposten und verändert keine gespeicherten Pfandbestände.

**Ausschank-Dashboard seit Build 26 (2026-08-17) überarbeitet:** Die

**Kellner-Dashboard (seit Build 68, 2026-08-21):** Identisches
Layout wie Ausschank-Dashboard (gleiche CSS-Klassen, nummerierte Schritte):
(1) Gruppe auswaehlen, (2) alle Artikel antippen (Essen orange +
Getraenke blau), (3) generischer "Pfand zurueck" Button (1,00 EUR pro Stueck),
(4) Rueckgeldberechnung. Bestellung wird sofort als bezahlt gebucht mit
`tisch_nummer=0` (wie Ausschank, keine Tischnummer mehr noetig).
Getraenkepunkte nur fuer Getraenke (KATEGORIE_GETRAENK), nicht fuer Speisen -
unabhaengig von der Gruppe, entscheidet allein die Artikel-Kategorie.
Route: `/kellner/`, `@rolle_noetig("kellner", "organisator")`, automatische
Weiterleitung von Startseite bei aktiver Rolle "kellner". Dateien:
`app/templates/kellner_dashboard.html`,
`app/blueprints/bestellung.py: kellner_dashboard()`.

**Gruppe ist OPTIONAL, nicht Pflicht (seit 2026-08-21, Kellner UND
Ausschank):** Auf Wunsch des Users - auch spontane Einzelverkaeufe ohne
Gruppenzuordnung muessen bezahlbar sein. Ohne Gruppe: `team_id=None` und
0 Getraenkepunkte auf der/den betroffenen Position(en) (kein Team, dem man
sie gutschreiben koennte) - die Bestellung selbst wird trotzdem normal als
bezahlt gebucht. Weiterhin Pflicht: mindestens 1 Artikel/Getraenk. Kein
`required` mehr auf dem `team_id`-Select, Absende-Button nur noch von
"mindestens 1 Artikel gewaehlt" abhaengig, nicht mehr von der Gruppe.
Tests: `tests/test_bestellung.py::
test_kellner_dashboard_ohne_gruppe_keine_punkte`,
`test_kellner_dashboard_mit_gruppe_zaehlen_nur_getraenke`,
`test_ausschank_braucht_mindestens_ein_getraenk_aber_keine_gruppe`.

**Ausschank-Dashboard seit Build 26 (2026-08-17) ueberarbeitet:** Die
Getränke-Buttons zeigen den Pfand-Anteil separat neben dem Preis an (z.B.
"Bier 4,00 € + 1,00 € Pfand"). Statt einzelner Pfand-Buttons pro Getränk
gibt es **einen einzigen generischen "Pfand zurück" Button** mit +/- Zähler,
der pauschal 1,00 € pro zurückgegebenem Behälter abzieht (Formularfeld
`pfand_zurueck`, backend in `bestellung.py: ausschank_dashboard()`).
Die Zusammenfassung listet vier Zeilen: Getränke / Pfand (neu) /
Pfand zurück / Zu bezahlen. Dateien: `app/templates/ausschank_dashboard.html`,
`app/blueprints/bestellung.py`, `app/static/css/style.css`,
`tests/test_bestellung.py`.

## Produktions-Deployment

**Beste Einzelzeit (vorbereitet für Build 84):** `app/wertung.py:
beste_einzelzeit()` ermittelt rein lesend die schnellste positive Teilzeit aus
allen vier Teilzeiten aller vollständig gemessenen `NotfallBahn`-Datensätze.
Ausgegeben werden Läufername (über Mitgliedsposition 1–4), Mannschaft, Lauf,
Bahn und Zeit in Webwertung, live gepollter Moderation, live gepollter
Besucheransicht und Gesamtwertungs-PDF. Unvollständige/abgebrochene Bahnen
werden ignoriert. Diese Auszeichnung ist rein informativ und verändert laut
`TURNIERREGELN.md` weder Weiterkommen noch Platzierung. Die Besucheransicht
zeigt damit als bewusst gewünschte Ausnahme den Namen des aktuell schnellsten
Läufers; andere Mitgliedsnamen bleiben dort verborgen.

**Strafenkatalog-Gnadenfenster für den vorherigen Lauf (Build 83,
2026-08-22):** Bugfix, während des laufenden Wettkampfs entdeckt und (auf
expliziten Wunsch des Users) erst in einer Pause deployt: Punkterichter
dürfen über `/strafen/` nur Teams aus dem aktuell im Moderator-Dashboard
eingestellten Lauf (`ModeratorStatus`) bestrafen. Das automatische
Weiterschalten des Moderator-Status
(`moderator.py:_lauf_automatisch_weiterruecken`, läuft bei jedem
Dashboard-Poll) springt aber SOFORT zum nächsten Heat, sobald alle Zeiten
eines Laufs da sind - dadurch fiel das gerade fertig gelaufene Team
praktisch augenblicklich (nur wenige Sekunden Fenster) aus der erlaubten
Liste. `strafen.py:_aktuelle_teams()` erlaubt jetzt zusätzlich Teams des
unmittelbar VORHERIGEN Heats (nicht beliebig weit zurück). Tests:
`tests/test_strafen.py::
test_strafe_fuer_team_des_unmittelbar_vorherigen_heats_erlaubt`,
`test_strafe_fuer_team_zwei_heats_zurueck_bleibt_abgelehnt`.

**Doppelte Disziplin bereinigt (2026-08-22, reine Datenkorrektur, kein
Code):** Produktions-DB enthielt zwei fast identische Disziplinen
("Siloplanen Race" ID 1 ohne Ergebnisse, "Siloplanenrace 22.08.2026" ID 2
mit den echten Live-Ergebnissen) - Besucher-Zeitplan
(`app/blueprints/besucher.py`) zeigt bewusst JEDE Disziplin mit
Startplätzen, dadurch erschienen beide, die alte sogar zuerst
(alphabetisch vor der neuen). ID 1 (84 Startplätze, 0 mit Ergebnis, keine
Fremdschlüssel-Referenzen von `ergebnis`/`notfall_bahn`) wurde gelöscht.
Bei künftigen Disziplin-Anlagen auf Duplikate achten, bevor Startlisten
importiert/ausgelost werden.

**Pausenregel bei automatischer Auslosung (ab Build 82):** Bei allen
automatisch erzeugten Läufen außer kleinem/großem Finale wird bestmöglich
versucht, zwischen zwei Einsätzen derselben Mannschaft mindestens einen
vollständigen anderen Lauf einzuplanen. Die fachliche Reihenfolge ist jedoch
hart und hat Vorrang: schlechteste Platzierungsläufe zuerst, danach die
Halbfinale. Ist eine Pause innerhalb dieser Reihenfolge nicht möglich, wird
die Runde trotzdem erzeugt und niemals umsortiert oder blockiert. Bereits
gespeicherte Zeitpläne werden durch das Update nicht nachträglich verändert.
Implementierung und Tests:
`app/blueprints/zeitplan.py`, `tests/test_zeitplan.py`.

**Manuelles Neuladen der Web-Worker (seit Build 81):** Im nur für
Administratoren zugänglichen Bereich **Datensicherung** gibt es den Button
„Anwendung neu laden“. Er sendet nach kurzer Verzögerung ein `SIGHUP` an den
Gunicorn-Master und ersetzt damit alle Web-Worker samt Datenbankverbindungen
kontrolliert. PostgreSQL, Docker, Traefik und andere Dienste werden nicht neu
gestartet. Die App kann dabei wenige Sekunden kurz nicht erreichbar sein. Der
Button funktioniert absichtlich nur unter Gunicorn, damit im lokalen
Entwicklungsbetrieb kein fremder Elternprozess signalisiert wird. Route:
`POST /sicherung/anwendung-neuladen`, Implementierung:
`app/blueprints/sicherung.py`, Oberfläche:
`app/templates/sicherung/index.html`.

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

**Kritischer Bug gefunden und gefixt (2026-08-16):** Bei einem
serverübergreifenden Abonnement (ThinkPad-Produktion abonniert bei
ffrattenberg-Produktion) geriet ffrattenberg versehentlich als Abonnent
BEI SICH SELBST in die `zeitmessung_abonnent`-Tabelle (vermutlich Artefakt
eines manuellen Debug-Tests) - Ergebnis: Endlosschleife, jedes Ereignis
wurde an sich selbst weitergeleitet, kam erneut an, wurde wieder
weitergeleitet usw. Zehntausende Duplikate in Minuten, auch auf dem
ThinkPad (der ja ebenfalls Abonnent war). **Fix:** `event_empfangen()` in
`app/blueprints/zeitmessung.py` leitet ein Ereignis NIE weiter, wenn es
selbst schon den Header `X-Weitergeleitet: 1` trägt (wird beim
Weiterleiten gesetzt) - jedes Ereignis macht dadurch maximal EINEN Hop,
unabhängig von der Abonnenten-Topologie. Test:
`test_weitergeleitetes_ereignis_wird_nicht_erneut_weitergeleitet` in
`tests/test_zeitmessung.py`. **Zusätzlich beim Prüfen von
Abonnenten-Listen immer auf Selbstreferenzen achten**
(`ziel_url` == eigener Event-Endpunkt).

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

**WICHTIG: --env-file bei Test-Instanzen zwingend (seit 2026-08-17
schmerzhaft gelernt):** Docker Compose lädt standardmäßig nur `.env`
(Produktions-Env) im aktuellen Verzeichnis, NICHT `.env.test`. Ohne
`--env-file deployment/.env.test` fehlen DB-Passwörter/Secrets und die
Test-Container crash-loopen sofort (`fe_sendauth: no password supplied`).
Korrekte Aufrufe:

```bash
# Test-Instanzen (immer mit --env-file!):
docker compose -f deployment/docker-compose.ffrattenberg-test.yml \
  --env-file deployment/.env.test up -d

# Produktion (.env wird automatisch geladen, --env-file optional aber empfohlen):
docker compose -f deployment/docker-compose.ffrattenberg.yml \
  --env-file deployment/.env up -d --build
```

### Deploy aus DSH (DeepSeek Harness) per SSH auf das ThinkPad (seit 2026-08-17)

SSH vom Entwicklungs-PC (DSH-Sandbox) zum ThinkPad funktioniert mit dem
dedizierten Schlüssel (siehe Abschnitt "Ersatzserver" unten für Pfad):
```bash
ssh -o IdentitiesOnly=yes -o ConnectTimeout=10 \
  -i C:\Users\<User>\.ssh\id_ed25519_ffrattenberg hans@192.168.1.14 '<cmd>'
```
**DSH-Sandbox-Falle:** SSH wird unter `workspace-write` blockiert
("failed to initialize w32posix wrapper") – braucht
`sandbox_permissions: "danger-full-access"` im `pwsh`-Tool-Aufruf.
Auch `git push` (HTTPS nach GitHub) braucht dasselbe, da der
`git-remote-https`-Helper stdio-Pipes erzeugt, die die Sandbox blockiert
("cannot create standard input pipe for remote-https: Permission denied").
Die Approval-Policy muss `ask` oder weaker sein, damit die Eskalation
funktioniert (bei `never` wird sie automatisch abgelehnt).

**Aktueller Deploy-Stand (2026-08-21):** ThinkPad läuft Build 79
(ffrattenberg-app:build79 als Image-Tag) auf ALLEN vier Instanzen
(Produktion + test1/test2/generalprobe), im Footer aller vier als
"Build 79 · 2026-08-21 17:55" verifiziert. BUILD_TAG in deployment/.env
und deployment/.env.test beide auf build79 – bewusst gleich gehalten,
da Test-Instanzen dasselbe Image nutzen wie Produktion. Beim nächsten Deploy
beide hochzählen. Standby-Server ffrattenberg (.238) Status unbekannt
(bei diesem Deploy nicht geprüft). ThinkPad-LAN-IP aktuell: 192.168.1.34
(per SSH `hostname -I` verifiziert, 2026-08-21). Tailscale-IP: 100.119.59.86
(funktioniert auch wenn sich die LAN-IP ändert – für SSH-Deploy
empfohlen, beim Build-79-Deploy erfolgreich genutzt). Desktop-App auf
`felferlinuxlab` ebenfalls auf Build 79-Stand gebracht (per scp, da dort
kein git-Checkout, sondern Dateikopie) und neu gestartet.

**Wichtige Falle (2026-08-18 erlebt):** `docker-compose.ffrattenberg-test.yml`
hat für die App-Services (`app-test1`/`app-test2`/`app-generalprobe`) **KEINEN
eigenen `build:`-Abschnitt**, nur `image: ffrattenberg-app:${BUILD_TAG}` –
`docker compose ... --build` baut dort also NICHTS, sondern nutzt einfach
ein evtl. schon vorhandenes, altes Image mit diesem Tag (falls der Tag
zufällig mit einem früheren Deploy übereinstimmt, startet Test lautlos mit
altem Code, ohne Fehlermeldung). **`.env` (Produktion, hat den echten
`build:`-Schritt) und `.env.test` MÜSSEN nach jedem Deploy auf denselben
`BUILD_TAG` gesetzt werden**, nicht unabhängig hochgezählt – sonst bekommt
Test nie den gerade gebauten Code. Nach dem Deploy immer per
`curl .../test1/... | grep Build` verifizieren, nicht nur auf der Produktion.

**Pfand-Konfiguration auf test1 (2026-08-17 per SQL gesetzt):** Alle
Getränke (`kategorie='getraenk'`) auf test1 haben `pfand_pro_einheit=1.0`.
Auf Produktion und den anderen Test-Instanzen ist das noch NICHT gesetzt
(alle 0.0) – muss dort bei Bedarf nachgeholt werden (entweder über die
Speisekarte in der App als Organisator, oder per SQL:
`UPDATE artikel SET pfand_pro_einheit=1.0 WHERE kategorie='getraenk';`
in der jeweiligen DB). Der generische "Pfand zurück"-Button im
Ausschank-Dashboard subtrahiert fest 1,00 € pro Stück unabhängig vom
`pfand_pro_einheit`-Wert der Artikel – er ist immer sichtbar, auch ohne
konfiguriertes Pfand.

### ⚠️ 2026-08-16 (Nachmittag): Rollentausch aktiv/Standby

Der User hat einen **echten, dauerhaften Wechsel** bestätigt: **das ThinkPad
ist ab jetzt der aktive Server**, `ffrattenberg` (`192.168.1.238`) wird zum
Standby. Die Rollenbezeichnungen im Abschnitt unten ("aktiver Server" =
ffrattenberg, "Standby" = ThinkPad) sind seitdem NICHT mehr aktuell und
wurden bewusst nicht überall nachgezogen (Domain/SSH-Alias-Namen bleiben
unverändert, nur wer tatsächlich Live-Traffic bekommt hat sich geändert).
**Vor jeder Aktion, die "den aktiven Server" betrifft, den User fragen,
welcher gerade gemeint ist**, bis dieser Abschnitt vollständig aktualisiert
ist. Insbesondere:
- **ThinkPad-IP ist NICHT stabil** - **keine DHCP-Reservierung** eingerichtet.
  War zunächst `192.168.1.34`, hat sich am 2026-08-16 (später am Tag) auf
  `192.168.1.14` geändert (per SSH verifiziert: `hostname` →
  `hans-ThinkPad-E590`, laufende Produktions-Container). **Bei jeder
  netzwerkbezogenen Aktion (Router-Portweiterleitung, AdGuard-DNS-Rewrite,
  ESP32/Desktop-App-URL) zuerst die AKTUELLE IP per SSH verifizieren, nicht
  blind eine hier notierte IP übernehmen** - sie kann sich jederzeit wieder
  ändern.
- Router-Portweiterleitung 80/443 wurde vom User bereits auf den aktiven
  Server umgestellt und bestätigt funktionsfähig (2026-08-16).
- Der ESP32 spricht wegen des Hairpin-NAT-Workarounds eine FEST
  eingestellte lokale App-URL (nicht die Domain) an - muss beim User vor Ort
  auf `http://<aktuelle-ThinkPad-IP>:8000/api/zeitmessung/event` umgestellt
  werden (seriell: `appurl <url>`, oder `http://<esp32-ip>/wlan-wechseln` im
  Browser im selben LAN) - kann NICHT remote per SSH erledigt werden. **Seit
  dem Hardware-Wechsel auf Arduino Mega + Desktop-App (siehe oben) betrifft
  das nur noch die alte ESP32-Firmware, nicht mehr den produktiven Weg.**
- **Hairpin-NAT betrifft bestätigt auch normale Handy-Browser, nicht nur
  das ESP32** (2026-08-16): `curl` gegen die öffentliche Domain von BEIDEN
  Servern aus (selbst im Veranstaltungs-WLAN) schlägt mit "Connection
  refused" fehl - identischer Fehler wie beim User im Handy-Browser
  (`net::ERR_CONNECTION_REFUSED`, getestet mit DuckDuckGo-Browser) beim
  Aufruf von `https://ffrattenberg.duckdns.org/` aus demselben WLAN.
  Fix: Geräte IM Veranstaltungs-WLAN müssen die lokalen Adressen nutzen,
  nicht die öffentliche Domain (siehe LAN-Ports oben, Produktion `:8000`,
  test1/test2/generalprobe `:8001`-`:8003`) - **ODER siehe den neuen
  Abschnitt "Netzwerk: Split-DNS für internen Zugriff" direkt unten, der das
  seit 2026-08-17 für die Domain selbst löst.**

### Netzwerk: Split-DNS für internen Zugriff auf die Domain (seit 2026-08-17)

Der TCL-Router (Modell HH132VM, LTE/4G) hat **in seiner Weboberfläche kein
Feld, um Clients per DHCP einen eigenen DNS-Server zuzuweisen** - weder
unter LAN/DHCP-Server noch unter WAN (direkt in der UI geprüft, beide Seiten
durchgesehen). Eine netzweite automatische Lösung des Hairpin-NAT-Problems
über diesen Router ist damit nicht möglich.

**Umgesetzte Lösung: AdGuard Home** läuft als Docker-Container auf dem
aktiven Server (`~/apps/adguard/docker-compose.yml`):
- DNS-Dienst an die LAN-IP des Servers gebunden (NICHT `0.0.0.0` - Konflikt
  mit `systemd-resolved`, das schon auf mehreren spezifischen Adressen
  lauscht). Docker-Compose-Ports deshalb explizit `<LAN-IP>:53:53` statt
  `53:53`.
- Admin-Weboberfläche NICHT auf dem AdGuard-Standard-Port 80 (kollidiert mit
  Traefik), sondern auf `<LAN-IP>:3001` gemappt (Container hört intern auf
  80, wenn im Setup-Assistenten der vorgeschlagene Port übernommen wurde).
- DNS-Rewrite unter „Filters → DNS-Umschreibungen": `ffrattenberg.duckdns.org`
  → aktuelle LAN-IP des Servers. Normale Domains werden weiterhin korrekt an
  Upstream weitergeleitet (kein Full-Pihole-Ersatz nötig).

**Da der Router den DNS nicht automatisch verteilt, muss JEDER Client
manuell auf den AdGuard-DNS umgestellt werden** (Netzwerkadapter-
Einstellungen, DNS-Server = AdGuard-IP). Verifizierter Stolperstein dabei
(2026-08-17): Ein Windows-Client hatte zusätzlich einen alten, falschen
`ffrattenberg*.duckdns.org`-Eintrag in `C:\Windows\System32\drivers\etc\hosts`,
der die AdGuard-Auflösung überschrieben hat - erst nach Entfernen dieses
Eintrags (PowerShell als Administrator, `Set-Content` auf die hosts-Datei) +
`ipconfig /flushdns` funktionierte der Zugriff auf die Domain von diesem
Client aus. **How to apply:** Bei "von innen nicht erreichbar" IMMER zuerst
prüfen, ob der Client (a) den AdGuard-DNS überhaupt eingetragen hat und (b)
keine alte `hosts`-Zeile die AdGuard-Auflösung überschreibt. Bis DNS auf
allen benötigten Geräten manuell umgestellt ist, bleibt Port 8000 (siehe
oben) der Fallback.

**Update 2026-08-19:** Seitdem zusätzlich **Tailscale** auf ThinkPad +
Entwicklungs-PC eingerichtet (SSH funktioniert dadurch auch ohne
Port-22-Weiterleitung, siehe `ssh -i ~/.ssh/id_ed25519_ffrattenberg
hans@100.119.59.86` bzw. `tailscale ssh hans@hans-thinkpad-e590` - Letzteres
verlangt gelegentlich eine erneute manuelle Bestätigung über einen
Tailscale-Link ("requires an additional check"), dann lieber den
regulären SSH-Schlüssel nehmen). Ausserdem wurde **AdGuard zusaetzlich als
DHCP-Server** eingerichtet (nicht mehr nur DNS), weil der Hauptrouter
selbst GAR KEIN DHCP macht (war zuvor ein unbekanntes/inzwischen
abgeschaltetes Zweitgeraet) - das sollte das Problem "jeder Client braucht
manuell den AdGuard-DNS eingetragen" beheben, da AdGuard beim DHCP-Lease
automatisch sich selbst als DNS mitgibt.

**Trotzdem weiterhin nicht wirklich geloest: Die LAN-IP des ThinkPad
driftet nach wie vor** (WLAN vs. Kabel wechselt offenbar von selbst) -
zuletzt beobachtet `.238` → `.14` → `.177` → `.34` (Stand 2026-08-19,
frueher Abend). Eine DHCP-Reservierung wurde mehrfach versucht, haelt aber
offenbar nicht dauerhaft. **AdGuards eigene DNS-Rewrite/Bind-Config wird
bei jedem Wechsel manuell nachgezogen** (`docker exec adguardhome cat
/opt/adguardhome/conf/AdGuardHome.yaml` zeigt aktuelle `bind_hosts`/
`address` - **immer zuerst hier die tatsaechlich aktuelle IP prüfen**,
nicht auf einen hier dokumentierten Wert verlassen). Wirklich stabile
Lösung (feste IP im Router UND passendes Interface/Kabel statt WLAN
erzwingen) steht weiterhin aus.

**Weiterer Fallback: Zugriff per SSH-Tunnel** - falls weder Domain noch
direkter LAN-Port 8000 erreichbar sind (z.B. von außerhalb des
Veranstaltungs-WLANs, oder wenn gerade keine der beiden Lösungen oben
greift), lässt sich jede Instanz/jeder Pfad über einen SSH-Tunnel zum Server
erreichen, ohne dass DNS oder Hairpin-NAT überhaupt eine Rolle spielen -
SSH (Port 22) ist von den bekannten Problemen hier nicht betroffen:

```bash
ssh -L 8000:localhost:8000 hans@<aktuelle-Server-IP>
```

Danach im Browser auf dem tunnelnden Rechner z.B.
`http://localhost:8000/test1/ausschank/` öffnen (Pfad/Instanz beliebig,
Port muss zur Ziel-Instanz passen: Produktion 8000, test1/test2/generalprobe
8001-8003, siehe oben). Erfordert einen funktionierenden SSH-Zugriff auf den
Server (siehe SSH-Alias/Schlüssel im Abschnitt "Ersatzserver" unten) sowie
dass der tunnelnde Rechner den Server auf Port 22 erreicht - meist eher
gegeben als HTTP/HTTPS, da Port 22 nicht denselben Hairpin-Einschränkungen
unterliegt wie 80/443. Tunnel bleibt nur für die Dauer der SSH-Sitzung
bestehen (Terminal offen lassen).

### Ersatzserver / Standby während der Veranstaltung

Zweiter Server: **`hans@hans-ThinkPad-E590`**, Linux Mint 22.3, WLAN-MAC
`20:79:18:b8:de:bd`. **Ist seit dem Rollentausch (siehe oben) inzwischen der
AKTIVE Produktionsserver**, nicht mehr nur Standby - die IP-Angabe unten
kann daher veraltet sein, vor jeder Aktion per SSH `hostname -I` prüfen
(keine DHCP-Reservierung, hat sich schon einmal geändert: `192.168.1.34` →
`192.168.1.14`, Stand 2026-08-17).

**SSH-Zugriff (getestet, funktioniert ohne Passphrase-Abfrage):**
```bash
ssh -i ~/.ssh/id_ed25519_ffrattenberg -o IdentitiesOnly=yes hans@192.168.1.14
```
Auf Windows-Entwicklungsrechnern denselben Pfad unter
`C:\Users\<User>\.ssh\id_ed25519_ffrattenberg` verwenden. **Nicht** den
Standard-Schlüssel `~/.ssh/id_ed25519` (ohne `-ffrattenberg`-Suffix)
benutzen - der ist passphrasegeschützt und die Passphrase ist nicht
bekannt/hinterlegt; der dedizierte `..._ffrattenberg`-Schlüssel funktioniert
dagegen ohne Passphrase-Abfrage. Falls IP oder Hostname nicht auflösen: erst
`ping 192.168.1.14` bzw. aktuelle IP anderweitig ermitteln, bevor man von
"Server ist offline" ausgeht - der Rechner kann auch nur gerade
ausgeschaltet/getrennt sein.

Docker läuft; Docker Compose wurde benutzerspezifisch unter
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
- **"Testdaten löschen"** (seit 2026-08-18, `/sicherung/`): löscht
  Zeitereignis/NotfallLauf+Bahn/Bestellung+BestellPosition/Strafe/Ergebnis
  und setzt `Startplatz.ergebnis_sekunden` zurück (Startplatz-Zeile selbst
  bleibt als Zeitplan erhalten). Team/Mitglied/Artikel (Preise) bewusst
  NICHT angefasst. Legt wie „Wiederherstellen" vorher automatisch eine
  Sicherung an (`typ="vor-testdaten-loeschen"`).

## Wichtige, teils noch offene fachliche Fragen

- **Turnierformat Siloplanen-Race – seit 2026-08-18 abschließend geklärt UND
  automatisiert** (löst die früher widersprüchlichen Notizen ab): 4 Bahnen,
  2 Vorrunden (jedes Team läuft 2× gegen wechselnde Gegner, Zeiten addiert
  → Gesamtrangliste). Plätze 1-8 → 2 Halbfinal-Läufe (**zufällig** ausgelost,
  `random.shuffle`). Aus den 8 Halbfinalisten: die 4 schnellsten Zeiten
  insgesamt → Großes Finale (Platz 1-4), die anderen 4 → Kleines Finale
  (Platz 5-8). Restliche Plätze 9-N in 4er-Gruppen als eigene
  Platzierungsläufe, von unten nach oben gruppiert (ein Rest <4 Teams bildet
  die beste verbleibende Gruppe). **Laufreihenfolge**: Platzierungsläufe
  zuerst (schlechteste Gruppe zuerst), dann Halbfinale, dann Kleines Finale,
  zuletzt Großes Finale.

  Vollautomatisiert unter `/zeitplan/disziplin/<id>/rangliste`
  (`app/blueprints/zeitplan.py: _naechste_runde_erzeugen()` +
  `_finale_erzeugen()`, Buttons erscheinen erst wenn die jeweilige
  Vorstufe vollständig ist). **Heat-Namensschema steuert Reihenfolge UND
  Ziel-Platzerkennung**: jeder neue Lauf bekommt eine fortlaufende Nummer
  als Präfix (sortiert numerisch hinter die Vorrunde ein, siehe
  `_heats_in_reihenfolge`); Platzierungsläufe und beide Finals tragen
  zusätzlich `"Platz <von>-<bis>"` im Namen (Regex `Platz (\d+)-(\d+)`) -
  das ist die Grundlage für `app/wertung.py: finale_platzierung()`.
  Manuelles Zusammenstellen (bestehendes Formular auf derselben Seite)
  bleibt als Fallback für Sonderfälle erhalten.

  **Gesamtwertung ist bracket-aware** (seit Build 39, löst eine Ungenauigkeit
  aus Build 38 - reine Zeitmessungs-Summe - für den echten Turnierverlauf):
  Sobald ein Team einen Ziellauf (Platzierungslauf/Finale) mit Ergebnis
  absolviert hat, ist DAS die endgültige Platzierung (`von + Rang-im-Lauf`,
  inkl. Strafsekunden als Sortierkriterium innerhalb dieses einen Laufs) -
  ändert sich nicht mehr durch spätere Läufe. Teams ohne Ziellauf werden in
  `/wertung/` als „vorläufig" markiert und nach der Vorrunden-Summenzeit
  gereiht.
- Zeitmessung: nur noch 1 Öffner-Kontakt pro Bahn (nicht mehr Start+Ziel
  getrennt), siehe `firmware/zeitmessung/README.md`. Die Zuordnung "welche
  der 5 Auslösungen pro Bahn war welcher Läufer" ist **seit 2026-08-16
  automatisiert**, sofern ein `NotfallLauf` mit Team-Besetzung je Bahn
  aktiviert ist (`NotfallLauf.aktiv`) - siehe
  `app/blueprints/zeitmessung.py:_automatische_zuordnung_pruefen()` und
  `app/blueprints/notfall.py:aktivieren()`. Ohne Aktivierung (oder falls die
  Automatik ausfällt) bleibt die manuelle Handeingabe unter `/notfall/` der
  Fallback; die visuelle laufende Nummer in `/zeitmessung/` bleibt zusätzlich
  bestehen, unabhängig von der Automatik.
- **Zeitmessung-Hardware seit 2026-08-16 gewechselt: Arduino Mega 2560 statt
  ESP32.** Grund: Bedenken der Veranstalter bei Strom-/WLAN-Ausfall am
  Veranstaltungsort. Der Mega hat kein WLAN, meldet Kontaktauslösungen nur
  über USB-Seriell an eine neue lokale **Desktop-App** (`desktop-app/`,
  PySide6), die die Ereignisse zuerst in einer eigenen SQLite puffert und
  erst danach an denselben `/api/zeitmessung/event`-Endpoint sendet wie
  vorher der ESP32 (Endpoint selbst unverändert, ihm ist die Quelle egal).
  Ein Sync-Retry nach Timeout erzeugt dank `client_event_id`
  (`Zeitereignis.client_event_id`, Dedup-Prüfung in `event_empfangen()`)
  KEIN Duplikat. Firmware: `firmware/zeitmessung-mega/README.md` (serielles
  Zeilenprotokoll `READY`/`HEARTBEAT`/`EVENT`). Der bisherige ESP32-Weg
  (`firmware/zeitmessung/`) bleibt als Code erhalten, wird aber nicht mehr
  eingesetzt. Zeitnehmungs-PC beim Event: `hans@felferlinuxlab` (Linux).
- **Manueller Offline-Modus der Desktop-App (seit 2026-08-17):** Falls die
  LAN-Verbindung zur Webapp während des Wettkampfs ausfällt, tippt der
  Organisator die Team-**Startnummer** je Bahn direkt in der Desktop-App ein
  ("Lokalen Lauf starten") - die App bildet die serverseitige
  5-Auslösungen-Logik lokal nach (`desktop-app/zeitmessung_desktop/
  lokale_zuordnung.py`) und meldet das Ergebnis automatisch nach, sobald die
  Webapp wieder erreichbar ist (`lauf_import_worker.py` →
  `POST /notfall/api/importieren`, `app/blueprints/notfall.py:
  api_importieren()`, matcht per `Team.startnummer`, idempotent per
  `server_lauf_id`). Details: `desktop-app/README.md`.
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
- **Startfreigabe / Start-Fenster (Desktop-App):** Der frühere Button
  "Gemeinsamer Start" wurde vollständig entfernt. Es gibt weiterhin ein
  **5-Sekunden Start-Fenster** (seit 2026-08-19): nach der
  ersten Kontaktauslösung (egal welche Bahn/Quelle) haben andere Bahnen 5
  Sekunden Zeit für ihren eigenen 1. Kontakt. Danach bekommen Bahnen mit
  0 Kontakten automatisch den 1. Kontakt gesetzt (mit dem Zeitpunkt des
  ersten Kontakts) – verhindert taktisches Nicht-Auslösen. Jede Bahn braucht
  insgesamt 5 Kontakte (1 Start + 4 Handover/Ziel).
- **Brücke Startliste → Zeitmessung (seit 2026-08-17):** Bisher waren
  Zeitplan (`Startplatz`: Team/Disziplin/Bahn/Heat/Startzeit) und
  Zeitmessung-Automatik (`NotfallLauf`) komplett getrennt - der
  Organisator musste die Team-Besetzung für jeden Lauf doppelt eintragen.
  Jetzt: Knopf **„Zeitmessung für diesen Lauf freigeben"** im
  Moderator-Dashboard (`app/blueprints/notfall.py:
  aus_startliste_freigeben()`) erzeugt und aktiviert automatisch einen
  `NotfallLauf` aus dem dort eingestellten aktuellen Heat
  (`ModeratorStatus`) - Team-Besetzung kommt aus den `Startplatz`-
  Datensätzen dieses Heats. Jede erzeugte `NotfallBahn` bekommt
  `startplatz_id` gesetzt; sobald die Automatik die Zeiten vollständig
  zuordnet, wird `Startplatz.ergebnis_sekunden` automatisch zurück-
  geschrieben (`app/blueprints/zeitmessung.py:
  _automatische_zuordnung_pruefen()`). Schließt den Kreis Startliste →
  Messung → Ergebnis, OHNE die bestehende manuelle `/notfall/neu`-Eingabe
  zu ersetzen (bleibt Fallback für Läufe ohne Startplatz-Bezug).

  **Rollentrennung Moderator vs. Organisator (seit Build 45, 2026-08-19):**
  Die Lauffreigabe aus der Startliste darf **nur dem Organisator**
  zustehen. `aus_startliste_freigeben()` ist deshalb auf
  `@rolle_noetig("organisator")` beschränkt (vorher
  `startrichter, organisator`). Das Moderator-Dashboard
  (`app/templates/moderator/dashboard.html`) ist für die **aktive Rolle
  `moderator`** jetzt **rein Lese-Ansicht**: es zeigt „Gerade im Bewerb"
  (Disziplin/Heat + Bahnen + Teamnamen/Wehr) sowie Publikumsinfo,
  Sponsoren und Nachrichten, aber **keinen** „Zeitmessung für diesen Lauf
  freigeben"-Button und **nicht** die „Anzeige als Organisator steuern"-
  Steuerung. Beide werden per `dashboard_zeigt('organisator')` (aktive
  Rolle, nicht `darf()`) eingeblendet – erscheinen also nur, wenn der
  Benutzer als Organisator (oder Admin) agiert, nicht als Moderator.
  Der Startrichter behält seine manuelle Erfassung unter `/notfall/neu`
  + `/notfall/<id>/aktivieren` (unverändert `startrichter, organisator`),
  nur der Ein-Klick-Freigabe-Knopf aus der Startliste ist ihm entzogen.
  Tests: `tests/test_moderator.py::
  test_moderator_sieht_keinen_freigabe_button_organisator_schon`,
  `tests/test_notfall.py::
  test_aus_startliste_freigeben_startrichter_abgewiesen`.

**Team Challenge (seit Build 55, 2026-08-19):** Zweite, unabhängige
  Wertung neben der Siloplanen-Race-Zeitwertung. Setzt sich zusammen aus:
  - **🥤 Getränkepunkte**: automatisch aus dem Bestell-/Ausschank-System
    (Kellner/Ausschank können über Bestellungen Punkte für Teams sammeln)
  - **🎉 Fanpunkte**: manuell vom Organisator eingegeben (für Kreativität,
    Fankultur, Voting etc.) – Eingabeformular auf `/wertung/`, nur für
    `darf('organisator')`
  - **🏆 Gesamt** = Getränkepunkte + Fanpunkte, gereiht nach höchster = bester
  - **Getrennt von der Siloplanen-Race-Wertung**: die Zeitwertung enthält
    KEINE Getränkepunkte mehr (seit Build 57), nur Rangpunkte/Strafsekunden/Zeit
  - Team Challenge erscheint auf `/wertung/` (mit PDF-Export
    `/pdf/team_challenge.pdf`), im Moderator-Dashboard (als eigene Karte),
    und die Fanpunkte sind im `Team`-Modell als `fanpunkte`-Spalte gespeichert
    (Schema-Migration in `__init__.py`).
  - **Motto & Lieblingslied**: `Team.motto` und `Team.lieblingslied` werden
    im Moderator-Dashboard pro Bahn angezeigt (sowie "Alle Mannschaften"-
    Übersicht), zusätzlich der **Teamchef** (1. Mannschaftsmitglied,
    `Mitglied.position == 1`). Felder im Team-Bearbeiten-Formular.

**Moderator-Dashboard Layout (seit Build 58-60, angepasst Build 67):**
  Reihenfolge für die aktive Rolle Moderator/DJ: (1) Gerade im Bewerb +
  Teamchef/Motto/Lied, (2) **Nächster Lauf** (nur Info: Disziplin/Heat +
  Bahnen/Teams, OHNE Aktions-Buttons), (3) Publikumsinfo + Sponsoren +
  Nachrichten, (4) Siloplanen-Race-Wertung als eigene Karte, (5)
  Team-Challenge-Wertung als eigene Karte. Der Organisator sieht beim
  Nächsten Lauf zusätzlich die Buttons "Als aktuellen Lauf setzen" und
  "Zeitmessung freigeben" (`dashboard_zeigt('organisator')`, wie schon bei
  der Lauffreigabe). **"Abgeschlossener Lauf" wurde komplett entfernt**
  (Build 67, auf Wunsch des Users) - die zugehörige Backend-Funktion
  `_letzter_abgeschlossener_lauf()` in `app/blueprints/moderator.py` gibt
  es nicht mehr, ihre Ergebniszeiten stehen ohnehin schon in der
  Siloplanen-Race-Wertung direkt darunter. Tests:
  `tests/test_moderator.py::
  test_moderator_sieht_naechsten_lauf_unter_aktuellem_lauf`.

**Desktop-App Zeitnahme-Buttons (seit Build 51-54):**
  - **Bahn X START** (grün): manueller 1. Kontakt für einzelne Bahn (Fallback)
  - **Bahn X STOPP** (rot): manueller Kontakt für einzelne Bahn (Fallback)
  - **🚨 Lauf abbrechen**: Notfall-Stopp bei Verletzung (deaktiviert aktiven
    NotfallLauf serverseitig + lokalen Lauf, Teilzeiten bleiben erhalten)
  - **Live-Zwischenzeiten**: nach jedem Kontakt wird die entsprechende
    Läuferzeit sofort angezeigt (nicht erst warten bis alle 5 da sind),
    inkl. Kontakt-Zähler (x/5) pro Bahn

**DMX-Bahnbeleuchtung (seit 2026-08-21, Desktop-App):** Zweiter, vom Mega
  unabhängiger Arduino (Uno + MAX485 → DMX → 4x Eurolite PAR-56, je 1
  Scheinwerfer pro Bahn) über eine zweite serielle Schnittstelle
  angesteuert (`desktop-app/zeitmessung_desktop/bahnbeleuchtung.py`,
  eigener `dmx_port` in den Einstellungen, leer = deaktiviert). Zustand
  (aus/vorbereitung/start/**fertig**) wird aus dem Lauf-Status abgeleitet
  (`licht_zustand.py`, reine Logik, testbar ohne Hardware) - lokaler
  Offline-Lauf übernimmt nur, wenn kein aktiver Server-Lauf gemeldet ist.
  Ein vom Organisator neu freigegebener Server-Lauf hat immer Vorrang, damit
  ein alter vollständiger Offline-Lauf die Lichter nicht auf ROT festhält.
  Bei Webapp-Ausfall funktioniert der lokale Lauf weiterhin. Jede
  Kontaktauslösung lässt die
  jeweilige Bahn kurz weiß aufblitzen. Komplett optional/robust: fehlt der
  Port, läuft die Zeitmessung unbeeinflusst weiter. Hardware-Referenz/
  ursprünglicher Handoff: `DMX_Zeitmessung/README.md`. Auf echter Hardware
  verifiziert (2026-08-21, `felferlinuxlab`, zweites CH340-Gerät - **Achtung:
  Mega und DMX-Uno sind beide CH340 und daher an den Ports nicht
  unterscheidbar, wenn nur einer gerade angeschlossen ist** - vor jedem
  Einsatz beide Ports einzeln prüfen/zuordnen, bevor `com_port` und
  `dmx_port` gesetzt werden, sonst öffnet die App denselben Port zweimal).
  Zustände (seit 2026-08-21, Desktop-App): `aus` / `vorbereitung` (Amber, Lauf vorhanden
  aber nicht freigegeben) / `start` (GRÜN, sobald der Organisator die
  Zeitmessung freigibt - nicht erst beim 1. Kontakt) / `fertig` (ROT, Lauf
  vollständig). **Blau ("bereit") ist vorerst bewusst entfernt** (User:
  "die Farbe Blau können wir uns zurzeit sparen").
  **ROT-bei-Laufende (seit 2026-08-21, Desktop-App + Web-App):** Sobald ein
  Lauf vollständig ist (alle Team-Bahnen haben alle 4 Läuferzeiten),
  schalten die Lichter auf **ROT** (Zustand "fertig") und bleiben dort, bis
  der nächste Lauf freigegeben wird - der fertige Lauf bleibt serverseitig
  `aktiv`, bis er durch `aus_startliste_freigeben`/`aktivieren` eines neuen
  Laufs abgelöst wird, deshalb persistiert ROT ohne extra "Sperre". Die
  Vollständigkeit meldet `/notfall/api/aktiv` als `vollstaendig`
  (serverseitig berechnet: alle Team-Bahnen haben `gesamtzeit`), die
  Desktop-App leitet sie in `_beleuchtung_aktualisieren` an
  `licht_zustand.zustand_bestimmen` weiter (für den lokalen Offline-Lauf
  lokal aus `lokale_bahn.zeit_laeufer1-4` berechnet). Beim Freigeben des
  nächsten Laufs (neuer NotfallLauf aktiv, nicht vollständig) schaltet das
  Licht sofort wieder auf **GRÜN** ("start").
  **Auto-Weiterruptcken "Gerade im Bewerb" beim Laufende:** Sobald die
  letzte Bahn eines Heats fertig wird, schreibt
  `zeitmessung.py:_automatische_zuordnung_pruefen` das Ergebnis in
  `Startplatz.ergebnis_sekunden` zurück UND triggert sofort
  `moderator._lauf_automatisch_weiltruecken` (vorher nur beim
  Dashboard-Polling) - "Gerade im Bewerb" rückt also in dem Moment auf den
  nächsten Heat, in dem die letzte Zeit gespeichert wird, ohne auf das
  nächste Polling zu warten. Test:
  `tests/test_notfall.py::test_laufabschluss_rueckt_gerade_im_bewerb_auf_naechsten_heat`.
  **Kollisionsschutz seit 2026-08-21 (Desktop-App):** Die beiden
  Port-Dropdowns im Einstellungsdialog sind jetzt gekoppelt
  (`hauptfenster.py:EinstellungenDialog._ports_synchronisieren`, reine
  Logik Qt-frei in `seriell_ports.py`, getestet in
  `tests/test_seriell_ports.py`): der in einem Dropdown gewählte Port
  wird im anderen ausgeblendet, und eine bestehende Kollision (gleicher
  Port für beide) wird beim Öffnen des Dialogs automatisch aufgelöst - der
  Mega (Zeitmessung, Pflicht) hat Vorrang, der DMX-Port geht auf "leer"
  (aus). Verhindert das versehentliche zweifache Öffnen desselben
  Arduino. Bleibt trotzdem editierbar (Geraet gerade nicht angesteckt),
  und der jeweils eigene gespeicherte Wert wird nie weggefiltert.

## Datenschutz/Rechtliches

Impressum/Datenschutz-Seiten sind bewusst als **Entwurf mit Platzhaltern**
markiert (App verarbeitet echte Personendaten, teils Minderjährige) — vor
echtem Einsatz durch eine verantwortliche Person / ggf. Rechtsberatung
prüfen lassen, nicht einfach als fertig annehmen.

## Firmware-Doku

**Aktuell eingesetzt:** `firmware/zeitmessung-mega/README.md` (Arduino Mega
2560, seit 2026-08-16) - seriell statt WLAN, siehe oben. Entwicklungs-PC hat
PlatformIO nicht vorinstalliert (`pip install platformio` nötig), der Mega
hängt an COM3.

**Nicht mehr eingesetzt, Code bleibt erhalten:** `firmware/zeitmessung/README.md`
(ESP32, WLAN/HTTP direkt an die Webapp, COM4).

## Desktop-App-Doku

Für die neue Zeitmessung-Desktop-App (liest den Mega seriell aus, puffert
lokal, synct mit der Webapp) immer zuerst `desktop-app/README.md` lesen
(Architektur-Tabelle, Setup, End-to-End-Testnachweis vom 2026-08-16).

**Autostart vorbereitet (2026-08-21):**
`desktop-app/autostart-installieren.sh` richtet auf dem Linux-
Zeitnehmungs-PC einen systemd-Benutzerdienst mit Auto-Restart ein. Die
Installation auf `felferlinuxlab` selbst und der echte Kontakt-/Offline-
End-to-End-Test bleiben Vor-Ort-Schritte; sie sind keine offenen Codepunkte.

**Produktiver Desktop-App-Stand auf `felferlinuxlab` (2026-08-21):**
Zugriff bei nicht erreichbarer LAN-IP per Tailscale unter `100.78.51.89`
(`hans`, dedizierter SSH-Schlüssel `codex_felferlinuxlab`). Installation unter
`/home/hans/zeitmessung-desktop`, manueller GUI-Start über `start.sh` mit
`DISPLAY=:0`; Konfiguration und Messdaten liegen separat unter
`/home/hans/.zeitmessung_desktop` und dürfen bei Updates nicht überschrieben
werden. Der Stand ohne „Gemeinsamer Start“-Button und mit Serverlauf-Vorrang
vor alten Offline-Läufen wurde dorthin kopiert, remote mit **83 bestandenen
Tests** geprüft und vom User im echten Betrieb bestätigt. Vorheriger Stand:
`/home/hans/zeitmessung-desktop-backup-20260821-185020`. Beide Geräte waren
nach dem Neustart geöffnet: Mega `/dev/ttyUSB0`, DMX-Uno `/dev/ttyUSB1`.
Der systemd-Autostart ist weiterhin nur vorbereitet, nicht installiert.

**Buzzer-Sperrzeit (seit 2026-08-21):** Die Desktop-App filtert physische
Mega-`EVENT`s zusätzlich zur kurzen Firmware-Entprellung softwareseitig pro
Bahn. Einstellung `buzzer_sperrzeit_s` im GUI-Feld „Buzzer-Sperrzeit je Bahn
(Sekunden)“, Standard 1 s, Bereich 0–60 s (0 = zusätzliche Sperre aus).
Innerhalb der Sperrzeit wird ein erneutes Ereignis derselben Bahn vor
SQLite-Speicherung, Läufer-Zuordnung, Lichtblitz und Server-Sync verworfen;
andere Bahnen bleiben unabhängig. Manuelle START-/STOPP-Tasten umgehen die
Sperre bewusst. Implementierung: `desktop-app/zeitmessung_desktop/
buzzer_sperre.py` + `seriell_worker.py`; Tests in `test_buzzer_sperre.py`.
Der Stand wurde auf `felferlinuxlab` ausgerollt und dort mit 1 s Default
gestartet; unmittelbar vorher angelegtes Backup:
`/home/hans/zeitmessung-desktop-backup-20260821-190107`.
Der User hat anschließend produktiv **20 Sekunden** eingestellt; dieser Wert
steht in `/home/hans/.zeitmessung_desktop/einstellungen.json` und wurde nach
dem Neustart remote über `laden().buzzer_sperrzeit_s == 20` verifiziert.

**Stabile Arduino-Portzuordnung auf `felferlinuxlab` (2026-08-22):** Mega
und DMX-Uno haben beide CH341 (`1a86:7523`) ohne eindeutige Seriennummer;
`ttyUSB0/1` vertauschen sich je nach Ansteckreihenfolge. Deshalb produktiv
keine `ttyUSB`-Namen verwenden, sondern die physischen `by-path`-Symlinks:
Mega (115200 Baud) =
`/dev/serial/by-path/pci-0000:00:1d.0-usb-0:1.5:1.0-port0`, DMX (9600 Baud) =
`/dev/serial/by-path/pci-0000:04:00.0-usb-0:1:1.0-port0`. Die Geräte müssen
dafür in denselben USB-Buchsen bleiben. Bei Unklarheit einzeln anstecken und
Mega an seiner Ausgabe `READY;mega2560-zeitmessung-1` erkennen. Diese Werte
sind aktuell in `~/.zeitmessung_desktop/einstellungen.json` gesetzt und nach
App-Neustart mit beiden offenen Ports verifiziert.

Für die DMX-Bahnbeleuchtung zusätzlich `DMX_Zeitmessung/README.md`
(Hardware/Verkabelung/Protokoll) sowie den Abschnitt "DMX-Bahnbeleuchtung"
oben.

## PDF-Listen und Wertungen (seit Build 80)

Die vier Wettbewerbs-PDFs (`Gesamtwertung`, `Team Challenge`,
Disziplin-Rangliste und Startliste) verwenden gemeinsam umbrechende
ReportLab-Paragraph-Zellen. Lange Mannschafts-, Wehr-, Orts- und
Sponsorennamen bleiben dadurch innerhalb ihrer Spalten. Ergebnislisten sind
nach Rang sortiert und verwenden bei gleichem Wert Mannschaft/Wehr als
alphabetischen Zweitschlüssel. Die Startliste ist nicht nach der früher als
„Start-Nr.“ bezeichneten Bahn 1-4 gruppiert, sondern sachlich nach der
numerischen Lauf-/Heat-Reihenfolge, innerhalb des Laufs nach Bahn und bei
Gleichstand alphabetisch. Ihre Spalten heißen `Lauf`, `Startzeit`, `Bahn`,
`Mannschaft`, `Wehr / Ort`. Visuell geprüft wurden alle Seiten aller vier
PDF-Arten mit 40 Einträgen und langen realen Namensformen; Regressionstests
liegen in `tests/test_erweiterungen.py`.

## Backup-Server und Failover (seit 2026-08-22)

Der zweite Ubuntu-Server `ffrattenberg` läuft regulär unter `192.168.1.35`
(Tailscale `100.78.100.82`). Er hält den aktuellen FeuerwehrRattenberg-Stack
mit vier App-/PostgreSQL-Instanzen als warmes Backup vor. Ein Cronjob spiegelt
alle vier produktiven Datenbanken alle fünf Minuten ausschließlich lesend vom
aktiven ThinkPad `.34`; das genaue Verfahren, Prüfkommandos, Umschaltung auf
`.34` und Rückkehr sind verbindlich in `deployment/FAILOVER.md` dokumentiert.
Nie beide Server gleichzeitig mit `.34` betreiben. Nextcloud auf Port 81 ist
ein eigener Dienst und nicht Teil dieser automatischen Datenspiegelung.

## Server-Monitoring und Traefik-Metriken (seit 2026-08-22)

Auf dem aktiven ThinkPad `.34` läuft Netdata 1.43.2 als systemd-Dienst
(`enabled`, `active`). Das Dashboard ist aus Sicherheitsgründen nur lokal am
Server auf `http://127.0.0.1:19999/` gebunden und wird dort im Browser
angezeigt. Netdata nimmt Traefik-StatsD-Metriken ausschließlich auf Loopback
und dem internen Traefik-Docker-Gateway an:
`udp/tcp:127.0.0.1:8125` und `udp/tcp:172.18.0.1:8125`; Port 8125 ist weder im
LAN noch öffentlich gebunden.

Traefik sendet alle zehn Sekunden StatsD-Metriken direkt an
`172.18.0.1:8125`, inklusive EntryPoint-, Router- und Service-Labels. Die
aktive Konfiguration liegt unter `~/apps/traefik/docker-compose.yml`, die
Sicherung vor Aktivierung unter
`~/apps/traefik/docker-compose.vor-monitoring-20260822.yml`. Netdata gruppiert
`traefik.*` über `/etc/netdata/statsd.d/traefik.conf`. Im Dashboard erscheinen
die Diagramme unter dem StatsD-/Traefik-Bereich (Requests, Antwortzeiten,
Statuscodes, Bytes und offene Verbindungen). Ein kontrolliertes Traefik-
Recreate unterbricht nur Domainzugriffe kurz; beim Einrichten wurden etwa
1,8 bis 2,5 Sekunden gemessen. Direkte App-Ports und Datenbanken bleiben
dabei aktiv.
