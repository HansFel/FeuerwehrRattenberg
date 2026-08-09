# Feuerwehr Rattenberg – Wettbewerb (120 Jahre)

Lokale Web-App zur Organisation des Jubiläums-Wettbewerbs der Feuerwehr
Rattenberg. Verwaltet **Mannschaften**, **Disziplinen/Stationen**,
**Zeiten & Wertung** sowie **Zeitplan/Startlisten**. Läuft komplett lokal
(Flask + SQLite), keine Cloud, mehrere Geräte können im selben WLAN zugreifen.

## Funktionen

- **Mannschaften** anlegen/bearbeiten (Name, Wehr/Ort, Startnummer, Kontakt)
- **Disziplinen** definieren – Zeit- oder Punktewertung, Strafsekunden je Fehlerpunkt
- **Zeitplan** – Startlisten je Disziplin (automatisch aus allen Mannschaften,
  danach Startnummer/-zeit/Heat anpassbar)
- **Wertung** – Ergebnisse erfassen (Zeit + Fehlerpunkte), Einzelrangliste je
  Disziplin und Gesamtwertung nach Rangpunkten

## Einrichtung (Windows / PowerShell)

```powershell
cd C:\dev\FeuerwehrRattenberg
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Starten

```powershell
python run.py
```

Dann im Browser öffnen: <http://127.0.0.1:8000>

Für Zugriff vom Tablet/Handy: im selben WLAN `http://<PC-IP>:8000` öffnen
(IP per `ipconfig` ermitteln, ggf. Windows-Firewall für Python freigeben).

> Hinweis: Port 8000 statt 5000, da 5000 unter Windows häufig von
> Docker Desktop / WSL belegt ist.

## Tests

```powershell
pip install pytest
python -m pytest
```

## Datenablage

Die SQLite-Datenbank liegt unter `instance/wettbewerb.sqlite` und ist per
`.gitignore` ausgenommen. Zum Zurücksetzen einfach diese Datei löschen –
beim nächsten Start wird sie neu angelegt.

## Projektstruktur

```
app/
  __init__.py        App-Factory, DB-Setup
  models.py          Team, Disziplin, Ergebnis, Startplatz
  wertung.py         Ranglisten- und Gesamtwertungs-Logik
  blueprints/        start, teams, disziplinen, wertung, zeitplan
  templates/         Jinja2-Vorlagen
  static/css/        Styling
run.py               Startpunkt
tests/               pytest
```

## Wertungslogik (Kurzfassung)

- **Zeit-Disziplin:** Nettozeit = Rohzeit + Fehlerpunkte × Strafsekunden;
  kleinste Nettozeit gewinnt.
- **Punkte-Disziplin:** höchste Punktzahl gewinnt.
- **Gesamtwertung:** je Disziplin gibt es Rangpunkte = Platzierung
  (1 = beste). Nicht gewertete/DSQ-Teams erhalten (Teilnehmerzahl + 1)
  Punkte. Wenigste Rangpunkte = Gesamtsieger.
```
