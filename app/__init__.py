"""Flask-App-Factory für die Wettbewerbs-Organisation."""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from urllib.error import URLError

from flask import Flask

from .models import db, Benutzer, BenutzerRolle, ROLLEN
from .version import BUILD_NUMMER, BUILD_ZEIT
from .wertung import format_zeit


class PrefixMiddleware:
    """WSGI-Middleware: setzt SCRIPT_NAME aus dem 'X-Script-Name'-Header.

    Nötig, damit url_for() hinter einem Reverse-Proxy mit Pfad-Prefix
    (z.B. Traefik PathPrefix("/test1")) weiterhin korrekte Links erzeugt.
    Übernommen aus dem MGRSoftware-Deployment-Muster.

    Reagiert bewusst NUR auf den Header pro Anfrage, nicht (mehr) auf einen
    statischen Konfigurationswert: dieselbe Instanz ist zusätzlich direkt im
    lokalen Netz erreichbar (ohne Traefik, siehe "ports:" in den
    docker-compose-Dateien - z.B. wenn die öffentliche Domain durch einen
    Google-Safe-Browsing-Fehlalarm blockiert ist). Ohne Traefik davor fehlt
    der Header, es darf dann KEIN Präfix angewendet werden, sonst zeigen
    alle generierten Links ins Leere.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        prefix = environ.get("HTTP_X_SCRIPT_NAME", "")
        if prefix:
            environ["SCRIPT_NAME"] = prefix
            pfad = environ.get("PATH_INFO", "")
            if pfad.startswith(prefix):
                environ["PATH_INFO"] = pfad[len(prefix):]
        return self.app(environ, start_response)


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    # Reverse-Proxy-Pfad-Präfix (z.B. /test1 hinter Traefik) wird pro
    # Anfrage über den 'X-Script-Name'-Header erkannt (siehe
    # PrefixMiddleware) - IMMER registriert, damit dieselbe Instanz sowohl
    # über Traefik (mit Präfix) als auch direkt im LAN (ohne Präfix)
    # funktioniert.
    app.wsgi_app = PrefixMiddleware(app.wsgi_app)

    # X-Forwarded-Proto/-Host von Traefik vertrauen, damit url_for(_external=True)
    # (z.B. für QR-Code-Links) korrekt "https://" statt "http://" erzeugt.
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    db_path = os.path.join(app.instance_path, "wettbewerb.sqlite")
    # Produktion: PostgreSQL 17 via DATABASE_URL (wie mgr-test1);
    # lokal ohne Variable: SQLite-Datei als Fallback.
    db_url = os.environ.get("DATABASE_URL", f"sqlite:///{db_path}")
    if db_url.startswith("postgres://"):        # alte Schreibweise normalisieren
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-nur-lokal"),
        SQLALCHEMY_DATABASE_URI=db_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        # Startpasswort des Standard-Administrators (nur beim ersten Anlegen).
        ADMIN_STARTPASSWORT=os.environ.get("ADMIN_STARTPASSWORT", "admin"),
        # Instanzname für Sicherungsdateien (mehrere Instanzen dieser App
        # können parallel laufen, z.B. "silo" auf dem NAS) – Konvention aus
        # MGRSoftware übernommen: INSTANCE_NAME > HOSTNAME > Kurzname.
        INSTANCE_NAME=(os.environ.get("INSTANCE_NAME")
                      or os.environ.get("HOSTNAME") or "ffrattenberg"),
        # Gemeinsames Geheimnis für die ESP32-Zeitmessgeräte (Header
        # 'X-API-Key'). Unbedingt in der Produktion per Umgebungsvariable
        # überschreiben.
        ZEITMESSUNG_API_KEY=os.environ.get(
            "ZEITMESSUNG_API_KEY", "dev-nur-lokal-zeitmessung"),
        # Falls gesetzt: diese Instanz meldet sich selbst als Weiterleitungs-
        # Ziel bei einer anderen (produktiven) Instanz an, um dieselben
        # ESP32-Zeitmessung-Ereignisse live mitzubekommen (z.B. test1/test2/
        # generalprobe bei der Produktion). Siehe _bei_quelle_anmelden()
        # unten sowie app/blueprints/zeitmessung.py:abonnieren().
        ZEITMESSUNG_QUELLE_URL=os.environ.get("ZEITMESSUNG_QUELLE_URL", ""),
        ZEITMESSUNG_QUELLE_API_KEY=os.environ.get("ZEITMESSUNG_QUELLE_API_KEY", ""),
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)

    # flask-login initialisieren
    from .auth import (login_manager, ist_angemeldet, darf, aktive_rolle,
                       dashboard_zeigt)
    login_manager.init_app(app)

    # Jinja-Filter/-Globals
    app.jinja_env.filters["zeit"] = format_zeit
    app.jinja_env.globals["ist_angemeldet"] = ist_angemeldet
    app.jinja_env.globals["darf"] = darf
    app.jinja_env.globals["aktive_rolle"] = aktive_rolle
    app.jinja_env.globals["dashboard_zeigt"] = dashboard_zeigt
    app.jinja_env.globals["ROLLEN"] = ROLLEN
    app.jinja_env.globals["BUILD_NUMMER"] = BUILD_NUMMER
    app.jinja_env.globals["BUILD_ZEIT"] = BUILD_ZEIT
    app.jinja_env.globals["INSTANZ_NAME"] = app.config["INSTANCE_NAME"]

    from datetime import date
    app.jinja_env.globals["heutiges_jahr"] = lambda: date.today().year

    from .blueprints import (teams, disziplinen, wertung, zeitplan, start,
                             auth, export, pdf, benutzer, sicherung,
                             anforderungen, nachrichten, speisekarte, bestellung,
                             zeitmessung, notfall, moderator, strafen, besucher)

    from flask_login import current_user as _current_user

    def _ungelesene_nachrichten():
        if not _current_user.is_authenticated:
            return []
        return nachrichten.fuer_benutzer(_current_user, nur_ungelesen=True)

    app.jinja_env.globals["ungelesene_nachrichten"] = _ungelesene_nachrichten
    app.jinja_env.globals["nachrichten_fuer_benutzer"] = nachrichten.fuer_benutzer
    app.register_blueprint(start.bp)
    app.register_blueprint(teams.bp)
    app.register_blueprint(disziplinen.bp)
    app.register_blueprint(wertung.bp)
    app.register_blueprint(zeitplan.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(export.bp)
    app.register_blueprint(pdf.bp)
    app.register_blueprint(benutzer.bp)
    app.register_blueprint(sicherung.bp)
    app.register_blueprint(anforderungen.bp)
    app.register_blueprint(nachrichten.bp)
    app.register_blueprint(speisekarte.bp)
    app.register_blueprint(bestellung.bp)
    app.register_blueprint(zeitmessung.bp)
    app.register_blueprint(notfall.bp)
    app.register_blueprint(moderator.bp)
    app.register_blueprint(strafen.bp)
    app.register_blueprint(besucher.bp)

    with app.app_context():
        db.create_all()
        _schema_migrieren()
        _standard_admin_anlegen(app)

    _bei_quelle_anmelden(app)

    return app


def _bei_quelle_anmelden(app: Flask) -> None:
    """Meldet diese Instanz bei ZEITMESSUNG_QUELLE_URL als Weiterleitungs-
    Ziel für ESP32-Zeitmessung-Ereignisse an (falls konfiguriert) und
    erneuert die Anmeldung periodisch in einem Hintergrund-Thread.

    Erneuerung statt einmaliger Anmeldung, damit sich das System von selbst
    heilt, egal ob diese Instanz oder die Quelle neu startet - kein
    manuelles Aufräumen von Alteinträgen auf der Quelle nötig (siehe
    ABONNEMENT_GUELTIGKEIT_S in zeitmessung.py).
    """
    quelle_url = app.config["ZEITMESSUNG_QUELLE_URL"]
    if not quelle_url:
        return
    eigene_ziel_url = f"http://app-{app.config['INSTANCE_NAME']}:8000/api/zeitmessung/event"
    nutzlast = json.dumps({
        "ziel_url": eigene_ziel_url,
        "api_key": app.config["ZEITMESSUNG_API_KEY"],
    }).encode("utf-8")
    quelle_api_key = app.config["ZEITMESSUNG_QUELLE_API_KEY"]

    def schleife() -> None:
        while True:
            try:
                anfrage = urllib.request.Request(
                    quelle_url, data=nutzlast, method="POST",
                    headers={"Content-Type": "application/json",
                             "X-API-Key": quelle_api_key})
                urllib.request.urlopen(anfrage, timeout=5)
            except (URLError, OSError, ValueError) as exc:
                app.logger.warning(
                    "Zeitmessung-Abonnement bei %s fehlgeschlagen: %s", quelle_url, exc)
            time.sleep(60)

    threading.Thread(target=schleife, daemon=True).start()


def _spalten_ergaenzen(tabelle: str, neue_spalten: dict[str, str]) -> None:
    """Ergänzt fehlende Spalten einer bereits bestehenden Tabelle.

    Funktioniert für PostgreSQL und SQLite. Nötig, weil ``db.create_all()``
    bei einer NEUEN Tabelle zwar automatisch alle Spalten anlegt, bei einer
    bereits VORHANDENEN Tabelle aber keine fehlenden Spalten nachträgt (z.B.
    nach einem Code-Update, das neue Modellfelder zu einem bestehenden
    Modell hinzufügt).
    """
    from sqlalchemy import inspect, text
    inspektor = inspect(db.engine)
    if not inspektor.has_table(tabelle):
        return   # Tabelle existiert noch gar nicht -> create_all() erledigt das
    vorhandene = {spalte["name"] for spalte in inspektor.get_columns(tabelle)}
    for spalte, typ in neue_spalten.items():
        if spalte not in vorhandene:
            db.session.execute(
                text(f'ALTER TABLE {tabelle} ADD COLUMN "{spalte}" {typ}'))
    db.session.commit()


def _schema_migrieren() -> None:
    """Additive Migrationen für Modellfelder, die zu bereits bestehenden
    Tabellen hinzugefügt wurden (siehe ``_spalten_ergaenzen``)."""
    gleitkomma = "DOUBLE PRECISION" if db.engine.dialect.name == "postgresql" else "REAL"
    _spalten_ergaenzen("mitglied", {
        "vorname": "TEXT", "nachname": "TEXT", "spitzname": "TEXT",
        "telefon": "TEXT", "alter": "INTEGER",
        "haftungsausschluss": "BOOLEAN NOT NULL DEFAULT FALSE",
        "ausweis_kontrolliert": "BOOLEAN NOT NULL DEFAULT FALSE",
        "einverstaendniserklaerung": "BOOLEAN NOT NULL DEFAULT FALSE",
    })
    _spalten_ergaenzen("team", {
        "getraenk": "TEXT",
        "bezahlt": "BOOLEAN NOT NULL DEFAULT FALSE",
        "haftungsausschluss": "BOOLEAN NOT NULL DEFAULT FALSE",
        "motto": "TEXT",
        "lieblingslied": "TEXT",
        "fanpunkte": "INTEGER NOT NULL DEFAULT 0",
    })
    _spalten_ergaenzen("artikel", {
        "pfand_pro_einheit": f"{gleitkomma} NOT NULL DEFAULT 0.0",
    })
    _spalten_ergaenzen("startplatz", {
        "ergebnis_sekunden": gleitkomma,
        "platz_override": "INTEGER",
    })
    _spalten_ergaenzen("bestellposition", {
        "pfand_pro_einheit": f"{gleitkomma} NOT NULL DEFAULT 0.0",
        "pfand_zurueckgegeben": "INTEGER NOT NULL DEFAULT 0",
    })
    _spalten_ergaenzen("notfall_lauf", {
        "aktiv": "BOOLEAN NOT NULL DEFAULT FALSE",
        "aktiviert_um": "TIMESTAMP",
    })
    _spalten_ergaenzen("zeitereignis", {
        "client_event_id": "VARCHAR(64)",
    })
    _spalten_ergaenzen("disziplin", {
        "dauer_pro_lauf_min": f"{gleitkomma} NOT NULL DEFAULT 7.0",
        "startzeit_erster_lauf": "VARCHAR(20)",
    })
    _spalten_ergaenzen("notfall_bahn", {
        "startplatz_id": "INTEGER",
        "einzelzeit_ausschluss_mask": "INTEGER NOT NULL DEFAULT 0",
    })


def _standard_admin_anlegen(app: Flask) -> None:
    """Legt beim ersten Start einen Administrator an, falls keiner existiert."""
    if Benutzer.query.count() > 0:
        return
    admin = Benutzer(username="admin", name="Administrator", aktiv=True)
    admin.set_password(app.config["ADMIN_STARTPASSWORT"])
    admin.rollen.append(BenutzerRolle(rolle="administrator"))
    db.session.add(admin)
    db.session.commit()
    app.logger.warning(
        "Standard-Administrator 'admin' angelegt – Startpasswort '%s'. "
        "Bitte nach dem ersten Login unter Benutzer ändern.",
        app.config["ADMIN_STARTPASSWORT"])
