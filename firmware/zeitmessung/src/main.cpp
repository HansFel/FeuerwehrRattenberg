// Zeitmessung Siloplanen-Race: liest 4 Öffner-Kontakte (einer pro Bahn),
// meldet jede Auslösung roh (Bahn, Zeitstempel) per HTTP an die
// FeuerwehrRattenberg-App. Jeder Läufer löst beim Loslaufen denselben
// Bahn-Kontakt aus, der letzte Läufer zusätzlich am Ziel - die Firmware
// selbst kennt keine Läufe/Runden oder Läufer-Zuordnung, das macht die
// spätere Auswertung anhand der Reihenfolge. Siehe README.md für
// Verkabelung/Einrichtung.
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiManager.h>
#include <WiFiClientSecure.h>
#include <ArduinoOTA.h>
#include <time.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <ESPAsyncWebServer.h>
#include <Preferences.h>

#include "config.h"

Preferences einstellungen;
AsyncWebServer webserver(WEBSERVER_PORT);
WiFiManager wifiManager;

String appUrl;
String apiKey;
String ntpServer;
bool zeitSynchronisiert = false;

struct Kontakt {
  uint8_t pin;
  int bahn;
  const char* typ;
  // Startwert = Ruhezustand des Oeffner-Kontakts (geschlossen = LOW).
  bool stabilHigh = false;
  bool letzterRoh = false;
  unsigned long letzteAenderung = 0;
};

Kontakt kontakte[ANZAHL_BAHNEN];

enum class SendeStatus { WARTEND, GESENDET, FEHLGESCHLAGEN };

struct EreignisEintrag {
  bool belegt = false;
  int bahn = 0;
  const char* typ = "";
  unsigned long geraetMillis = 0;
  String geraetZeitIso;
  SendeStatus status = SendeStatus::WARTEND;
  unsigned long letzterVersuch = 0;
};

EreignisEintrag verlauf[LETZTE_EREIGNISSE_ANZEIGEN];
int verlaufIndex = 0;
// Schuetzt verlauf/verlaufIndex zwischen dem Haupt-Loop (Kontakte lesen,
// schreibt neue Eintraege) und netzwerkTask (sendet/aktualisiert Status auf
// einem eigenen FreeRTOS-Task/Core) - siehe netzwerkTask() weiter unten.
SemaphoreHandle_t verlaufMutex;

constexpr unsigned long WIEDERHOLUNGS_INTERVALL_MS = 3000;

void ladeEinstellungen();
void speichereEinstellungen();
void starteWLAN(bool portalErzwingen);
void starteZeitSynchronisation();
void starteWebserver();
void kontaktePruefen();
void ereignisAufzeichnen(int bahn, const char* typ);
bool ereignisSenden(EreignisEintrag& eintrag);
String aktuelleZeitIso();
String statusJson();
String startseiteHtml();
void serielleBefehleVerarbeiten();
void serielleHilfeAusgeben();
void serielleStatusAusgeben();
void starteOTA();
void netzwerkTask(void* parameter);

void setup() {
  Serial.begin(115200);
  delay(200);

  for (int i = 0; i < ANZAHL_BAHNEN; i++) {
    pinMode(PIN_KONTAKT[i], INPUT_PULLUP);
    kontakte[i] = {PIN_KONTAKT[i], i + 1, "kontakt"};
  }

  verlaufMutex = xSemaphoreCreateMutex();

  ladeEinstellungen();
  bool portalErzwingen = einstellungen.getBool("portal_erzw", false);
  if (portalErzwingen) einstellungen.putBool("portal_erzw", false);
  starteWLAN(portalErzwingen);
  starteZeitSynchronisation();
  starteWebserver();
  starteOTA();

  // Netzwerk-Versand laeuft auf einem eigenen Task/Core, damit ein
  // haengender/langsamer HTTP(S)-Versuch NIE die Kontakterkennung im
  // Haupt-Loop blockiert (Timing-Genauigkeit hat Vorrang).
  xTaskCreatePinnedToCore(netzwerkTask, "netzwerk", 8192, NULL, 1, NULL, 0);

  Serial.println("Bereit. 'hilfe' eingeben fuer Befehlsuebersicht.");
  serielleStatusAusgeben();
}

