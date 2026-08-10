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

1. Aktuellen Stand von `C:\dev\FeuerwehrRattenberg` nach `Z:\siloplanenrace\repo`
   kopieren (überschreiben; `instance\`, `.venv\`, `__pycache__` auslassen)
2. Auf dem NAS erneut:
   ```bash
   docker compose up -d --build
   ```

## Datensicherung

Die App hat unter „Sicherung" (nur Administrator) eine eigene, eingebaute
Datensicherung für PostgreSQL (`pg_dump`/`psql`), inklusive Download/Upload
und Wiederherstellung mit Prüfsummen-Check. Zusätzlich sichert das Postgres-
Docker-Volume `db-silo-data` die Rohdaten auf dem NAS.
