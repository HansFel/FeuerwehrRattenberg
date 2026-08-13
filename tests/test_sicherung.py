"""Tests für die Datensicherung (SQLite-Backup)."""
import os

import pytest

from app import create_app
from app.models import db, Team, Sicherung
from app import sicherung as dienst


@pytest.fixture
def app(tmp_path):
    dbdatei = tmp_path / "wettbewerb.sqlite"
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{dbdatei}",
        "ADMIN_STARTPASSWORT": "admin",
    })
    app.instance_path = str(tmp_path)      # Sicherungen isoliert im Temp-Ordner
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client):
    return client.post("/anmelden",
                       data={"username": "admin", "passwort": "admin"})


def test_sicherung_nur_admin(client):
    r = client.get("/sicherung/", follow_redirects=True)
    assert "anmelden".encode() in r.data.lower()


def test_sicherung_erstellen_erzeugt_datei(client, app):
    _login(client)
    client.post("/sicherung/erstellen")
    with app.app_context():
        alle = Sicherung.query.all()
        assert len(alle) == 1
        pfad = os.path.join(app.instance_path, "sicherungen", alle[0].dateiname)
        assert os.path.exists(pfad)
        assert alle[0].checksum                       # Prüfsumme gesetzt
        assert alle[0].erstellt_von == "admin"


def test_wiederherstellen_holt_geloeschte_daten_zurueck(app):
    with app.app_context():
        db.session.add(Team(name="Wiederkehr"))
        db.session.commit()

        s = dienst.erstellen(typ="manuell", von="admin")

        # Team löschen …
        db.session.delete(Team.query.filter_by(name="Wiederkehr").first())
        db.session.commit()
        assert Team.query.filter_by(name="Wiederkehr").first() is None

        # … und aus der Sicherung wiederherstellen
        dienst.wiederherstellen(s.id)
        assert Team.query.filter_by(name="Wiederkehr").first() is not None
        # Nach dem Abgleich sind beide Dateien (Original + Vorher-Sicherung)
        # in der Liste sichtbar
        assert Sicherung.query.count() == 2
        import os as _os
        dateien = _os.listdir(_os.path.join(app.instance_path, "sicherungen"))
        assert len([d for d in dateien if d.endswith(".sqlite.gz")]) == 2


def test_wiederherstellen_verweigert_falsches_format(app):
    """Ein .sql.gz (Postgres-Dump) darf auf einer SQLite-Instanz nicht als
    Wiederherstellung akzeptiert werden – klare Fehlermeldung statt Absturz."""
    with app.app_context():
        pfad = os.path.join(app.instance_path, "sicherungen")
        os.makedirs(pfad, exist_ok=True)
        fremd = os.path.join(pfad, "fremd.sql.gz")
        with open(fremd, "wb") as f:
            f.write(b"kein echtes gzip, nur zum Testen der Format-Pruefung")

        s = Sicherung(dateiname="fremd.sql.gz", dateigroesse=10,
                      checksum=dienst._sha256(fremd), typ="upload")
        db.session.add(s)
        db.session.commit()

        with pytest.raises(RuntimeError, match="nicht kompatibel"):
            dienst.wiederherstellen(s.id)


def test_aufbewahrung_begrenzt_anzahl(app):
    with app.app_context():
        for _ in range(3):
            dienst.erstellen(typ="manuell", von="admin")
        assert dienst.aufraeumen(max_sicherungen=2) == 1
        assert Sicherung.query.count() == 2


def test_download_fehlende_datei_zeigt_fehler_statt_500(client, app):
    """Fehlt die physische Datei (z.B. nach einem Container-Neustart ohne
    Volume), darf der Download nicht mit einem Serverfehler abstuerzen."""
    _login(client)
    with app.app_context():
        s = dienst.erstellen(typ="manuell", von="admin")
        pfad = os.path.join(app.instance_path, "sicherungen", s.dateiname)
        os.remove(pfad)
        sid = s.id
    r = client.get(f"/sicherung/{sid}/download", follow_redirects=True)
    assert r.status_code == 200
    assert "fehlt auf dem Server".encode() in r.data


def test_groesse_formatiert():
    s = Sicherung(dateigroesse=2048)
    assert s.groesse_formatiert == "2.0 KB"


def test_dateiname_enthaelt_instanzname(client, app):
    """Sicherungsdateien müssen den Instanznamen tragen, damit man bei vielen
    Sicherungen aus verschiedenen Apps/Instanzen erkennt, wozu sie gehören."""
    _login(client)
    client.post("/sicherung/erstellen")
    with app.app_context():
        s = Sicherung.query.first()
        assert s.dateiname.startswith("ffrattenberg_sicherung_")


def test_upload_behaelt_urspruenglichen_dateinamen(app):
    """Eine hochgeladene Datei (z.B. von einer anderen Instanz heruntergeladen)
    muss unter ihrem ursprünglichen Namen in der Liste erscheinen –
    Umbenennen macht sie sonst unauffindbar."""
    with app.app_context():
        original = dienst.erstellen(typ="manuell", von="admin")
        quelle = os.path.join(app.instance_path, "sicherungen", original.dateiname)

        class _FakeUpload:
            filename = "lokal_sicherung_20260812_073231_857883.sql.gz"
            def save(self, ziel):
                import shutil as _shutil
                _shutil.copyfile(quelle, ziel)

        hochgeladen = dienst.hochladen(_FakeUpload(), von="Felfer")
        assert hochgeladen.dateiname == "lokal_sicherung_20260812_073231_857883.sql.gz"
        assert Sicherung.query.filter_by(
            dateiname="lokal_sicherung_20260812_073231_857883.sql.gz").first() is not None


def test_upload_weicht_bei_namenskonflikt_aus(app):
    with app.app_context():
        original = dienst.erstellen(typ="manuell", von="admin")
        quelle = os.path.join(app.instance_path, "sicherungen", original.dateiname)

        class _FakeUpload:
            filename = "kollision.sql.gz"
            def save(self, ziel):
                import shutil as _shutil
                _shutil.copyfile(quelle, ziel)

        erster = dienst.hochladen(_FakeUpload(), von="admin")
        zweiter = dienst.hochladen(_FakeUpload(), von="admin")
        assert erster.dateiname == "kollision.sql.gz"
        assert zweiter.dateiname != "kollision.sql.gz"   # Konflikt -> Ausweichname
        assert "upload" in zweiter.dateiname


def test_instanzname_aus_umgebungsvariable(tmp_path):
    dbdatei = tmp_path / "wettbewerb.sqlite"
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{dbdatei}",
        "ADMIN_STARTPASSWORT": "admin",
        "INSTANCE_NAME": "Silo Test!",   # unsichere Zeichen müssen bereinigt werden
    })
    app.instance_path = str(tmp_path)
    with app.app_context():
        s = dienst.erstellen(typ="manuell", von="admin")
        assert s.dateiname.startswith("silo-test_sicherung_")
