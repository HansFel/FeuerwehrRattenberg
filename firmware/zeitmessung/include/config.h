#pragma once

// ── Pinbelegung ───────────────────────────────────────────────────────────
// Kontakte gegen GND, normal offen, interner Pullup (idle = HIGH, Auslösung
// = kurzer LOW-Impuls). Bewusst nur Pins gewählt, die INPUT_PULLUP können
// und keine Boot-Strapping-/Flash-Pins sind (GPIO34-39 fallen raus, die
// haben keinen internen Pullup).
// Nur noch EIN Kontakt pro Bahn (kein separater Ziel-Kontakt): jeder
// Läufer löst ihn beim Loslaufen (Übergabe) aus, der letzte Läufer
// zusätzlich noch einmal am Ziel - macht 5 Auslösungen pro Bahn über den
// gesamten Lauf (Läufer 1-4 Start + Läufer 4 Ziel). Die Zuordnung
// "welche Auslösung war was" passiert später in der Auswertung anhand der
// Reihenfolge, nicht mehr über zwei getrennte Pins.
constexpr int ANZAHL_BAHNEN = 4;
constexpr uint8_t PIN_KONTAKT[ANZAHL_BAHNEN] = {32, 33, 25, 26};

// ── Entprellung ───────────────────────────────────────────────────────────
constexpr unsigned long ENTPRELL_MS = 30;

// ── Gerät ─────────────────────────────────────────────────────────────────
// Eindeutige Geräte-ID, falls mehrere ESP32 im Einsatz sind (z.B. je Bahn
// eigenes Gerät statt einem Gerät mit 4 Bahnen) - dann pro Gerät anpassen.
constexpr char GERAETE_ID[] = "esp32-zeitmessung-1";

// ── Zeitserver ────────────────────────────────────────────────────────────
constexpr char NTP_SERVER_STANDARD[] = "pool.ntp.org";
constexpr long GMT_OFFSET_SEC = 3600;        // MEZ
constexpr int DAYLIGHT_OFFSET_SEC = 3600;    // MESZ

// ── App-Server (Vorgabewerte für die WiFiManager-Konfigseite; über die
// Weboberfläche des ESP32 ohne Neuflashen änderbar) ─────────────────────
constexpr char APP_URL_STANDARD[] = "http://192.168.178.78:8000/api/zeitmessung/event";
constexpr char API_KEY_STANDARD[] = "dev-nur-lokal-zeitmessung";

// ── Sende-Warteschlange (Ringpuffer bei WLAN-Aussetzern) ────────────────
constexpr int PUFFER_GROESSE = 40;

// ── Lokaler Webserver ─────────────────────────────────────────────────────
constexpr int WEBSERVER_PORT = 80;
constexpr int LETZTE_EREIGNISSE_ANZEIGEN = 25;
