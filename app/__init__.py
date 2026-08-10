"""Flask-App-Factory für die Wettbewerbs-Organisation."""
from __future__ import annotations

import os

from flask import Flask

from .models import db, Benutzer, BenutzerRolle, ROLLEN
from .wertung import format_zeit


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)

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

    from .blueprints import (teams, disziplinen, wertung, zeitplan, start,
                             auth, export, pdf, benutzer, sicherung)
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

    with app.app_context():
        db.create_all()
        _standard_admin_anlegen(app)

    return app


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
