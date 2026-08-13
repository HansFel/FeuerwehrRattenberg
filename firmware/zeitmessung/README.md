# Zeitmessung Siloplanen-Race (ESP32)

Liest 4 Start- und 4 Zielkontakte (je Bahn einer) und meldet jede Auslösung
per HTTP an die FeuerwehrRattenberg-App (`/api/zeitmessung/event`). Die App
ordnet die rohen Ereignisse später dem laufenden Wettkampf-Lauf zu; die
Firmware selbst kennt keine Läufe/Runden.

## Verkabelung

Kontakte gegen GND, normal offen (Ruhezustand = Kontakt offen = HIGH durch
internen Pullup, Auslösung = kurzer Schluss gegen GND = LOW).

| Bahn | Start-Pin (GPIO) | Ziel-Pin (GPIO) |
|------|-------------------|-------------------|
| 1    | 32                | 27                |
| 2    | 33                | 14                |
| 3    | 25                | 13                |
| 4    | 26                | 4                 |

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
   ändert (dazu über die Geräte-Weboberfläche "WLAN zurücksetzen" und das
   Portal erneut durchlaufen).

## Lokale Weboberfläche

Nach dem Verbinden ist der ESP32 unter seiner WLAN-IP erreichbar (im Router
oder Serial-Monitor ablesen):

- `/` – Status (WLAN, Zeit-Sync, App-URL) und die letzten ~25 Kontaktereignisse
  mit Sendestatus (gesendet/wartend/fehlgeschlagen) – zum Testen vor Ort, ob
  die Kontakte sauber auslösen, ohne die Haupt-App zu öffnen
- `/status` – dieselben Daten als JSON
- `/wlan-zuruecksetzen` – löscht die WLAN-Zugangsdaten und startet neu
  (Captive Portal erscheint wieder)

## Bauen und Flashen (PlatformIO)

```bash
pio run                    # kompilieren
pio run -t upload          # auf COM4 flashen (siehe platformio.ini)
pio device monitor         # Serial-Ausgabe (115200 Baud)
```

`upload_port`/`monitor_port` in `platformio.ini` ggf. anpassen, falls der
ESP32 an einem anderen COM-Port hängt.

## Offene Punkte

- Bei mehreren ESP32-Geräten (z.B. eines pro Bahn statt eines für alle 4)
  `GERAETE_ID` in `include/config.h` je Gerät eindeutig setzen.
- Entprellzeit (`ENTPRELL_MS`, aktuell 30 ms) ggf. nach ersten Tests mit der
  echten Mechanik der Kontakte anpassen.
