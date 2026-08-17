#pragma once

// ── Pinbelegung ───────────────────────────────────────────────────────────
// Öffner-Kontakte (NC/Break-Kontakte) am internen Pullup: Ruhezustand =
// Kontakt geschlossen = gegen GND kurzgeschlossen = LOW. Auslösung = Kontakt
// öffnet = Pin wird vom internen Pullup auf HIGH gezogen. Auslösung ist die
// Flanke LOW -> HIGH (nicht umgekehrt) - identische Verkabelung/Logik wie
// beim bisherigen ESP32 (siehe ../zeitmessung/README.md), nur andere Pins.
// Bewusst NICHT die UART-Pins (0/1, 14-19) oder SPI/I2C-Pins verwendet.
constexpr int ANZAHL_BAHNEN = 4;
// Bahn 1 (war Pin 22) und Bahn 4 (war Pin 28) am 2026-08-17 auf 30/32
// umgelegt: Kontakte selbst per Multimeter als elektrisch einwandfrei
// verifiziert (Spannung wechselt zuverlässig), Pins 22/28 haben den Wechsel
// aber nicht registriert - Verdacht auf Pin-spezifisches Problem auf diesem
// Board. Kabel von Bahn 1/4 müssen physisch auf 30/32 umgesteckt werden.
constexpr uint8_t PIN_KONTAKT[ANZAHL_BAHNEN] = {30, 24, 26, 32};

// ── Entprellung ───────────────────────────────────────────────────────────
constexpr unsigned long ENTPRELL_MS = 30;

// ── Gerät ─────────────────────────────────────────────────────────────────
constexpr char GERAETE_ID[] = "mega2560-zeitmessung-1";

// ── Heartbeat (Lebenszeichen, damit die Desktop-App eine hängende/tote
// USB-Verbindung von einer nur gerade untätigen Bahn unterscheiden kann) ──
constexpr unsigned long HEARTBEAT_INTERVALL_MS = 2000;

// ── Live-Zustand (für die Desktop-App-Anzeige beim Verkabeln/Testen, damit
// man sofort sieht ob ein Pin überhaupt reagiert, statt auf eine vollständig
// entprellte Flanke warten zu müssen) - deutlich häufiger als HEARTBEAT. ──
constexpr unsigned long STATE_INTERVALL_MS = 200;
