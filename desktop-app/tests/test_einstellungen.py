from zeitmessung_desktop import einstellungen as einstellungen_modul


def test_laden_ohne_datei_liefert_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(einstellungen_modul, "KONFIG_DATEI", tmp_path / "fehlt.json")
    e = einstellungen_modul.laden()
    assert e.baudrate == 115200
    assert e.sync_intervall_s == 15


def test_speichern_und_laden_rundtrip(tmp_path, monkeypatch):
    konfig_datei = tmp_path / "einstellungen.json"
    monkeypatch.setattr(einstellungen_modul, "KONFIG_ORDNER", tmp_path)
    monkeypatch.setattr(einstellungen_modul, "KONFIG_DATEI", konfig_datei)

    e = einstellungen_modul.Einstellungen(com_port="COM7", api_key="geheim")
    einstellungen_modul.speichern(e)

    geladen = einstellungen_modul.laden()
    assert geladen.com_port == "COM7"
    assert geladen.api_key == "geheim"


def test_laden_ignoriert_unbekannte_felder(tmp_path, monkeypatch):
    konfig_datei = tmp_path / "einstellungen.json"
    konfig_datei.write_text('{"com_port": "COM9", "veraltetes_feld": 1}', encoding="utf-8")
    monkeypatch.setattr(einstellungen_modul, "KONFIG_DATEI", konfig_datei)

    geladen = einstellungen_modul.laden()
    assert geladen.com_port == "COM9"
