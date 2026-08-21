"""Konfiguration der Desktop-App: COM-Port, Webapp-Zugang, Intervalle.

Wird als JSON unter ~/.zeitmessung_desktop/einstellungen.json gespeichert -
funktioniert unverändert auf Windows (Entwicklung/Flashen) und Linux (echter
Zeitnehmungs-PC beim Event)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

KONFIG_ORDNER = Path.home() / ".zeitmessung_desktop"
KONFIG_DATEI = KONFIG_ORDNER / "einstellungen.json"


@dataclass
class Einstellungen:
    com_port: str = ""
    baudrate: int = 115200
    # Zweiter, unabhaengiger serieller Port fuer die Bahnbeleuchtung (DMX
    # ueber Arduino Uno + MAX485, siehe ../DMX_Zeitmessung/README.md und
    # bahnbeleuchtung.py). Leer = Beleuchtung deaktiviert, komplett
    # optional - fehlt der Port, laeuft die Zeitmessung unbeeinflusst.
    dmx_port: str = ""
    # Bewusst die direkte LAN-IP + Port 8000 (kein Traefik/TLS), NICHT die
    # öffentliche Domain: Der TCL-Router unterstützt kein zuverlässiges
    # NAT-Hairpin für alle Clients, und selbst mit dem AdGuard-Split-DNS-
    # Workaround (siehe AGENTS.md, Abschnitt "Netzwerk: Split-DNS") hängt
    # die Domain von korrekter Client-DNS-Konfiguration ab - die direkte IP
    # braucht weder DNS noch TLS und ist damit der robustere Standardweg für
    # Hardware im selben LAN (identisches Muster wie beim ESP32).
    # ACHTUNG: Diese IP ist NICHT stabil (keine DHCP-Reservierung auf dem
    # Server) - vor dem Event per SSH verifizieren, ob sie noch stimmt.
    webapp_url: str = "http://192.168.1.14:8000/api/zeitmessung/event"
    api_key: str = ""
    instance_name: str = "zeitmessung-laptop1"
    sync_intervall_s: int = 15
    backup_intervall_min: int = 5
    backup_ordner: str = str(KONFIG_ORDNER / "sicherungen")
    db_pfad: str = str(KONFIG_ORDNER / "zeitmessung.sqlite")

    def als_dict(self) -> dict:
        return asdict(self)


def laden() -> Einstellungen:
    if not KONFIG_DATEI.exists():
        return Einstellungen()
    try:
        rohdaten = json.loads(KONFIG_DATEI.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Einstellungen()
    gueltige_felder = {f for f in Einstellungen.__dataclass_fields__}
    gefiltert = {k: v for k, v in rohdaten.items() if k in gueltige_felder}
    return Einstellungen(**gefiltert)


def speichern(einstellungen: Einstellungen) -> None:
    KONFIG_ORDNER.mkdir(parents=True, exist_ok=True)
    KONFIG_DATEI.write_text(json.dumps(einstellungen.als_dict(), indent=2, ensure_ascii=False),
                            encoding="utf-8")
