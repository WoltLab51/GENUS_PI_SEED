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


def test_zyklische_norm_stuerzt_nicht_ab(conn):
    # eine Norm, die sich (über eine Merkmal-Kette) selbst voraussetzt -> früher RecursionError (P0.1)
    reactors.observe_relation(conn, "norm:x", "braucht", "merkmal:y", "gesetz")
    reactors.observe_relation(conn, "merkmal:y", "braucht", "norm:x", "gesetz")   # Ring
    e = recht.subsumiere(conn, "norm:x", {})
    assert e["erfuellt"] is False                              # unerfüllbar, KEIN Absturz
    assert isinstance(recht.narrate_subsumtion(conn, e), str)  # narrate übersteht es


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


# --- Deuter-Anbindung: freier Text → Merkmale (Modell liest, Kern rechnet) ---------------

def test_blatt_merkmale_steigt_rekursiv_zu_den_faktbasierten_hinab(conn):
    _mit_norm(conn)
    ids = {b["id"] for b in recht.blatt_merkmale(conn, "norm:kaufpreis")}
    # kaufvertrag ist zusammengesetzt -> seine BLÄTTER (angebot/annahme), nicht es selbst
    assert ids == {"merkmal:angebot", "merkmal:annahme", "merkmal:faelligkeit"}
    assert "merkmal:kaufvertrag" not in ids


def test_die_grenze_laesst_nur_bekannte_merkmale_und_zwicky_zellen_zu(conn):
    _mit_norm(conn)
    g = recht.gbnf_sachverhalt(["merkmal:angebot", "merkmal:faelligkeit"])
    assert "merkmal:angebot" in g and "merkmal:faelligkeit" in g
    for zelle in recht.MERKMAL_ZELLEN:
        assert zelle in g   # die kreuz-konsistenten Zellen sind die einzigen erlaubten Werte


def test_subsumiere_frei_uebersetzt_die_zwicky_zelle_und_rechnet_deterministisch(conn):
    _mit_norm(conn)
    # ein FAKE-Deuter (kein Modell nötig) liest die Schilderung in Zwicky-Zellen
    def fake(text, blaetter):
        return {"merkmal:angebot": "erfuellt_urkunde", "merkmal:annahme": "erfuellt_zeuge",
                "merkmal:faelligkeit": "erfuellt_aussage"}
    frei = recht.subsumiere_frei(conn, "norm:kaufpreis", "ich habe ein Auto verkauft ...", fake)
    e = frei["ergebnis"]
    assert e["erfuellt"] is True
    # Zelle -> Quelle: urkunde->dokument:genannt, zeuge->zeuge:genannt, aussage->aussage
    assert frei["sachverhalt"]["merkmal:angebot"] == "dokument:genannt"
    assert frei["sachverhalt"]["merkmal:annahme"] == "zeuge:genannt"
    assert frei["sachverhalt"]["merkmal:faelligkeit"] == "aussage"
    assert e["schwaechste"]["merkmal"] == "merkmal:faelligkeit"   # nur Aussage = schwächste


def test_subsumiere_frei_wirft_erfundene_und_unerfuellte_zellen_weg(conn):
    _mit_norm(conn)
    def fake(text, blaetter):
        return {"merkmal:angebot": "erfuellt_urkunde",
                "merkmal:erfunden": "erfuellt_urkunde",   # unbekannt -> raus
                "merkmal:annahme": "offen"}               # offen -> nicht erfüllt
    frei = recht.subsumiere_frei(conn, "norm:kaufpreis", "...", fake)
    assert "merkmal:erfunden" not in frei["sachverhalt"]
    assert "merkmal:annahme" not in frei["sachverhalt"]
    assert frei["ergebnis"]["erfuellt"] is False


def test_zwicky_gewinn_nein_wird_von_offen_unterschieden(conn):
    # der eigentliche Zwicky-Gewinn: „nicht_erfuellt" (aktiv verneint) ist etwas anderes als
    # „offen" (nicht erwähnt) -- beides verhindert den Anspruch, heißt aber Verschiedenes
    _mit_norm(conn)
    fake = lambda t, b: {"merkmal:angebot": "erfuellt_urkunde",
                         "merkmal:annahme": "nicht_erfuellt",       # der Fall verneint sie
                         "merkmal:faelligkeit": "offen"}            # der Fall schweigt dazu
    frei = recht.subsumiere_frei(conn, "norm:kaufpreis", "...", fake)
    text = recht.narrate_frei(conn, frei)
    assert "ausdrücklich NICHT erfüllt" in text and "Annahme" in text
    assert frei["ergebnis"]["erfuellt"] is False


def test_narrate_frei_rahmt_die_deutung_ehrlich(conn):
    _mit_norm(conn)
    fake = lambda t, b: {"merkmal:angebot": "erfuellt_urkunde", "merkmal:annahme": "erfuellt_urkunde",
                         "merkmal:faelligkeit": "erfuellt_aussage"}
    frei = recht.subsumiere_frei(conn, "norm:kaufpreis", "...", fake)
    text = recht.narrate_frei(conn, frei)
    assert "meine Deutung" in text and "kein Anwalt" in text
    assert "der Anspruch besteht" in text   # der exakte Kern darunter


def test_subsumiere_frei_ist_read_time(conn):
    _mit_norm(conn)
    vorher = conn.execute("SELECT COUNT(*) n FROM event_log").fetchone()["n"]
    recht.subsumiere_frei(conn, "norm:kaufpreis", "...",
                          lambda t, b: {"merkmal:angebot": "erfuellt_urkunde"})
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
