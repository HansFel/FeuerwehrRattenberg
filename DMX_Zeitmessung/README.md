# DMX-Bahnbeleuchtung — Integrationsleitfaden

Handoff-Dokument für die Anbindung der Bahn-Beleuchtung an die
Zeitmess-Software. Enthält alles, um `lane_lights.py` in ein
Python-Programm zu integrieren — ohne Hardware-Zugriff.

Stand: funktionsfähig getestet, alle 4 PARs einzeln steuerbar, Farben verifiziert.

---

## 1. Zweck

4 DMX-Scheinwerfer (je einer pro **Bahn 1–4**) signalisieren den
Lauf-Status und quittieren Buzzer-Drücke:

- **Globaler Zustand** (alle 4 Lampen gleiche Farbe):
  - *Lauf in Vorbereitung* → Amber
  - *Lauf bereit* → Blau
  - *Lauf startet / im Gange* → Grün
- **Buzzer pro Bahn**: bei Druck blitzt **nur diese Bahn** kurz **weiß**
  auf und kehrt danach automatisch zur aktuellen Zustandsfarbe zurück.

Farben und Timing sind konfigurierbar (siehe §7).

---

## 2. Systemkette

```
Zeitmess-Software (Python, Linux)
      │  USB-Serial, 9600 Baud, Zeilen mit '\n'
      ▼
Arduino Uno (AZ-Delivery, CH340)  ->  /dev/ttyUSB0
      │  DMX-Signal (Pin 3, DmxSimple-Library)
      ▼
MAX485-Modul (TTL -> RS485)
      │  DMX512 (XLR)
      ▼
4x Eurolite LED PAR-56 RGB   (Bahn 1..4 = PAR 1..4)
```

Die Software spricht **nur mit dem Arduino** über die serielle
Schnittstelle. Der Arduino erzeugt das DMX-Timing selbst.

---

## 3. Hardware & Verkabelung

**Arduino → MAX485 → DMX/XLR:**

| MAX485 | Arduino Uno | DMX / XLR |
|--------|-------------|-----------|
| VCC    | 5V          | –         |
| GND    | GND         | Pin 1 (Masse) |
| DI     | Pin 3       | –         |
| DE     | 5V          | –         |
| RE     | 5V          | –         |
| A      | –           | Pin 3 (Data +) |
| B      | –           | Pin 2 (Data −) |

- DE+RE fest auf 5V = Dauersenden.
- 120 Ω zwischen A und B am Ende der PAR-Kette (bei kurzer Strecke optional).
- Keine Reaktion, aber Selbsttest läuft → A und B tauschen.

---

## 4. DMX-Adressierung (DIP-Schalter an den PARs)

Jeder PAR belegt **5 DMX-Kanäle**, daher 5er-Abstand.
**DIP-Schalter 10 = ON** (DMX-Modus) bei allen. Adresse binär auf 1–9
(DIP1=1, DIP2=2, DIP3=4, DIP4=8, DIP5=16 …), Summe = Startadresse.

| Bahn / PAR | Startadresse | Kanäle | DIP ON |
|------------|--------------|--------|--------|
| 1 | 1  | 1–5   | 1        + 10 |
| 2 | 6  | 6–10  | 2, 3     + 10 |
| 3 | 11 | 11–15 | 1, 2, 4  + 10 |
| 4 | 16 | 16–20 | 5        + 10 |

> Hinweis: Bei diesem PAR-Modell schaltet **DIP 10 = ON** in den
> DMX-Betrieb. Steht es falsch, läuft ein Auto-Farbwechselprogramm.

---

## 5. Kanalbelegung eines PARs (Eurolite LED PAR-56 RGB)

Wichtig: **Kanal 1 ist NICHT Rot**, sondern ein Makro-/Programmkanal.

| Kanal (ab Startadresse) | Funktion | Wert im Betrieb |
|-------------------------|----------|-----------------|
| 1 | Makro / Programm | **immer 0** (sonst Auto-Farbwechsel) |
| 2 | Rot   | 0–255 |
| 3 | Grün  | 0–255 |
| 4 | Blau  | 0–255 |
| 5 | Speed / Strobe | **immer 0** |

Der Arduino-Sketch hält Kanal 1 und 5 automatisch auf 0. Die Software
muss sich darum **nicht** kümmern — sie sendet nur PAR-Nummer + RGB.

---

## 6. Arduino-Sketch & serielles Protokoll

Sketch: `DMX_Zeitmessung.ino` (bereits auf den Arduino geflasht).
Library: **DmxSimple**. Serielle Schnittstelle: **9600 Baud, 8N1**,
jeder Befehl mit **`\n`** abgeschlossen.

### Befehle

| Befehl | Wirkung |
|--------|---------|
| `<par> <r> <g> <b>` | PAR `par` (1–4) auf Farbe RGB. `par=0` = alle PARs. |
| `c <kanal> <wert>`  | DEBUG: DMX-Kanal direkt setzen (nur zur Diagnose). |

`r/g/b` und `wert`: 0–255. `par`: 0–4. `kanal`: 1–512.

### Verifizierte Beispiele