void loop() {
  kontaktePruefen();
  serielleBefehleVerarbeiten();
  ArduinoOTA.handle();
}

// Laeuft dauerhaft auf einem eigenen Core: sucht Ereignisse, die noch nicht
// (erfolgreich) gesendet wurden, und versucht sie zu senden. Haelt den
// Mutex bewusst NUR waehrend des Kopierens/Zurueckschreibens von verlauf,
// NICHT waehrend des eigentlichen (potenziell langsamen) HTTP-Aufrufs - der
// laeuft auf einer lokalen Kopie, damit ein zeitgleiches Ueberschreiben
// desselben Ringpuffer-Slots durch ereignisAufzeichnen() (Haupt-Loop) nie
// mitten in einem laufenden Sendeversuch passieren kann.
void netzwerkTask(void* parameter) {
  for (;;) {
    unsigned long jetzt = millis();
    for (int i = 0; i < LETZTE_EREIGNISSE_ANZEIGEN; i++) {
      xSemaphoreTake(verlaufMutex, portMAX_DELAY);
      bool sollSenden = verlauf[i].belegt &&
                        verlauf[i].status != SendeStatus::GESENDET &&
                        (jetzt - verlauf[i].letzterVersuch) >= WIEDERHOLUNGS_INTERVALL_MS;
      EreignisEintrag kopie;
      if (sollSenden) {
        kopie = verlauf[i];
        verlauf[i].letzterVersuch = jetzt;   // verhindert sofortiges Doppel-Senden
      }
      xSemaphoreGive(verlaufMutex);

      if (sollSenden) {
        ereignisSenden(kopie);
        xSemaphoreTake(verlaufMutex, portMAX_DELAY);
        verlauf[i].status = kopie.status;
        xSemaphoreGive(verlaufMutex);
      }
    }
    vTaskDelay(pdMS_TO_TICKS(200));
  }
}

// ── Einstellungen (Preferences/NVS) ─────────────────────────────────────
void ladeEinstellungen() {
  einstellungen.begin("zeitmessung", false);
  appUrl = einstellungen.getString("app_url", APP_URL_STANDARD);
  apiKey = einstellungen.getString("api_key", API_KEY_STANDARD);
  ntpServer = einstellungen.getString("ntp_server", NTP_SERVER_STANDARD);
}

void speichereEinstellungen() {
  einstellungen.putString("app_url", appUrl);
  einstellungen.putString("api_key", apiKey);
  einstellungen.putString("ntp_server", ntpServer);
}

// ── WLAN (WiFiManager mit eigenen Feldern für App-URL/API-Key/Zeitserver,
// so lassen sich diese vor Ort über die Captive-Portal-Seite anpassen,
// ohne neu zu flashen) ──────────────────────────────────────────────────
//
// portalErzwingen=true (gesetzt über /wlan-wechseln + Neustart) öffnet das
// Konfigurationsportal auch dann, wenn noch WLAN-Zugangsdaten gespeichert
// sind - im Unterschied zu /wlan-zuruecksetzen werden dabei WEDER die
// bisherigen WLAN-Zugangsdaten NOCH App-URL/API-Key vorher gelöscht. Bricht
// man das Portal ab oder läuft es in den Timeout, bleiben die alten Werte
// als Fallback erhalten (WiFiManager verwirft sie erst bei erfolgreichem
// Abschluss des Portals).
void starteWLAN(bool portalErzwingen) {
  WiFiManagerParameter feldAppUrl(
      "app_url", "App-URL (z.B. http://192.168.1.10:8000/api/zeitmessung/event)",
      appUrl.c_str(), 160);
  WiFiManagerParameter feldApiKey("api_key", "API-Key", apiKey.c_str(), 80);
  WiFiManagerParameter feldNtp("ntp_server", "Zeitserver", ntpServer.c_str(), 80);

  wifiManager.addParameter(&feldAppUrl);
  wifiManager.addParameter(&feldApiKey);
  wifiManager.addParameter(&feldNtp);

  String apName = String("Zeitmessung-") + GERAETE_ID;

  if (portalErzwingen) {
    // Netzwerk-Wechsel: Timeout, damit das Gerät nicht auf unbestimmte Zeit
    // im Konfigurations-AP hängen bleibt, falls niemand das Portal
    // ausfüllt - danach automatischer Versuch mit den alten Zugangsdaten.
    wifiManager.setConfigPortalTimeout(180);
    wifiManager.startConfigPortal(apName.c_str());
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("Netzwerk-Wechsel abgebrochen/Timeout - verbinde erneut mit bisherigem WLAN.");
      WiFi.begin();
    }
  } else {
    // Ersteinrichtung: kein Timeout, der Access Point soll zuverlässig
    // stehen bleiben, bis er eingerichtet wurde, statt nach ein paar
    // Minuten wegzufallen und neu zu starten (verwirrend beim ersten Mal).
    wifiManager.autoConnect(apName.c_str());
  }

  appUrl = feldAppUrl.getValue();
  apiKey = feldApiKey.getValue();
  ntpServer = feldNtp.getValue();
  speichereEinstellungen();

  Serial.printf("WLAN verbunden, IP: %s\n", WiFi.localIP().toString().c_str());
}

