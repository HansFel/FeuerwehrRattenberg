# Zeitmessung Siloplanen-Race (Arduino Mega 2560)

Ersetzt den ESP32 (siehe `../zeitmessung/`) als Zeitmessung-Hardware: liest
dieselben 4 Kontakte (einer pro Bahn), meldet Auslösungen aber **nur über
USB-Seriell** an eine lokale Desktop-App statt per WLAN/HTTP direkt an die
Webapp. Kein WiFi/OTA/NTP - robuster bei Strom-/WLAN-Ausfall am
Veranstaltungsort, die Desktop-App puffert und synchronisiert selbst (siehe
`desktop-app/README.md`).

Ablauf pro Bahn: Läufer 1 löst den Kontakt beim Loslaufen aus, bei der
Übergabe löst jeweils der nächste Läufer denselben Kontakt erneut aus, der
letzte (vierte) Läufer löst ihn zusätzlich noch einmal am Ziel aus - macht 5
Auslösungen pro Bahn über den gesamten Lauf (identisch zum ESP32).

## Verkabelung

**Öffner-Kontakte** (NC/Break-Kontakte) am internen Pullup: Ruhezustand =
Kontakt geschlossen = gegen GND kurzgeschlossen = LOW. Auslösung = Kontakt
öffnet = Pin wird vom internen Pullup auf HIGH gezogen. Auslösung ist die
Flanke LOW → HIGH.

| Bahn | Kontakt-Pin |
|------|-------------|
| 1    | 30          |
| 2    | 24          |
| 3    | 26          |
| 4    | 32          |

Anpassbar in `include/config.h`. **Bahn 1/4 am 2026-08-17 von 22/28 auf
30/32 umgelegt**: Kontakte per Multimeter als elektrisch einwandfrei
verifiziert (Spannung wechselt beim Betätigen zuverlässig), Pins 22/28 haben
den Wechsel aber nicht registriert (Live-Zustand blieb dauerhaft auf
"ausgelöst" hängen, auch bei betätigtem/geschlossenem Kontakt) - Verdacht
auf ein Pin-spezifisches Problem auf diesem konkreten Board. Nach dem
Umstecken auf 30/32 noch nicht erneut mit den echten Kontakten verifiziert
(Stand dieser Doku-Aktualisierung).

## Serielles Protokoll

115200 Baud, Zeilenende `\n`, reines ASCII:

| Zeile | Bedeutung |
|---|---|
| `READY;<geraet_id>` | einmalig direkt nach dem Booten |
| `HEARTBEAT;<millis>` | alle 2s, auch ohne Auslösung (Lebenszeichen für die Desktop-App) |
| `EVENT;<bahn>;<millis>` | bei jeder Kontaktauslösung |

Die Desktop-App bildet `EVENT`-Zeilen auf dasselbe JSON-Format ab, das der
ESP32 an `/api/zeitmessung/event` sendet (`geraet_id`, `bahn`,
`kontakt="kontakt"`, `geraet_millis`). `geraet_zeit_iso` bleibt leer - der
Mega hat keine Echtzeituhr/NTP, die Auswertung nutzt ohnehin den
Server-Empfangszeitstempel (siehe `app/blueprints/zeitmessung.py`).

## Bauen und Flashen (PlatformIO)

```bash
pio run                    # kompilieren
pio run -t upload          # auf COM5 flashen (siehe platformio.ini)
pio device monitor         # Serial-Ausgabe (115200 Baud)
```

`upload_port`/`monitor_port` in `platformio.ini` ggf. anpassen, falls der
Mega an einem anderen COM-Port hängt (Windows vergibt bei USB-Neuerkennung
gelegentlich eine neue Nummer - war zuerst COM3, dann COM5). Aktuellen Port
ermitteln: PowerShell `[System.IO.Ports.SerialPort]::getportnames()`.
Getestet 2026-08-16: kompiliert (RAM 3,4%, Flash 1,3% ausgelastet) und
liefert nach dem Flashen zuverlässig `HEARTBEAT`-Zeilen alle 2s.

## Offene Punkte

- Kontakte real anschließen und `EVENT`-Zeilen end-to-end bis in die
  Desktop-App und die Zeitereignis-Tabelle der Webapp testen (nur
  `HEARTBEAT` bisher auf echter Hardware verifiziert, `EVENT` nur durch
  Code-Review gegen die identische ESP32-Logik).
- Entprellzeit (`ENTPRELL_MS`, aktuell 30 ms) ggf. nach ersten Tests mit der
  echten Mechanik der Kontakte anpassen (gleicher Wert wie beim ESP32).