```
1 255 0 0        -> PAR 1 Rot
1 0 255 0        -> PAR 1 Grün
1 0 0 255        -> PAR 1 Blau
1 255 255 255    -> PAR 1 Weiß
1 0 0 0          -> PAR 1 Aus
0 0 255 0        -> ALLE Bahnen Grün
```

Beim Einschalten blitzen die PARs zum Selbsttest kurz nacheinander rot.

---

## 7. Python-Modul `lane_lights.py`

Kapselt das Protokoll. Nicht-blockierend (Buzzer-Blitz läuft über
Hintergrund-Timer), thread-sicher (Lock um serielle Schreibzugriffe).

### Abhängigkeit

```bash
pip install pyserial
```

### API

| Aufruf | Beschreibung |
|--------|--------------|
| `LaneLights(port="/dev/ttyUSB0", baud=9600)` | Öffnet Port, wartet 2 s auf Arduino-Reset. Einmal beim Start erzeugen. |
| `set_state(state)` | Setzt **alle** Bahnen auf die Zustandsfarbe. `state` ∈ `"vorbereitung"`, `"bereit"`, `"start"`, `"aus"`. |
| `buzzer(lane)` | Bahn `lane` (1–4) kurz weiß aufblitzen, dann zurück zum Zustand. Nicht blockierend. |
| `all_off()` | Alle Bahnen aus. |
| `close()` | Timer stoppen, alles aus, Port schließen. Beim Beenden aufrufen. |

### Konfiguration (oben in der Datei)

```python
COLORS = {
    "vorbereitung": (255, 80, 0),   # Amber
    "bereit":       (0, 0, 255),    # Blau
    "start":        (0, 255, 0),    # Grün
    "aus":          (0, 0, 0),
}
FLASH_COLOR = (255, 255, 255)       # Buzzer-Blitz = Weiß
FLASH_MS    = 350                   # Blitzdauer in ms
```

### Testkonsole (ohne die Software)

```bash
python3 lane_lights.py /dev/ttyUSB0
# v/b/s = Zustände, 1..4 = Buzzer, o = aus, q = Ende
```

---

## 8. Aufgabe für das integrierende Modell

Ziel: `lane_lights.py` in die bestehende Python-Zeitmess-Software einhängen.

1. **Import & Instanz** einmalig beim Programmstart:
   ```python
   from lane_lights import LaneLights
   lights = LaneLights("/dev/ttyUSB0")
   ```
2. **Statuswechsel → `set_state`**: An den Stellen, wo die Software
   ihren Lauf-Status ändert, den passenden Zustand setzen:
   ```python
   lights.set_state("vorbereitung")   # Lauf in Vorbereitung
   lights.set_state("bereit")         # Lauf bereit
   lights.set_state("start")          # Lauf startet / im Gange
   ```
   > TODO: Die **echten Statusmeldungen/Events der Software** auf diese
   > drei Zustände mappen. Wenn Status als Enum/String/Code vorliegt,
   > ein Dict `status -> state_name` anlegen und `set_state(mapping[status])`
   > aufrufen.
3. **Buzzer-Druck → `buzzer(lane)`**: An der Stelle, wo die Software
   einen Buzzer-Druck einer Bahn erkennt:
   ```python
   lights.buzzer(bahn_nr)   # bahn_nr ∈ 1..4
   ```
   > Die Buzzer-Erkennung liefert die Software selbst (Teil der
   > Zeitmessung). Das Modul erzeugt keine Buzzer, es reagiert nur.
4. **Beim Beenden** `lights.close()` aufrufen (z. B. in `finally`/Shutdown-Hook).

### Zuordnung Bahn ↔ PAR
Bahn 1 = `lights.buzzer(1)` = PAR an Adresse 1, usw. bis Bahn 4 = Adresse 16.

---

## 9. Betrieb & Stolpersteine

- **Port** `/dev/ttyUSB0` (AZ-Delivery/CH340). Nutzer muss in Gruppe
  `dialout` sein (`sudo usermod -aG dialout $USER`, neu einloggen).
- **Port nur EINMAL öffnen** und offen halten. Beim Öffnen resettet der
  Arduino (~2 s, im Modul per `time.sleep(2)` berücksichtigt).
- **Nur ein Prozess** darf den Port gleichzeitig nutzen — nicht parallel
  Arduino-IDE-Monitor / Testkonsole / Hauptprogramm.
- **Fällt der Port weg** (`ttyUSB0` verschwindet): meist USB-Kabel
  (Datenadern) — anständiges Kabel verwenden.
- **PAR wechselt Farben von allein**: DIP 10 steht falsch → auf ON stellen.
- **Falsche Grundfarbe**: Kanal-Offsets `OFF_R/OFF_G/OFF_B` im Sketch prüfen.

---

## 10. Dateien

| Datei | Zweck |
|-------|-------|
| `DMX_Zeitmessung.ino` | Arduino-Sketch (geflasht). DMX-Ausgabe + serielles Protokoll. |
| `lane_lights.py`      | Python-Modul für die Integration + Testkonsole. |
| `README.md`           | Dieses Dokument. |
