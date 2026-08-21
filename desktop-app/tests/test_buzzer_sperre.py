from zeitmessung_desktop.buzzer_sperre import BuzzerSperre


def test_erster_impuls_wird_angenommen():
    assert BuzzerSperre(5).darf_ausloesen(1, 10.0)


def test_erneuter_impuls_innerhalb_sperrzeit_wird_verworfen():
    sperre = BuzzerSperre(5)
    assert sperre.darf_ausloesen(1, 10.0)
    assert not sperre.darf_ausloesen(1, 14.999)


def test_impuls_ab_grenzwert_wird_wieder_angenommen():
    sperre = BuzzerSperre(5)
    assert sperre.darf_ausloesen(1, 10.0)
    assert sperre.darf_ausloesen(1, 15.0)


def test_sperrzeit_gilt_getrennt_pro_bahn():
    sperre = BuzzerSperre(10)
    assert sperre.darf_ausloesen(1, 10.0)
    assert sperre.darf_ausloesen(2, 10.1)
    assert not sperre.darf_ausloesen(1, 10.1)


def test_null_deaktiviert_zusaetzliche_sperre():
    sperre = BuzzerSperre(0)
    assert sperre.darf_ausloesen(1, 10.0)
    assert sperre.darf_ausloesen(1, 10.0)
