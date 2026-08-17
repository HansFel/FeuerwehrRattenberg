from zeitmessung_desktop.sync_worker import ereignis_zu_nutzlast


def test_ereignis_zu_nutzlast_baut_erwartetes_format():
    zeile = {"bahn": 2, "geraet_millis": 5000, "client_event_id": "xyz"}
    nutzlast = ereignis_zu_nutzlast(zeile, geraet_id="zeitmessung-laptop1")
    assert nutzlast == {
        "geraet_id": "zeitmessung-laptop1",
        "bahn": 2,
        "kontakt": "kontakt",
        "geraet_millis": 5000,
        "geraet_zeit_iso": "",
        "client_event_id": "xyz",
    }