// ── Zeitserver ────────────────────────────────────────────────────────────
void starteZeitSynchronisation() {
  configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, ntpServer.c_str());
  struct tm zeitinfo;
  zeitSynchronisiert = getLocalTime(&zeitinfo, 10000);
  if (zeitSynchronisiert) {
    Serial.println("Zeit synchronisiert.");
  } else {
    Serial.println("Zeitserver nicht erreichbar - Geraete-Zeit bleibt leer, "
                    "Auswertung nutzt den Server-Empfangszeitstempel.");
  }
}

String aktuelleZeitIso() {
  if (!zeitSynchronisiert) return "";
  struct tm zeitinfo;
  if (!getLocalTime(&zeitinfo, 0)) return "";
  char puffer[32];
  strftime(puffer, sizeof(puffer), "%Y-%m-%dT%H:%M:%S", &zeitinfo);
  return String(puffer);
}

// ── Kontakte lesen (entprellt, flankengetriggert) ──────────────────────
// Oeffner-Kontakte (Schliesser waere NICHT hier gemeint) am internen
// Pullup: Ruhezustand = Kontakt geschlossen = gegen GND kurzgeschlossen =
// LOW. Ausloesung = Kontakt oeffnet = Pin wird vom Pullup auf HIGH gezogen.
// Ausloesung ist also die Flanke LOW -> HIGH (nicht umgekehrt).
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
        ereignisAufzeichnen(k.bahn, k.typ);
      }
    }
  }
}

void ereignisAufzeichnen(int bahn, const char* typ) {
  // Nur den Ringpuffer-Eintrag schreiben - das eigentliche Senden macht
  // netzwerkTask() auf einem eigenen Core, damit diese Funktion (aufgerufen
  // aus kontaktePruefen() im Haupt-Loop) immer schnell zurückkehrt und die
  // Kontakterkennung nie durch einen langsamen/haengenden HTTP-Aufruf
  // blockiert wird.
  xSemaphoreTake(verlaufMutex, portMAX_DELAY);
  EreignisEintrag& eintrag = verlauf[verlaufIndex];
  eintrag.belegt = true;
  eintrag.bahn = bahn;
  eintrag.typ = typ;
  eintrag.geraetMillis = millis();
  eintrag.geraetZeitIso = aktuelleZeitIso();
  eintrag.status = SendeStatus::WARTEND;
  eintrag.letzterVersuch = 0;
  verlaufIndex = (verlaufIndex + 1) % LETZTE_EREIGNISSE_ANZEIGEN;
  xSemaphoreGive(verlaufMutex);

  Serial.printf("Bahn %d %s ausgeloest\n", bahn, typ);
}

