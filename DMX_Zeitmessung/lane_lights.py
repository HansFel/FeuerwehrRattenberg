"""
lane_lights.py
------------------------------------------------------------------
Steuerung der 4 Bahn-PARs (Eurolite LED PAR-56 RGB) ueber den
DMX-Arduino.  Zum Einbinden in die Zeitmess-Software.

Bahn 1..4  ->  PAR 1..4  (Arduino-Adressen 1/6/11/16)

Benoetigt:  pip install pyserial

Einbinden (3 Aufrufe genuegen):
    from lane_lights import LaneLights
    lights = LaneLights("/dev/ttyUSB0")

    lights.set_state("vorbereitung")   # bei Statuswechsel
    lights.set_state("bereit")
    lights.set_state("start")

    lights.buzzer(3)                   # wenn Buzzer Bahn 3 gedrueckt

    lights.close()                     # beim Beenden
------------------------------------------------------------------
"""

import threading
import time

import serial


class LaneLights:
    # ---- Zustandsfarben (R, G, B) -- hier nach Wunsch anpassen -----
    COLORS = {
        "vorbereitung": (255, 80, 0),    # Amber/Orange
        "bereit":       (0, 0, 255),     # Blau
        "start":        (0, 255, 0),     # Gruen
        "aus":          (0, 0, 0),
    }
    FLASH_COLOR = (255, 255, 255)        # Buzzer-Blitz = Weiss
    FLASH_MS    = 350                    # Blitzdauer in Millisekunden
    NUM_LANES   = 4
    # ---------------------------------------------------------------

    def __init__(self, port="/dev/ttyUSB0", baud=9600):
        self.ser = serial.Serial(port, baud, timeout=1)
        time.sleep(2)                    # Arduino bootet nach Auto-Reset
        self._lock = threading.Lock()
        self._flash_timers = {}          # bahn -> threading.Timer
        self.state = "aus"
        self.all_off()

    # ---- intern: ein PAR setzen -----------------------------------
    def _write(self, lane, rgb):
        if not self.ser.is_open:
            return
        r, g, b = rgb
        cmd = f"{lane} {r} {g} {b}\n".encode()
        with self._lock:
            self.ser.write(cmd)

    # ---- Zustand fuer ALLE Bahnen ---------------------------------
    def set_state(self, state):
        if state not in self.COLORS:
            raise ValueError(f"Unbekannter Zustand: {state!r}")
        self.state = state
        rgb = self.COLORS[state]
        for lane in range(1, self.NUM_LANES + 1):
            self._cancel_flash(lane)     # evtl. laufenden Blitz stoppen
            self._write(lane, rgb)

    def all_off(self):
        self.set_state("aus")

    # ---- Buzzer: kurz weiss, dann zurueck zum Zustand -------------
    def buzzer(self, lane):
        """Bahn `lane` kurz weiss aufblitzen lassen (nicht blockierend)."""
        if not 1 <= lane <= self.NUM_LANES:
            return
        self._cancel_flash(lane)
        self._write(lane, self.FLASH_COLOR)
        t = threading.Timer(self.FLASH_MS / 1000.0, self._restore, args=(lane,))
        t.daemon = True
        self._flash_timers[lane] = t
        t.start()

    def _restore(self, lane):
        self._flash_timers.pop(lane, None)
        self._write(lane, self.COLORS[self.state])

    def _cancel_flash(self, lane):
        t = self._flash_timers.pop(lane, None)
        if t is not None:
            t.cancel()

    # ---- aufraeumen -----------------------------------------------
    def close(self):
        for lane in list(self._flash_timers):
            self._cancel_flash(lane)
        self.all_off()
        self.ser.close()


# ===================================================================
# Testkonsole:  python3 lane_lights.py  [port]
# ===================================================================
if __name__ == "__main__":
    import sys

    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    lights = LaneLights(port)

    print(f"""
Verbunden mit {port}. Befehle:
    v        Zustand: Vorbereitung  (Amber)
    b        Zustand: Bereit        (Blau)
    s        Zustand: Start         (Gruen)
    1 2 3 4  Buzzer Bahn 1..4       (weisser Blitz)
    o        alles aus
    q        Ende
""")
    try:
        while True:
            cmd = input("> ").strip().lower()
            if cmd == "q":
                break
            elif cmd == "v":
                lights.set_state("vorbereitung")
            elif cmd == "b":
                lights.set_state("bereit")
            elif cmd == "s":
                lights.set_state("start")
            elif cmd == "o":
                lights.all_off()
            elif cmd in ("1", "2", "3", "4"):
                lights.buzzer(int(cmd))
            else:
                print("  ? unbekannt")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        lights.close()
        print("\nBeendet, Lampen aus.")
