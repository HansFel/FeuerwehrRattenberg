from zeitmessung_desktop.lauf_worker import LaufWorker, aktiver_lauf_url


def test_aktiver_lauf_url_aus_event_url_abgeleitet():
    assert (aktiver_lauf_url("http://192.168.1.14:8000/api/zeitmessung/event")
            == "http://192.168.1.14:8000/notfall/api/aktiv")


def test_aktiver_lauf_url_behaelt_instanz_pfadpraefix():
    """z.B. /test1 - eine reine urljoin()-Lösung würde das Präfix verschlucken."""
    assert (aktiver_lauf_url("https://ffrattenberg.duckdns.org/test1/api/zeitmessung/event")
            == "https://ffrattenberg.duckdns.org/test1/notfall/api/aktiv")


def test_worker_meldet_erfolg_ueber_status_callback(monkeypatch):
    class GefaelschteAntwort:
        status_code = 200
        def json(self): return {"aktiv": False}

    monkeypatch.setattr("zeitmessung_desktop.lauf_worker.requests.get",
                        lambda *a, **kw: GefaelschteAntwort())

    lauf_log, status_log = [], []
    worker = LaufWorker("http://server/api/zeitmessung/event", "key", 999,
                        auf_lauf_aktualisiert=lauf_log.append,
                        auf_status_geaendert=status_log.append)

    worker.start()
    worker._stop_angefordert.wait(0.3)
    worker.stoppen()

    assert {"aktiv": False} in lauf_log
    assert {"erfolgreich": True} in status_log


def test_worker_faengt_unerwarteten_fehler_im_callback_ab(monkeypatch):
    """Ein Bug in der Callback-Verarbeitung (z.B. GUI-Code) darf den Thread
    nicht lautlos sterben lassen - muss ueber den Status-Callback sichtbar
    werden."""
    class GefaelschteAntwort:
        status_code = 200
        def json(self): return {"aktiv": True}

    monkeypatch.setattr("zeitmessung_desktop.lauf_worker.requests.get",
                        lambda *a, **kw: GefaelschteAntwort())

    def kaputter_callback(daten):
        raise ValueError("kaputt")

    status_log = []
    worker = LaufWorker("http://server/api/zeitmessung/event", "key", 999,
                        auf_lauf_aktualisiert=kaputter_callback,
                        auf_status_geaendert=status_log.append)

    worker.start()
    worker._stop_angefordert.wait(0.3)
    worker.stoppen()

    assert any(not s.get("erfolgreich") for s in status_log)
    assert any("unerwartet" in str(s.get("fehler", "")) for s in status_log)