bool ereignisSenden(EreignisEintrag& eintrag) {
  eintrag.letzterVersuch = millis();
  if (WiFi.status() != WL_CONNECTED) {
    eintrag.status = SendeStatus::FEHLGESCHLAGEN;
    return false;
  }

  JsonDocument nutzlast;
  nutzlast["geraet_id"] = GERAETE_ID;
  nutzlast["bahn"] = eintrag.bahn;
  nutzlast["kontakt"] = eintrag.typ;
  nutzlast["geraet_millis"] = eintrag.geraetMillis;
  nutzlast["geraet_zeit_iso"] = eintrag.geraetZeitIso;
  String koerper;
  serializeJson(nutzlast, koerper);

  // HTTPS-Ziele (z.B. der Produktionsserver hinter Traefik/Let's Encrypt)
  // brauchen einen eigenen TLS-Client. setInsecure() verzichtet bewusst auf
  // Zertifikatspruefung - unproblematisch fuer diese interne Zeitmessdaten,
  // vermeidet aber das Einbetten/Pflegen eines Root-Zertifikats auf dem
  // ESP32.
  HTTPClient http;
  bool gestartet;
  WiFiClientSecure tlsClient;
  if (appUrl.startsWith("https://")) {
    tlsClient.setInsecure();
    gestartet = http.begin(tlsClient, appUrl);
  } else {
    gestartet = http.begin(appUrl);
  }
  if (!gestartet) {
    eintrag.status = SendeStatus::FEHLGESCHLAGEN;
    Serial.printf("Senden fehlgeschlagen (Bahn %d %s): http.begin() fehlgeschlagen (App-URL: %s)\n",
                  eintrag.bahn, eintrag.typ, appUrl.c_str());
    return false;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", apiKey);
  // HTTPS-TLS-Handshakes brauchen auf dem ESP32 deutlich laenger als
  // schlichtes HTTP - 2s (frueherer Wert) reichte dafuer oft nicht.
  http.setTimeout(10000);
  int code = http.POST(koerper);
  String fehlertext = (code < 0) ? http.errorToString(code) : "";
  http.end();

  if (code == 200 || code == 201) {
    eintrag.status = SendeStatus::GESENDET;
    return true;
  }
  eintrag.status = SendeStatus::FEHLGESCHLAGEN;
  Serial.printf("Senden fehlgeschlagen (Bahn %d %s): Code %d %s (freier Heap: %u Bytes, "
                "groesster Block: %u Bytes)\n",
                eintrag.bahn, eintrag.typ, code, fehlertext.c_str(),
                ESP.getFreeHeap(), ESP.getMaxAllocHeap());
  return false;
}

// ── Lokaler Webserver (Diagnose vor Ort) ────────────────────────────────
String statusJson() {
  JsonDocument doc;
  doc["geraet_id"] = GERAETE_ID;
  doc["wlan_ip"] = WiFi.localIP().toString();
  doc["wlan_rssi"] = WiFi.RSSI();
  doc["zeit_synchronisiert"] = zeitSynchronisiert;
  doc["aktuelle_zeit"] = aktuelleZeitIso();
  doc["app_url"] = appUrl;
  doc["uptime_s"] = millis() / 1000;

  JsonArray kontaktzustaende = doc["kontaktzustaende"].to<JsonArray>();
  for (auto& k : kontakte) {
    JsonObject o = kontaktzustaende.add<JsonObject>();
    o["bahn"] = k.bahn;
    o["typ"] = k.typ;
    o["ausgeloest"] = k.stabilHigh;   // true = Oeffner-Kontakt gerade ausgeloest
  }

  JsonArray ereignisse = doc["ereignisse"].to<JsonArray>();
  for (int i = 0; i < LETZTE_EREIGNISSE_ANZEIGEN; i++) {
    int idx = (verlaufIndex - 1 - i + LETZTE_EREIGNISSE_ANZEIGEN) % LETZTE_EREIGNISSE_ANZEIGEN;
    auto& e = verlauf[idx];
    if (!e.belegt) continue;
    JsonObject o = ereignisse.add<JsonObject>();
    o["bahn"] = e.bahn;
    o["kontakt"] = e.typ;
    o["geraet_millis"] = e.geraetMillis;
    o["status"] = e.status == SendeStatus::GESENDET ? "gesendet"
                : e.status == SendeStatus::FEHLGESCHLAGEN ? "fehlgeschlagen" : "wartend";
  }

  String ergebnis;
  serializeJson(doc, ergebnis);
  return ergebnis;
}

String startseiteHtml() {
  // Statische Seite, füllt sich per JS aus /status – kein Full-Page-Reload,
  // damit sich die Kontaktzustände flüssig live aktualisieren.
  String html;
  html.reserve(3072);
  html += "<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\">";
  html += "<title>Zeitmessung " + String(GERAETE_ID) + "</title>";
  html += "<style>body{font-family:sans-serif;margin:1.5rem;background:#111;color:#eee}"
          "table{border-collapse:collapse;width:100%;margin-top:.5rem}"
          "td,th{border:1px solid #444;padding:.3rem .6rem;text-align:left}"
          ".ok{color:#7c7}.fehler{color:#e77}.wartend{color:#cc7}"
          ".bereit{color:#7c7}.ausgeloest{color:#fa3;font-weight:bold}"
          "a.knopf{display:inline-block;margin-top:1rem;padding:.4rem .8rem;"
          "background:#a33;color:#fff;text-decoration:none;border-radius:4px}</style></head><body>";
  html += "<h1>Zeitmessung " + String(GERAETE_ID) + "</h1>";
  html += "<p>WLAN: <span id=\"wlan\">-</span></p>";
  html += "<p>Zeit: <span id=\"zeit\">-</span></p>";
  html += "<p>App-Server: <span id=\"appurl\">-</span></p>";
  html += "<p>Laufzeit: <span id=\"uptime\">-</span></p>";
  html += "<h2>Kontaktzustände (live)</h2>";
  html += "<table><thead><tr><th>Bahn</th><th>Kontakt</th><th>Zustand</th></tr></thead>"
          "<tbody id=\"kontakte\"></tbody></table>";
  html += "<h2>Letzte Ereignisse</h2>";
  html += "<table><thead><tr><th>Bahn</th><th>Kontakt</th><th>Geraete-ms</th><th>Status</th></tr></thead>"
          "<tbody id=\"ereignisse\"></tbody></table>";
  html += "<a class=\"knopf\" href=\"/wlan-wechseln\" "
          "onclick=\"return confirm('Konfigurationsportal zum Wechseln des WLAN oeffnen? "
          "App-URL/API-Key bleiben erhalten, das Geraet ist kurz nicht ueber diese Seite erreichbar.');\">"
          "WLAN wechseln</a> ";
  html += "<a class=\"knopf\" href=\"/wlan-zuruecksetzen\" "
          "onclick=\"return confirm('WLAN-Zugangsdaten UND App-URL/API-Key loeschen und neu starten?');\">"
          "Alles zuruecksetzen</a>";
  html += "<script>"
          "async function aktualisieren(){"
          "try{"
          "const r=await fetch('/status');const d=await r.json();"
          "document.getElementById('wlan').textContent=d.wlan_ip+' (RSSI '+d.wlan_rssi+' dBm)';"
          "document.getElementById('zeit').textContent=d.zeit_synchronisiert?d.aktuelle_zeit:'nicht synchronisiert';"
          "document.getElementById('appurl').textContent=d.app_url;"
          "document.getElementById('uptime').textContent=d.uptime_s+' s';"
          "const kt=document.getElementById('kontakte');kt.innerHTML='';"
          "d.kontaktzustaende.forEach(k=>{"
          "const tr=document.createElement('tr');"
          "const zustand=k.ausgeloest?'AUSGELOEST':'bereit';"
          "const klasse=k.ausgeloest?'ausgeloest':'bereit';"
          "tr.innerHTML='<td>'+k.bahn+'</td><td>'+k.typ+'</td><td class=\"'+klasse+'\">'+zustand+'</td>';"
          "kt.appendChild(tr);});"
          "const ev=document.getElementById('ereignisse');ev.innerHTML='';"
          "d.ereignisse.forEach(e=>{"
          "const tr=document.createElement('tr');"
          "const klasse=e.status==='gesendet'?'ok':e.status==='fehlgeschlagen'?'fehler':'wartend';"
          "tr.innerHTML='<td>'+e.bahn+'</td><td>'+e.kontakt+'</td><td>'+e.geraet_millis+'</td>"
          "<td class=\"'+klasse+'\">'+e.status+'</td>';"
          "ev.appendChild(tr);});"
          "}catch(e){}"
          "}"
          "setInterval(aktualisieren,300);aktualisieren();"
          "</script>";
  html += "</body></html>";
  return html;
}

void starteWebserver() {
  webserver.on("/", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "text/html; charset=utf-8", startseiteHtml());
  });
  webserver.on("/status", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "application/json", statusJson());
  });
  webserver.on("/wlan-zuruecksetzen", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "text/html; charset=utf-8",
                 "<html><body>WLAN-Zugangsdaten geloescht, Neustart...</body></html>");
    wifiManager.resetSettings();
    delay(1000);
    ESP.restart();
  });
  webserver.on("/wlan-wechseln", HTTP_GET, [](AsyncWebServerRequest* request) {
    String antwort = String("<html><body>Neustart ins Konfigurationsportal (WLAN \"Zeitmessung-") +
                     GERAETE_ID +
                     "\") - App-URL/API-Key bleiben erhalten. Mit Handy/Laptop mit diesem WLAN "
                     "verbinden, um ein neues Netzwerk zu waehlen. Ohne Eingabe verbindet sich "
                     "das Geraet nach ca. 3 Minuten automatisch wieder mit dem bisherigen "
                     "WLAN.</body></html>";
    request->send(200, "text/html; charset=utf-8", antwort);
    einstellungen.putBool("portal_erzw", true);
    delay(1000);
    ESP.restart();
  });
  webserver.begin();
}

