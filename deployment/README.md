# Deployment auf dem eigenen Server "ffrattenberg" (Ubuntu, Traefik, eigene Domain)

Produktiv-Instanz ab August 2026: eigener Ubuntu-Server (Hostname/SSH-Alias
`ffrattenberg`, siehe `~/.ssh/config` am Windows-PC), eigener Traefik, eigene
DuckDNS-Domain **ffrattenberg.duckdns.org** (kein Pfad-Präfix, im Unterschied
zum NAS-Deployment – die App läuft hier direkt unter der Domain-Wurzel).

Repo liegt auf GitHub (`HansFel/FeuerwehrRattenberg`, privat) und wird auf
dem Server nach `~/apps/FeuerwehrRattenberg` geklont (Read-only-Deploy-Key,
kein Passwort/Token nötig). Updates ausrollen: auf dem Server `git pull`,
Build-Tag in `deployment/.env` erhöhen, `docker compose -f
deployment/docker-compose.ffrattenberg.yml up -d --build`.

Secrets liegen ausschließlich in `deployment/.env` auf dem Server (nicht in
Git, siehe `.gitignore`). Traefik-Stack (mit DuckDNS-DNS-01-Certresolver
`duckdns`) läuft separat unter `~/apps/traefik` und wird von mehreren Apps
auf diesem Server gemeinsam genutzt (externes Docker-Netzwerk `traefik`).

Ein systemd-Timer auf dem Server aktualisiert die DuckDNS-IP periodisch
(nötig, da der Server ggf. die Netzwerk-/Provider-Umgebung wechselt).

Die Hilfsskripte `duckdns-update.sh` und `duckdns-jetzt.sh` erwarten den
Geheimwert ausschließlich in der Prozessumgebung `DUCKDNS_TOKEN`. Der Token
darf weder in die Skripte noch in Git oder Protokolldateien geschrieben
werden. Die Cron-/systemd-Konfiguration des jeweiligen Rechners muss die
Variable über dessen geschützte Secret-Verwaltung bereitstellen.

---

# Deployment auf dem NAS (UGOS / Docker, hinter Traefik)

Diese App wird genau nach dem Muster der bestehenden Instanzen auf diesem NAS
deployt (siehe z.B. `mgr-test1`, `felfer`): eigene Postgres-Datenbank, eigenes
internes Docker-Netzwerk, Beitritt zum bereits laufenden externen
`traefik`-Netzwerk. **Traefik selbst, die DuckDNS-Domain
(`mgrattenberg.duckdns.org`) und die Portfreigabe am Router sind bereits
eingerichtet und laufen** – für diese App ist nichts davon neu zu machen. Es
werden hier nur die Labels ergänzt, die den Container bei Traefik "anmelden"
(Router-Regel, HTTPS-Zertifikat, Ziel-Port).

Erreichbar danach unter: **https://mgrattenberg.duckdns.org/silo**

## Auf dem NAS liegender Ordner

```
Z:\siloplanenrace\
  .env                  ← echte Zufallswerte (NICHT im Git-Repo)
  docker-compose.yml     ← Kopie von deployment/docker-compose.yml
  repo\                  ← Kopie des App-Quellcodes (app/, run.py, requirements.txt, deployment/)
```

Der Build-Context in `docker-compose.yml` zeigt auf den **NAS-seitigen**
Pfad `/volume1/docker/instanzen/siloplanenrace/repo` (das ist `Z:\siloplanenrace\repo`
vom Windows-PC aus gesehen).

## Erststart

Auf dem NAS (Container-Manager-Konsole / SSH im Ordner `siloplanenrace`):

```bash
docker compose up -d --build
```

Das legt an:
- `db-silo` – PostgreSQL 17 mit eigener Datenbank `wettbewerb`
- `app-silo` – die Flask-App, wartet beim Start auf die Datenbank und legt
  Tabellen sowie den Standard-Administrator `admin` automatisch an
  (Passwort = `ADMIN_STARTPASSWORT` aus der `.env`)

## Nach dem Erststart

1. **https://mgrattenberg.duckdns.org/silo** öffnen
2. Mit `admin` / dem in `.env` hinterlegten `ADMIN_STARTPASSWORT` anmelden
3. Unter „Benutzer" das Admin-Passwort ändern und die echte
   Organisator-Mannschaft mit Rollen anlegen

## Wenn sich der App-Code ändert (Update ausrollen)

**Wichtig:** `docker compose up` (auch ohne `--build`, z.B. per Klick in
UGOS) baut das Image **nicht neu**, wenn bereits ein Image mit dem
angegebenen Tag existiert – das gilt unabhängig davon, was sich im
Quellcode geändert hat. Deshalb trägt der Image-Tag in
`Z:\siloplanenrace\docker-compose.yml` die Build-Nummer, z.B.
`siloplanenrace:build5` (passend zu `BUILD_NUMMER` in `app/version.py`).

Beim Ausrollen eines neuen Stands:

1. Aktuellen Stand von `C:\dev\FeuerwehrRattenberg` nach `Z:\siloplanenrace\repo`
   kopieren (überschreiben; `instance\`, `.venv\`, `__pycache__` auslassen)
2. In `Z:\siloplanenrace\docker-compose.yml` den Image-Tag
   (`image: siloplanenrace:buildN`) auf die neue `BUILD_NUMMER` erhöhen
3. Auf dem NAS wie gewohnt deployen (egal ob per `docker compose up -d`
   oder per UGOS-Klick) – da der Tag neu ist, **muss** ein echter Rebuild
   passieren, ein Löschen des alten Images ist nicht mehr nötig
4. Nach dem Deploy im Footer der Seite prüfen: zeigt es die erwartete
   „Build N (Zeitpunkt)"? Wenn ja, ist der neue Stand live.

Alte `siloplanenrace:buildN`-Images (mit niedrigerer Nummer) können jederzeit
gefahrlos manuell gelöscht werden, um Speicherplatz freizugeben.

## Datensicherung

Die App hat unter „Sicherung" (nur Administrator) eine eigene, eingebaute
Datensicherung für PostgreSQL (`pg_dump`/`psql`), inklusive Download/Upload
und Wiederherstellung mit Prüfsummen-Check. Zusätzlich sichert das Postgres-
Docker-Volume `db-silo-data` die Rohdaten auf dem NAS.
