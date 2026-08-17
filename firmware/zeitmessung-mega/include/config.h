#pragma once

// ── Pinbelegung ───────────────────────────────────────────────────────────
// Öffner-Kontakte (NC/Break-Kontakte) am internen Pullup: Ruhezustand =
// Kontakt geschlossen = gegen GND kurzgeschlossen = LOW. Auslösung = Kontakt
// öffnet = Pin wird vom internen Pullup auf HIGH gezogen. Auslösung ist die
// Flanke LOW -> HIGH (nicht umgekehrt) - identische Verkabelung/Logik wie
// beim bisherigen ESP32 (siehe ../zeitmessung/README.md), nur andere Pins.
// Bewusst NICHT die UART-Pins (0/1, 14-19) oder SPI/I2C-Pins verwendet.
constexpr int ANZAHL_BAHNEN = 4;
constexpr uint8_t PIN_KONTAKT[ANZAHL_BAHNEN] = {22, 24, 26, 28};

// ── Entprellung ───────────────────────────────────────────────────────────
constexpr unsigned long ENTPRELL_MS = 30;

// ── Gerät ─────────────────────────────────────────────────────────────────
constexpr char GERAETE_ID[] = "mega2560-zeitmessung-1";

// ── Heartbeat (Lebenszeichen, damit die Desktop-App eine hängende/tote
// USB-Verbindung von einer nur gerade untätigen Bahn unterscheiden kann) ──
constexpr unsigned long HEARTBEAT_INTERVALL_MS = 2000;