// ── OTA-Updates (Firmware-Update uebers WLAN, kein USB/Boot-Taste mehr
// noetig) ─────────────────────────────────────────────────────────────────
// Passwort ist der aktuelle API-Key (kein zusaetzliches Geheimnis zu
// pflegen) - siehe platformio.ini fuer den Upload-Befehl.
void starteOTA() {
  ArduinoOTA.setHostname(GERAETE_ID);
  ArduinoOTA.setPassword(apiKey.c_str());
  ArduinoOTA.onStart([]() {
    Serial.println("OTA-Update startet...");
  });
  ArduinoOTA.onEnd([]() {
    Serial.println("OTA-Update fertig, Neustart.");
  });
  ArduinoOTA.onProgress([](unsigned int fortschritt, unsigned int gesamt) {
    Serial.printf("OTA: %u%%\r", (fortschritt * 100) / gesamt);
  });
  ArduinoOTA.onError([](ota_error_t fehler) {
    Serial.printf("OTA-Fehler [%u]\n", fehler);
  });
  ArduinoOTA.begin();
  Serial.println("OTA bereit (Passwort = aktueller API-Key).");
}

// ── Serielle Konsole (USB) ───────────────────────────────────────────────
// Einrichtung/Diagnose ohne Handy/Laptop im WLAN: 'pio device monitor'
// (oder ein beliebiges serielles Terminal, 115200 Baud, Zeilenende "\n")
// oeffnen und Befehle eintippen. Siehe README.md fuer die vollstaendige
// Befehlsliste.
void serielleHilfeAusgeben() {
  Serial.println("── Befehle ──────────────────────────────────────────");
  Serial.println("hilfe                    - diese Uebersicht");
  Serial.println("status | ip              - aktueller Status");
  Serial.println("scan                     - WLAN-Netzwerke in der Umgebung auflisten");
  Serial.println("wifi <SSID>|<Passwort>   - mit neuem WLAN verbinden + speichern");
  Serial.println("                           (Trennzeichen ist das Pipe-Zeichen |,");
  Serial.println("                           SSID/Passwort duerfen Leerzeichen enthalten)");
  Serial.println("apiurl <URL>             - App-URL setzen");
  Serial.println("apikey <Schluessel>      - API-Key setzen");
  Serial.println("ntp <Server>             - Zeitserver setzen");
  Serial.println("testsenden               - Test-Ereignis an die App-URL senden (ohne Kontakt)");
  Serial.println("neustart                 - Geraet neu starten");
  Serial.println("────────────────────────────────────────────────────");
}

