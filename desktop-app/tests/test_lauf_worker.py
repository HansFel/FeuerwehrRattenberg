from zeitmessung_desktop.lauf_worker import aktiver_lauf_url


def test_aktiver_lauf_url_aus_event_url_abgeleitet():
    assert (aktiver_lauf_url("http://192.168.1.14:8000/api/zeitmessung/event")
            == "http://192.168.1.14:8000/notfall/api/aktiv")


def test_aktiver_lauf_url_behaelt_instanz_pfadpraefix():
    """z.B. /test1 - eine reine urljoin()-Lösung würde das Präfix verschlucken."""
    assert (aktiver_lauf_url("https://ffrattenberg.duckdns.org/test1/api/zeitmessung/event")
            == "https://ffrattenberg.duckdns.org/test1/notfall/api/aktiv")
