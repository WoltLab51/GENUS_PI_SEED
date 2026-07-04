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
    # Seit Phase 3 gibt es keine zweite handgepflegte Menge mehr: die Stimme-Eignung
    # folgt überall strukturell aus der Spec. "berechnen" hat bewusst KEINEN
    # Zellen-Registry-Eintrag (nur die vier Mathe-Werkzeuge + die Muster-Schnellspur)
    # -- ein unregistrierter Name ist automatisch nie Stimme-geeignet.
    werkzeuge_seed.registriere_mathe_werkzeuge()
    companion.registriere_zellen()
    for name in ("ableitung", "extremstellen", "stammfunktion", "integral"):
        assert werkzeug.stimme_geeignet(name) is False, name
    assert werkzeug.stimme_geeignet(f"{companion.ZELLE_PREFIX}berechnen") is False


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


# --- Phase 3 Scheibe 1: die Gesprächszellen laufen durch den Werkzeugbauer ------------


def test_alle_zellen_sind_registrierte_geprueft_werkzeuge():
    companion.registriere_zellen()
    zellen = companion._handelbare_werkzeuge()
    assert set(zellen) == set(companion._HANDELBAR)   # gleiche Namen, jetzt geprüft
    for name, w in zellen.items():
        assert werkzeug.pruefen(w) == [], name
        assert w.name == f"{companion.ZELLE_PREFIX}{name}"
        assert w.beschreibung.strip(), name
        assert w.pruefbar_als, name


def test_zellen_schreibrechte_sind_ausdruecklich():
    # Nur merken/tatsache schreiben (via erinnerung.merke) -- alles andere liest.
    zellen = companion._handelbare_werkzeuge()
    schreibend = {name for name, w in zellen.items() if w.schreibt}
    assert schreibend == {"merken", "tatsache"}


def test_stimme_eignung_folgt_strukturell_aus_der_spec():
    # Die frühere zweite Menge _STIMME_GEEIGNET ist weg -- Eignung = not wortlautfest.
    companion.registriere_zellen()
    frei = {name for name, w in companion._handelbare_werkzeuge().items()
            if not w.wortlautfest}
    assert frei == {"definition", "beziehung", "vergleich", "grammatik", "frage-begriff"}
    assert werkzeug.stimme_geeignet(f"{companion.ZELLE_PREFIX}definition")
    assert not werkzeug.stimme_geeignet(f"{companion.ZELLE_PREFIX}wiederholen")
    assert not hasattr(companion, "_STIMME_GEEIGNET")


def test_dispatch_ueberlebt_eine_geleerte_registry():
    # conftest leert die REGISTRY vor jedem Test -- der Dispatch registriert idempotent
    # nach (dieselbe Selbstheilung wie registriere_mathe_werkzeuge): eine geleerte
    # Registry darf nie eine stumme Antwort-Lücke erzeugen.
    werkzeug.REGISTRY.clear()
    zellen = companion._handelbare_werkzeuge()
    assert "definition" in zellen and "dank" in zellen


# --- Phase 3 Scheibe 2: die Registrierungs-ENTSCHEIDUNG wird Ledger-Geschichte --------


def test_registrierung_wird_einmal_protokolliert_nie_gespammt(conn):
    werkzeuge_seed.registriere_mathe_werkzeuge()
    companion.registriere_zellen()
    n = len(werkzeug.alle())
    assert werkzeug.protokolliere_registrierungen(conn) == n   # erste Protokollierung: alle
    assert werkzeug.protokolliere_registrierungen(conn) == 0   # Prozess-Start spammt nie
    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM event_log WHERE event_type = 'werkzeug_registriert'"
    ).fetchone()
    assert rows["n"] == n


def test_vertragsaenderung_schreibt_eine_neue_entscheidung(conn):
    werkzeug.verdrahten(_leeres_werkzeug(wortlautfest=True))
    assert werkzeug.protokolliere_registrierungen(conn) == 1
    # dieselbe Spec nochmal verdrahtet (Neuladen) -> keine neue Entscheidung
    werkzeug.verdrahten(_leeres_werkzeug(wortlautfest=True))
    assert werkzeug.protokolliere_registrierungen(conn) == 0
    # ein ECHTER Vertragswechsel (wortlautfest kippt) -> neue Entscheidung, Historie bleibt
    werkzeug.verdrahten(_leeres_werkzeug(wortlautfest=False))
    assert werkzeug.protokolliere_registrierungen(conn) == 1
    rows = conn.execute(
        "SELECT payload FROM event_log WHERE event_type = 'werkzeug_registriert' ORDER BY id"
    ).fetchall()
    import json as _json
    historie = [_json.loads(r["payload"])["wortlautfest"] for r in rows]
    assert historie == [True, False]


def test_beschreibungs_prosa_ist_keine_neue_entscheidung(conn):
    # Der Fingerabdruck ist der VERTRAG (Parameter, schreibt, wortlautfest, pruefbar_als)
    # -- Prosa darf sich aendern, ohne die Historie aufzublaehen.
    werkzeug.verdrahten(_leeres_werkzeug(beschreibung="Erste Prosa."))
    assert werkzeug.protokolliere_registrierungen(conn) == 1
    werkzeug.verdrahten(_leeres_werkzeug(beschreibung="Ganz andere Prosa."))
    assert werkzeug.protokolliere_registrierungen(conn) == 0


def test_werkzeug_registriert_ist_bewusst_roh_und_replay_stabil(conn):
    # Der Phase-1-Vertragstest erzwingt die Entscheidung (projiziert oder roh) ohnehin;
    # hier zusaetzlich der Beweis, dass ein protokolliertes Event den Replay nicht stoert.
    from genus import event_router, integrity
    assert "werkzeug_registriert" in event_router.BEWUSST_ROH
    werkzeug.verdrahten(_leeres_werkzeug())
    werkzeug.protokolliere_registrierungen(conn)
    report = integrity.check(conn)
    assert report["ok"], report