void serielleStatusAusgeben() {
  Serial.println("── Status ───────────────────────────────────────────");
  Serial.printf("Geraet-ID:   %s\n", GERAETE_ID);
  bool verbunden = WiFi.status() == WL_CONNECTED;
  Serial.printf("WLAN:        %s\n", verbunden ? "verbunden" : "NICHT verbunden");
  if (verbunden) {
    Serial.printf("SSID:        %s\n", WiFi.SSID().c_str());
    Serial.printf("IP-Adresse:  %s\n", WiFi.localIP().toString().c_str());
    Serial.printf("RSSI:        %d dBm\n", WiFi.RSSI());
  }
  Serial.printf("Zeit-Sync:   %s\n", zeitSynchronisiert ? "ja" : "nein");
  Serial.printf("App-URL:     %s\n", appUrl.c_str());
  Serial.printf("NTP-Server:  %s\n", ntpServer.c_str());
  Serial.printf("Laufzeit:    %lu s\n", millis() / 1000);
  Serial.println("────────────────────────────────────────────────────");
}

void serielleBefehleVerarbeiten() {
  if (!Serial.available()) return;
  String zeile = Serial.readStringUntil('\n');
  zeile.trim();
  if (zeile.length() == 0) return;

  int leerzeichen = zeile.indexOf(' ');
  String befehl = (leerzeichen == -1) ? zeile : zeile.substring(0, leerzeichen);
  String rest = (leerzeichen == -1) ? "" : zeile.substring(leerzeichen + 1);
  befehl.toLowerCase();
  rest.trim();

  if (befehl == "hilfe" || befehl == "help") {
    serielleHilfeAusgeben();

  } else if (befehl == "status" || befehl == "ip") {
    serielleStatusAusgeben();

  } else if (befehl == "scan") {
    Serial.println("Suche WLAN-Netzwerke...");
    int anzahl = WiFi.scanNetworks();
    for (int i = 0; i < anzahl; i++) {
      Serial.printf("  %-32s RSSI %4d dBm  Kanal %2d  %s\n",
                    WiFi.SSID(i).c_str(), WiFi.RSSI(i), WiFi.channel(i),
                    WiFi.encryptionType(i) == WIFI_AUTH_OPEN ? "[offen]" : "[verschluesselt]");
    }
    Serial.printf("%d Netzwerk(e) gefunden.\n", anzahl);

  } else if (befehl == "wifi") {
    int trenner = rest.indexOf('|');
    if (trenner == -1) {
      Serial.println("Format: wifi <SSID>|<Passwort>  (Trennzeichen: |)");
    } else {
      String ssid = rest.substring(0, trenner);
      String passwort = rest.substring(trenner + 1);
      Serial.printf("Verbinde mit \"%s\"...\n", ssid.c_str());
      WiFi.disconnect();
      WiFi.begin(ssid.c_str(), passwort.c_str());
      unsigned long start = millis();
      while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
        delay(300);
        Serial.print(".");
      }
      Serial.println();
      if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("Verbunden. IP-Adresse: %s\n", WiFi.localIP().toString().c_str());
      } else {
        Serial.println("Verbindung fehlgeschlagen. Zugangsdaten pruefen und erneut "
                        "versuchen, oder 'neustart' fuer einen neuen Versuch mit den "
                        "zuletzt gespeicherten Zugangsdaten.");
      }
    }

  } else if (befehl == "apiurl") {
    if (rest.length() == 0) {
      Serial.println("Format: apiurl <URL>");
    } else {
      appUrl = rest;
      speichereEinstellungen();
      Serial.printf("App-URL gesetzt: %s\n", appUrl.c_str());
    }

  } else if (befehl == "apikey") {
    if (rest.length() == 0) {
      Serial.println("Format: apikey <Schluessel>");
    } else {
      apiKey = rest;
      speichereEinstellungen();
      Serial.println("API-Key gesetzt.");
    }

  } else if (befehl == "ntp") {
    if (rest.length() == 0) {
      Serial.println("Format: ntp <Server>");
    } else {
      ntpServer = rest;
      speichereEinstellungen();
      starteZeitSynchronisation();
      Serial.printf("NTP-Server gesetzt: %s\n", ntpServer.c_str());
    }

  } else if (befehl == "testsenden") {
    Serial.println("Sende Test-Ereignis...");
    EreignisEintrag test;
    test.belegt = true;
    test.bahn = 0;
    test.typ = "test";
    test.geraetMillis = millis();
    test.geraetZeitIso = aktuelleZeitIso();
    bool ok = ereignisSenden(test);
    Serial.println(ok ? "Test-Ereignis erfolgreich gesendet." : "Test-Ereignis fehlgeschlagen (siehe Fehlermeldung oben).");

  } else if (befehl == "neustart" || befehl == "restart") {
    Serial.println("Neustart...");
    delay(300);
    ESP.restart();

  } else {
    Serial.printf("Unbekannter Befehl \"%s\" - 'hilfe' fuer Uebersicht.\n", befehl.c_str());
  }
}
