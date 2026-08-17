// Zeitmessung Siloplanen-Race (Arduino Mega 2560): liest 4 Öffner-Kontakte
// (einer pro Bahn) und meldet jede Auslösung als Zeile über USB-Seriell an
// eine lokale Desktop-App - kein WLAN, kein Server-Kontakt vom Gerät selbst.
// Ablauf pro Bahn: Läufer 1 löst den Kontakt beim Loslaufen aus, bei der
// Übergabe löst jeweils der nächste Läufer denselben Kontakt erneut aus,
// der letzte (vierte) Läufer löst ihn zusätzlich noch einmal am Ziel aus -
// macht 5 Auslösungen pro Bahn über den gesamten Lauf. Die Firmware selbst
// kennt keine Läufe/Runden oder Läufer-Zuordnung, das macht die Desktop-App
// bzw. die Webapp anhand der Reihenfolge. Siehe README.md.
//
// Serielles Protokoll (115200 Baud, Zeilenende "\n", reines ASCII):
//   READY;<geraet_id>                  - einmalig direkt nach dem Booten
//   HEARTBEAT;<millis>                 - alle HEARTBEAT_INTERVALL_MS, auch
//                                         ohne Auslösung (Lebenszeichen)
//   EVENT;<bahn>;<millis>               - bei jeder Kontaktauslösung
//   STATE;<millis>;<b1>;<b2>;<b3>;<b4>  - alle STATE_INTERVALL_MS, aktueller
//                                         entprellter Pin-Zustand je Bahn
//                                         (0=bereit/LOW, 1=ausgelöst/HIGH) -
//                                         nur für die Live-Anzeige beim
//                                         Verkabeln/Testen, KEIN Ersatz für
//                                         EVENT (das bleibt die einzige
//                                         Quelle für echte Zeitmessung)
#include <Arduino.h>
#include "config.h"

struct Kontakt {
  uint8_t pin;
  int bahn;
  // Startwert = Ruhezustand des Oeffner-Kontakts (geschlossen = LOW).
  bool stabilHigh = false;
  bool letzterRoh = false;
  unsigned long letzteAenderung = 0;
};

Kontakt kontakte[ANZAHL_BAHNEN];
unsigned long letzterHeartbeat = 0;
unsigned long letzterStatus = 0;

void kontaktePruefen();
void statusSenden();

void setup() {
  Serial.begin(115200);
  delay(200);

  for (int i = 0; i < ANZAHL_BAHNEN; i++) {
    pinMode(PIN_KONTAKT[i], INPUT_PULLUP);
    kontakte[i].pin = PIN_KONTAKT[i];
    kontakte[i].bahn = i + 1;
  }

  Serial.print("READY;");
  Serial.println(GERAETE_ID);
}

void loop() {
  kontaktePruefen();

  unsigned long jetzt = millis();
  if (jetzt - letzterHeartbeat >= HEARTBEAT_INTERVALL_MS) {
    letzterHeartbeat = jetzt;
    Serial.print("HEARTBEAT;");
    Serial.println(jetzt);
  }
  if (jetzt - letzterStatus >= STATE_INTERVALL_MS) {
    letzterStatus = jetzt;
    statusSenden();
  }
}

void statusSenden() {
  Serial.print("STATE;");
  Serial.print(millis());
  for (auto& k : kontakte) {
    Serial.print(";");
    Serial.print(k.stabilHigh ? 1 : 0);
  }
  Serial.println();
}

// ── Kontakte lesen (entprellt, flankengetriggert) ──────────────────────
// Siehe config.h für die Polarität (idle=LOW, Auslösung=Flanke LOW->HIGH).
void kontaktePruefen() {
  unsigned long jetzt = millis();
  for (auto& k : kontakte) {
    bool roh = digitalRead(k.pin) == HIGH;
    if (roh != k.letzterRoh) {
      k.letzterRoh = roh;
      k.letzteAenderung = jetzt;
    }
    if (roh != k.stabilHigh && (jetzt - k.letzteAenderung) >= ENTPRELL_MS) {
      k.stabilHigh = roh;
      if (k.stabilHigh) {   // stabile Flanke auf HIGH = Oeffner-Kontakt ausgelöst
        Serial.print("EVENT;");
        Serial.print(k.bahn);
        Serial.print(";");
        Serial.println(jetzt);
      }
    }
  }
}
