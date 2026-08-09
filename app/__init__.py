"""Flask-App-Factory für die Wettbewerbs-Organisation."""
from __future__ import annotations

import os

from flask import Flask

from .models import db
from .wertung import format_zeit


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    db_path = os.path.join(app.instance_path, "wettbewerb.sqlite")
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-nur-lokal"),
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{db_path}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)

    # Jinja-Filter für Zeitanzeige
    app.jinja_env.filters["zeit"] = format_zeit

    from .blueprints import teams, disziplinen, wertung, zeitplan, start
    app.register_blueprint(start.bp)
    app.register_blueprint(teams.bp)
    app.register_blueprint(disziplinen.bp)
    app.register_blueprint(wertung.bp)
    app.register_blueprint(zeitplan.bp)

    with app.app_context():
        db.create_all()

    return app
