"""Die Deduktion als allgemeines Werkzeug (Ronny 2026-07-06): Modus Ponens über braucht/bewirkt-
Regeln, domänenfrei, rekursiv, Vertrauen = schwächste Prämisse — plus Vorwärts- UND
Rückwärtsverkettung. Die Heraushebung des Musters, das in inference.py und recht.py fest
verdrahtet lag."""
from genus import deduktion, reactors


def _regel(conn, regel, praemissen, folge=None, quelle="test"):
    for p in praemissen:
        reactors.observe_relation(conn, regel, "braucht", p, quelle)
    if folge:
        reactors.observe_relation(conn, regel, "bewirkt", folge, quelle)


def test_alle_praemissen_gegeben_die_folge_gilt(conn):
    _regel(conn, "r:test", ["a", "b"], "z")
    e = deduktion.schliesse(conn, "r:test", {"a": "q1", "b": "q2"})
    assert e["erfuellt"] is True and e["folge"] == "z"


def test_eine_offene_praemisse_verhindert_den_schluss(conn):
    _regel(conn, "r:test", ["a", "b"], "z")
    e = deduktion.schliesse(conn, "r:test", {"a": "q1"})
    assert e["erfuellt"] is False
    assert [p["atom"] for p in e["offen"]] == ["b"]


def test_rekursion_eine_praemisse_ist_selbst_eine_regel(conn):
    _regel(conn, "r:ober", ["r:unter", "c"], "z")
    _regel(conn, "r:unter", ["a", "b"])          # zusammengesetzte Prämisse (Unter-Regel)
    e = deduktion.schliesse(conn, "r:ober", {"a": "q", "b": "q", "c": "q"})
    assert e["erfuellt"] is True
    unter = next(p for p in e["praemissen"] if p["atom"] == "r:unter")
    assert unter["art"] == "abgeleitet" and unter["erfuellt"]


def test_vertrauen_ist_die_schwaechste_praemisse(conn):
    # eine Quelle nach oben kalibrieren, damit sich die Vertrauen unterscheiden
    for _ in range(6):
        reactors.observe_relation(conn, "belegt@de", "expresses", "Qx", "stark")
    _regel(conn, "r:test", ["a", "b"], "z")
    e = deduktion.schliesse(conn, "r:test", {"a": "stark", "b": "schwach"})
    trusts = [p["trust"] for p in e["praemissen"]]
    assert e["vertrauen"] == min(trusts)


def test_rueckwaerts_beweise_mir_z(conn):
    # BACKWARD chaining: nenne ein Ziel, finde die Regel, die es bewirkt, und beweise sie
    _regel(conn, "r:test", ["a", "b"], "ziel:z")
    b = deduktion.beweise(conn, "ziel:z", {"a": "q", "b": "q"})
    assert b is not None and b["beweisbar"] is True
    assert b["ergebnis"]["regel"] == "r:test"


def test_rueckwaerts_zeigt_ehrlich_was_zum_beweis_fehlt(conn):
    _regel(conn, "r:test", ["a", "b"], "ziel:z")
    b = deduktion.beweise(conn, "ziel:z", {"a": "q"})            # b fehlt
    assert b["beweisbar"] is False
    assert [p["atom"] for p in b["ergebnis"]["offen"]] == ["b"]


def test_rueckwaerts_none_wenn_kein_regel_das_ziel_bewirkt(conn):
    assert deduktion.beweise(conn, "ziel:unbekannt", {}) is None


def test_vorwaerts_leitet_ketten_bis_zum_fixpunkt_ab(conn):
    # z folgt aus a,b; und w folgt aus z -> eine abgeleitete Folge erfüllt die nächste Regel
    _regel(conn, "r:eins", ["a", "b"], "z")
    _regel(conn, "r:zwei", ["z"], "w")
    folgen = {f["folge"] for f in deduktion.leite_ab(conn, {"a": "q", "b": "q"})}
    assert folgen == {"z", "w"}                                 # die Kette rollt bis w


def test_deduktion_ist_read_time(conn):
    _regel(conn, "r:test", ["a"], "z")
    vorher = conn.execute("SELECT COUNT(*) n FROM event_log").fetchone()["n"]
    deduktion.schliesse(conn, "r:test", {"a": "q"})
    deduktion.beweise(conn, "z", {"a": "q"})
    deduktion.leite_ab(conn, {"a": "q"})
    assert conn.execute("SELECT COUNT(*) n FROM event_log").fetchone()["n"] == vorher


def test_narrate_ist_ein_glaeserner_beweis(conn):
    _regel(conn, "r:test", ["a", "b"], "z")
    e = deduktion.schliesse(conn, "r:test", {"a": "q", "b": "q"})
    text = deduktion.narrate(conn, e)
    assert "bewiesen" in text and "schwächste Prämisse" in text


def test_die_rechts_norm_ist_ueber_den_allgemeinen_schliesser_beweisbar(conn):
    # der Beweis der Heraushebung: der GENERAL-Schließer beweist eine Rechtsfolge über den
    # vorhandenen norm:kaufpreis-Bauplan, OHNE eine Zeile Recht zu kennen (Rückwärtsverkettung)
    from genus import recht
    recht.seed_normen(conn)
    b = deduktion.beweise(conn, "rechtsfolge:kaufpreiszahlung",
                          {"merkmal:angebot": "dokument:vertrag",
                           "merkmal:annahme": "dokument:vertrag",
                           "merkmal:faelligkeit": "ronny"})
    assert b is not None and b["beweisbar"] is True
    assert b["ergebnis"]["regel"] == "norm:kaufpreis"
