from zeitmessung_desktop.seriell_protokoll import zeile_parsen


def test_ready_zeile():
    assert zeile_parsen("READY;mega2560-zeitmessung-1") == {
        "typ": "ready", "geraet_id": "mega2560-zeitmessung-1"}


def test_heartbeat_zeile():
    assert zeile_parsen("HEARTBEAT;12345") == {"typ": "heartbeat", "geraet_millis": 12345}


def test_event_zeile():
    assert zeile_parsen("EVENT;3;98765") == {"typ": "event", "bahn": 3, "geraet_millis": 98765}


def test_state_zeile():
    assert zeile_parsen("STATE;5000;0;1;0;0") == {
        "typ": "state", "geraet_millis": 5000, "zustaende": [0, 1, 0, 0]}


def test_state_zeile_mit_ungueltigem_wert_ergibt_none():
    assert zeile_parsen("STATE;5000;0;2;0;0") is None
    assert zeile_parsen("STATE;5000;0;x;0;0") is None


def test_state_zeile_zu_wenige_felder_ergibt_none():
    assert zeile_parsen("STATE;5000;0;1;0") is None


def test_zeile_mit_windows_zeilenende():
    assert zeile_parsen("EVENT;1;1\r\n") == {"typ": "event", "bahn": 1, "geraet_millis": 1}


def test_leere_zeile_ergibt_none():
    assert zeile_parsen("") is None
    assert zeile_parsen("   ") is None


def test_unbekannter_typ_ergibt_none():
    assert zeile_parsen("UNSINN;1;2") is None


def test_event_mit_ungueltiger_bahn_ergibt_none():
    assert zeile_parsen("EVENT;0;100") is None
    assert zeile_parsen("EVENT;5;100") is None


def test_event_mit_nicht_numerischen_werten_ergibt_none():
    assert zeile_parsen("EVENT;x;y") is None


def test_serielles_rauschen_ergibt_none_statt_absturz():
    assert zeile_parsen("\x00\x01garbage;;;") is None
