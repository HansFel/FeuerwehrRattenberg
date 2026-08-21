/*
  DMX_Zeitmessung.ino
  --------------------------------------------------------------------
  4x Eurolite LED PAR-56 RGB EINZELN steuern.
  Arduino Uno (AZ-Delivery / CH340) -> MAX485 -> DMX / PARs

  VERKABELUNG
    MAX485   Arduino        DMX/XLR
    VCC      5V
    GND      GND    ----->  Pin 1
    DI       Pin 3
    DE       5V
    RE       5V
    A                       Pin 3 (Data +)
    B                       Pin 2 (Data -)

  KANALBELEGUNG dieses PARs (5 Kanaele je Geraet):
    1 = Makro/Programm (MUSS 0 sein, sonst Farbwechsel!)
    2 = Rot   3 = Gruen   4 = Blau   5 = Speed/Strobe (0)

  ADRESSIERUNG (5er-Abstand), DIP 10 = ON fuer DMX:
    PAR1 Adr  1  -> DIP 1
    PAR2 Adr  6  -> DIP 2 + 3
    PAR3 Adr 11  -> DIP 1 + 2 + 4
    PAR4 Adr 16  -> DIP 5

  PROTOKOLL (Zeile mit \n), 9600 Baud:
    "<par> <r> <g> <b>"   par: 1..4 einzeln, 0 = alle
       "1 255 0 0"  PAR1 rot     "0 0 0 0"  alle aus
    DEBUG - Rohkanal direkt setzen:
    "c <kanal> <wert>"    z.B. "c 2 255"  setzt DMX-Kanal 2 auf 255
  --------------------------------------------------------------------
*/

#include <DmxSimple.h>

// ===== Konfiguration ================================================
const int DMX_PIN  = 3;
const int NUM_PARS = 4;
int startAddr[NUM_PARS] = {1, 6, 11, 16};

// Kanal-Offsets ab Startadresse (0-basiert):
const int OFF_MACRO = 0;   // Kanal 1 -> immer 0
const int OFF_R     = 1;   // Kanal 2 = Rot
const int OFF_G     = 2;   // Kanal 3 = Gruen
const int OFF_B     = 3;   // Kanal 4 = Blau
const int OFF_SPEED = 4;   // Kanal 5 -> immer 0

const bool SELFTEST = true;
// ====================================================================

char buf[24];
byte idx = 0;

void setPar(int n, int r, int g, int b) {   // n = 1..4
  if (n < 1 || n > NUM_PARS) return;
  int base = startAddr[n - 1];
  DmxSimple.write(base + OFF_MACRO, 0);    // Makro AUS
  DmxSimple.write(base + OFF_R, r);
  DmxSimple.write(base + OFF_G, g);
  DmxSimple.write(base + OFF_B, b);
  DmxSimple.write(base + OFF_SPEED, 0);    // Speed/Strobe AUS
}

void allPars(int r, int g, int b) {
  for (int i = 1; i <= NUM_PARS; i++) setPar(i, r, g, b);
}

void handleLine(char *s) {
  if (s[0] == 'c' || s[0] == 'C') {        // DEBUG: c <kanal> <wert>
    char *t = strtok(s + 1, " "); if (!t) return; int ch = atoi(t);
    t = strtok(NULL, " ");        if (!t) return; int v  = atoi(t);
    DmxSimple.write(ch, v);
    return;
  }
  char *t = strtok(s, " ");  if (!t) return; int p = atoi(t);
  t = strtok(NULL, " ");     if (!t) return; int r = atoi(t);
  t = strtok(NULL, " ");     if (!t) return; int g = atoi(t);
  t = strtok(NULL, " ");     if (!t) return; int b = atoi(t);
  if (p == 0) allPars(r, g, b);
  else        setPar(p, r, g, b);
}

void setup() {
  Serial.begin(9600);
  DmxSimple.usePin(DMX_PIN);
  DmxSimple.maxChannel(64);

  if (SELFTEST) {                          // PAR 1..4 nacheinander rot
    for (int i = 1; i <= NUM_PARS; i++) {
      setPar(i, 255, 0, 0); delay(400);
      setPar(i, 0, 0, 0);
    }
  }
  allPars(0, 0, 0);
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      buf[idx] = 0;
      if (idx > 0) handleLine(buf);
      idx = 0;
    } else if (idx < (int)sizeof(buf) - 1) {
      buf[idx++] = c;
    }
  }
}
