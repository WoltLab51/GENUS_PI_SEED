"""Der Werkzeugbauer (genus.werkzeug): Prüfen -> Verdrahten -> Registriert. Die Pflicht-
Entscheidung wortlautfest kann strukturell nicht vergessen werden (Ronnys Form-Frage +
docs/GENUS_AUDIT_2026_07.md, ausgelöst durch die reale Stimme-Gating-Lücke)."""
import pytest

from genus import companion, mathematik, werkzeug, werkzeuge_seed

# Registry-Isolation läuft über die autouse-Fixture in conftest.py (_isolate_werkzeug_registry)


def _leeres_werkzeug(**overrides) -> werkzeug.Werkzeug:
    basis = dict(
        name="testwerkzeug",
        beschreibung="Ein Werkzeug nur für Tests.",
        parameter={"term": werkzeug.Parameter("Text", pflicht=True)},
        schreibt=False,
        wortlautfest=True,
        pruefbar_als="sympy",
        implementierung=lambda term: {"ok": True, "term": term},
    )
    basis.update(overrides)
    return werkzeug.Werkzeug(**basis)


def test_wortlautfest_has_no_default_it_must_be_decided():
    # die strukturelle Antwort auf den echten Bug: eine Spec lässt sich gar nicht erst
    # konstruieren, ohne diese Entscheidung explizit zu treffen
    with pytest.raises(TypeError):
        werkzeug.Werkzeug(
            name="x", beschreibung="x", parameter={}, schreibt=False,
            pruefbar_als="sympy", implementierung=lambda: {"ok": True},
        )


def test_pruefen_accepts_a_well_formed_werkzeug():
    assert werkzeug.pruefen(_leeres_werkzeug()) == []


def test_pruefen_rejects_a_spec_that_promises_a_parameter_the_implementation_does_not_take():
    w = _leeres_werkzeug(parameter={
        "term": werkzeug.Parameter("Text", pflicht=True),
        "nichtvorhanden": werkzeug.Parameter("Text"),
    })
    fehler = werkzeug.pruefen(w)
    assert any("nichtvorhanden" in f for f in fehler)


def test_pruefen_rejects_missing_beschreibung():
    w = _leeres_werkzeug(beschreibung="")
    assert any("Beschreibung" in f for f in werkzeug.pruefen(w))


def test_pruefen_rejects_missing_pruefbar_als():
    w = _leeres_werkzeug(pruefbar_als="")
    assert any("pruefbar_als" in f for f in werkzeug.pruefen(w))


def test_pruefen_rejects_a_non_callable_implementierung():
    w = _leeres_werkzeug(implementierung="nicht aufrufbar")
    assert any("implementierung" in f for f in werkzeug.pruefen(w))


def test_verdrahten_refuses_a_broken_contract_never_registers_it():
    w = _leeres_werkzeug(beschreibung="")
    with pytest.raises(ValueError):
        werkzeug.verdrahten(w)
    assert werkzeug.registriert("testwerkzeug") is None


def test_verdrahten_then_registriert_roundtrips():
    werkzeug.verdrahten(_leeres_werkzeug())
    gefunden = werkzeug.registriert("testwerkzeug")
    assert gefunden is not None and gefunden.name == "testwerkzeug"


def test_verdrahten_is_idempotent_replaces_by_name():
    werkzeug.verdrahten(_leeres_werkzeug(beschreibung="Erste Version"))
    werkzeug.verdrahten(_leeres_werkzeug(beschreibung="Zweite Version"))
    assert werkzeug.registriert("testwerkzeug").beschreibung == "Zweite Version"


def test_stimme_geeignet_follows_structurally_from_wortlautfest():
    werkzeug.verdrahten(_leeres_werkzeug(wortlautfest=True))
    assert werkzeug.stimme_geeignet("testwerkzeug") is False
    werkzeug.verdrahten(_leeres_werkzeug(wortlautfest=False))
    assert werkzeug.stimme_geeignet("testwerkzeug") is True


def test_stimme_geeignet_is_false_for_an_unknown_werkzeug():
    assert werkzeug.stimme_geeignet("gibt-es-nicht") is False


# --- die vier Mathe-Werkzeuge, durch den Bauer gezogen: der eigentliche Beweis ------------

def test_all_four_math_werkzeuge_pass_the_contract_check():
    werkzeuge_seed.registriere_mathe_werkzeuge()
    for name in ("ableitung", "extremstellen", "stammfunktion", "integral"):
        w = werkzeug.registriert(name)
        assert w is not None, name
        assert werkzeug.pruefen(w) == [], name


def test_all_four_math_werkzeuge_are_wortlautfest_and_never_stimme_geeignet():
    # Konsistenz-Beweis mit der ALTEN, handgepflegten Menge in companion.py: dieselbe
    # Zelle "berechnen" darf dort auch nicht als Stimme-geeignet gelten
    werkzeuge_seed.registriere_mathe_werkzeuge()
    for name in ("ableitung", "extremstellen", "stammfunktion", "integral"):
        assert werkzeug.stimme_geeignet(name) is False, name
    assert "berechnen" not in companion._STIMME_GEEIGNET


def test_ableitung_werkzeug_actually_computes_through_the_registry():
    werkzeuge_seed.registriere_mathe_werkzeuge()
    w = werkzeug.registriert("ableitung")
    r = w.implementierung("3x^2 + 2x")
    assert r["ok"] and r["ableitung"] == "6*x + 2"
    text = w.formulierung(r)
    assert "6*x + 2" in text


def test_registry_wide_contract_check_the_testen_step_as_a_ci_gate():
    # der "Testen"-Schritt aus dem Bild ist bewusst kein Laufzeit-Pytest-Aufruf innerhalb des
    # Bauers, sondern EIN Vertrags-Test über die GANZE Registry -- wie test_membrane_purity.py
    # es für Membranen tut. Wächst automatisch mit, sobald mehr Werkzeuge registriert werden.
    werkzeuge_seed.registriere_mathe_werkzeuge()
    for w in werkzeug.alle():
        assert werkzeug.pruefen(w) == [], w.name
        assert isinstance(w.wortlautfest, bool), w.name
        assert isinstance(w.schreibt, bool), w.name


def test_alle_returns_werkzeuge_sorted_by_name():
    werkzeuge_seed.registriere_mathe_werkzeuge()
    namen = [w.name for w in werkzeug.alle()]
    assert namen == sorted(namen)
    assert "ableitung" in namen and "integral" in namen
