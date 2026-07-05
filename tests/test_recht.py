"""Die erste Denkweise: juristische Subsumtion (Ronny 2026-07-05, docs/GENUS_INTELLIGENZ.md §4).
Norm = Bauplan (braucht/bewirkt), Subsumtion = Verallgemeinerung der is_a-Inferenz, Vertrauen
= schwächste Prämisse = Beweislast-Radar, Wertung = ehrlicher Mensch-Slot. Read-time, gläsern."""
from genus import reactors, recht, sources


def _mit_norm(conn):
    recht.seed_normen(conn)
    return conn


def test_seed_ist_idempotent(conn):
    n1 = recht.seed_normen(conn)
    n2 = recht.seed_normen(conn)
    assert n1 == len(recht.NORM_SEED) and n2 == 0


def test_die_norm_ist_ein_bauplan_mit_rekursivem_merkmal_baum(conn):
    _mit_norm(conn)
    # norm:kaufpreis braucht kaufvertrag + faelligkeit; kaufvertrag ist selbst zusammengesetzt
    top = {r["object"] for r in sources.relations(conn, subject="norm:kaufpreis", predicate="braucht")}
    assert top == {"merkmal:kaufvertrag", "merkmal:faelligkeit"}
    unter = {r["object"] for r in sources.relations(conn, subject="merkmal:kaufvertrag", predicate="braucht")}
    assert unter == {"merkmal:angebot", "merkmal:annahme"}


def test_alle_merkmale_erfuellt_der_anspruch_besteht(conn):
    _mit_norm(conn)
    # der Sachverhalt erfüllt die BLATT-Merkmale; Kaufvertrag wird rekursiv abgeleitet
    sv = {"merkmal:angebot": "dokument:vertrag",
          "merkmal:annahme": "dokument:vertrag",
          "merkmal:faelligkeit": "dokument:rechnung"}
    e = recht.subsumiere(conn, "norm:kaufpreis", sv)
    assert e["erfuellt"] is True
    assert e["rechtsfolge"] == "rechtsfolge:kaufpreiszahlung"
    # das zusammengesetzte Merkmal ist abgeleitet erfüllt (Rekursion)
    kv = next(m for m in e["merkmale"] if m["merkmal"] == "merkmal:kaufvertrag")
    assert kv["erfuellt"] and kv["art"] == "abgeleitet"


def test_ein_fehlendes_merkmal_verhindert_den_anspruch(conn):
    _mit_norm(conn)
    sv = {"merkmal:angebot": "dokument:vertrag", "merkmal:faelligkeit": "ronny"}  # Annahme fehlt
    e = recht.subsumiere(conn, "norm:kaufpreis", sv)
    assert e["erfuellt"] is False
    # das offene BLATT ist die Annahme (über den Kaufvertrag)
    text = recht.narrate_subsumtion(conn, e)
    assert "besteht (noch) NICHT" in text


def test_beweislast_radar_findet_die_schwaechste_praemisse(conn):
    _mit_norm(conn)
    # Angebot+Annahme urkundlich, Fälligkeit nur Parteivortrag -> die schwächste Stelle
    sv = {"merkmal:angebot": "dokument:vertrag",
          "merkmal:annahme": "dokument:vertrag",
          "merkmal:faelligkeit": "ronny"}
    e = recht.subsumiere(conn, "norm:kaufpreis", sv)
    assert e["erfuellt"] is True
    assert e["schwaechste"]["merkmal"] == "merkmal:faelligkeit"
    assert e["schwaechste"]["art"] == "parteivortrag"
    text = recht.narrate_subsumtion(conn, e)
    assert "Beweislast" in text and "nur an deiner Aussage" in text


def test_vertrauen_ist_die_schwaechste_praemisse(conn):
    # exakt die is_a-Regel: die Kette ist nur so stark wie ihr schwächstes Glied
    _mit_norm(conn)
    reactors.observe_relation(conn, "a", "b", "c", "stark")   # kalibriert eine Quelle nach oben? egal:
    sv = {"merkmal:angebot": "dokument:vertrag",
          "merkmal:annahme": "dokument:vertrag",
          "merkmal:faelligkeit": "ronny"}
    e = recht.subsumiere(conn, "norm:kaufpreis", sv)
    trusts = [m["trust"] for m in e["merkmale"] if m["trust"] is not None]
    assert e["vertrauen"] == min(trusts)


def test_eine_wertung_ist_ein_ehrlicher_mensch_slot(conn):
    # ein Merkmal mit -art-> wertung wird NIE selbst gefüllt -- GENUS benennt es
    recht.seed_normen(conn)
    reactors.observe_relation(conn, "norm:test", "braucht", "merkmal:angemessen", "gesetz")
    reactors.observe_relation(conn, "merkmal:angemessen", "inhalt", "die Frist war angemessen", "gesetz")
    reactors.observe_relation(conn, "merkmal:angemessen", "art", "wertung", "gesetz")
    e = recht.subsumiere(conn, "norm:test", {"merkmal:angemessen": "ronny"})
    m = e["merkmale"][0]
    assert m["erfuellt"] is False and m["art"] == "wertung"   # trotz „Quelle" nicht gefüllt
    assert "menschliches Urteil" in recht.narrate_subsumtion(conn, e)


def test_subsumtion_erzeugt_keine_events_read_time(conn):
    _mit_norm(conn)
    vorher = conn.execute("SELECT COUNT(*) n FROM event_log").fetchone()["n"]
    recht.subsumiere(conn, "norm:kaufpreis", {"merkmal:angebot": "ronny"})
    assert conn.execute("SELECT COUNT(*) n FROM event_log").fetchone()["n"] == vorher


def test_der_beweisbaum_nennt_jede_voraussetzung_mit_ihrem_beleg(conn):
    _mit_norm(conn)
    sv = {"merkmal:angebot": "dokument:vertrag",
          "merkmal:annahme": "dokument:vertrag",
          "merkmal:faelligkeit": "ronny"}
    text = recht.narrate_subsumtion(conn, sv and recht.subsumiere(conn, "norm:kaufpreis", sv))
    assert "der Anspruch besteht" in text
    assert "belegt durch dokument:vertrag" in text          # die Urkunde benannt
    assert "nur Parteivortrag" in text                      # die Aussage ehrlich benannt
