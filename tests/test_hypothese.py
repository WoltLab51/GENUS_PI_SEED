"""Die dritte Denkweise: HYPOTHESE — Vermuten und Prüfen (Ronny 2026-07-06: „mach ③ den
Hypothese-Test-Loop"). GENUS erzeugt selbst eine Konjektur (Geschwister-Analogie, deterministisch)
und TESTET sie mit der Inferenz (bestätigt/widerlegt/offen). Der aktive Halbkreis, der den
Methoden-Bogen schließt; die „gezähmte Kreativität" — etikettiert, gedeckelt, geprüft."""
from genus import hypothese, reactors, sources


def _isa(conn, kind, eltern, quelle="wikidata"):
    reactors.observe_relation(conn, kind, "is_a", eltern, quelle)


def _events(conn):
    return conn.execute("SELECT COUNT(*) n FROM event_log").fetchone()["n"]


# --- Erzeugen: die Vermutung --------------------------------------------------------------

def test_vermute_erzeugt_echte_konjektur(conn):
    # Hund und Katze sind is_a Haustier und part_of Haushalt; das Pferd nicht -> Analogie
    for tier in ("Hund", "Katze", "Pferd"):
        _isa(conn, tier, "Haustier")
    for tier in ("Hund", "Katze"):
        reactors.observe_relation(conn, tier, "part_of", "Haushalt", "wikidata")
    v = hypothese.vermute(conn, "Pferd")
    treffer = [x for x in v if x["praedikat"] == "part_of" and x["objekt"] == "Haushalt"]
    assert treffer, "die Analogie Pferd part_of Haushalt fehlt"
    h = treffer[0]["herleitung"]
    assert h["k"] == 2 and h["m"] == 2 and h["muster"] == "geschwister_analogie"


def test_vermute_deterministisch_und_schweigt_ohne_geschwister(conn):
    for tier in ("Hund", "Katze", "Pferd"):
        _isa(conn, tier, "Haustier")
    for tier in ("Hund", "Katze"):
        reactors.observe_relation(conn, tier, "part_of", "Haushalt", "wikidata")
    assert hypothese.vermute(conn, "Pferd") == hypothese.vermute(conn, "Pferd")   # stabil
    # ein Einzelkind (kein Geschwister) trägt keine Analogie -> ehrlich leer
    _isa(conn, "Einhorn", "Fabelwesen")
    assert hypothese.vermute(conn, "Einhorn") == []


def test_mehrfach_bequellung_verfaelscht_die_mehrheit_nicht(conn):
    # Der lebende Graph bequellt jede Kante mehrfach (Wikidata + Lexem + DBnary). Ein Geschwister
    # darf trotzdem nur EINE Stimme in der Mehrheits-Arithmetik haben (Review-Fund, hoch).
    for tier in ("Hund", "Katze", "Pferd"):
        _isa(conn, tier, "Haustier")
    _isa(conn, "Hund", "Haustier", "lexem")        # Hund doppelt bequellt
    _isa(conn, "Hund", "Haustier", "dbnary")       # Hund dreifach bequellt
    reactors.observe_relation(conn, "Hund", "part_of", "Haushalt", "wikidata")   # nur EIN Geschwister trägt es
    v = hypothese.vermute(conn, "Pferd")
    # 1 von 2 distinkten Geschwistern (Hund/Katze) ist KEINE Mehrheit -> keine erfundene Konjektur
    assert not any(x["objekt"] == "Haushalt" for x in v)


def test_keine_mehrheit_keine_vermutung(conn):
    # 1 von 3 Geschwistern trägt das Merkmal -> keine Mehrheit -> keine Vermutung
    for tier in ("A", "B", "C", "D"):
        _isa(conn, tier, "Klasse")
    reactors.observe_relation(conn, "B", "part_of", "Etwas", "wikidata")
    v = hypothese.vermute(conn, "A")
    assert not any(x["objekt"] == "Etwas" for x in v)


# --- Prüfen: der Test ---------------------------------------------------------------------

def test_teste_bestaetigt_direkt(conn):
    _isa(conn, "Hund", "Haustier")
    e = hypothese.teste_konjektur(conn, "Hund", "is_a", "Haustier")
    assert e["urteil"] == "bestaetigt" and e["entailt"] and e["direkt"]


def test_teste_bestaetigt_transitiv_mit_vertrauen(conn):
    _isa(conn, "Hund", "Haustier")
    _isa(conn, "Haustier", "Tier")
    e = hypothese.teste_konjektur(conn, "Hund", "is_a", "Tier")     # nicht direkt, aber entailt
    assert e["urteil"] == "bestaetigt" and not e["direkt"]
    assert e["vertrauen"] is not None                              # schwächste Prämisse der Kette


def test_nicht_transitives_praedikat_entailt_nicht_ueber_ketten(conn):
    # „mag" ist nicht transitiv -> ein Zwei-Hop-Pfad zählt NICHT als bestätigt
    reactors.observe_relation(conn, "A", "mag", "B", "wikidata")
    reactors.observe_relation(conn, "B", "mag", "C", "wikidata")
    e = hypothese.teste_konjektur(conn, "A", "mag", "C")
    assert e["entailt"] is False and e["urteil"] != "bestaetigt"


def test_refutation_zyklus(conn):
    # „Haustier is_a Hund" schlösse einen Ring (Hund is_a Haustier existiert) -> widerlegt
    _isa(conn, "Hund", "Haustier")
    e = hypothese.teste_konjektur(conn, "Haustier", "is_a", "Hund")
    assert e["urteil"] == "widerlegt" and e["schliesst_ring"]


def test_refutation_wal_ist_kein_fisch(conn):
    # DER PRÜFSTEIN: der Wal ist ein Säugetier; Säugetier ist unvereinbar mit Fisch (Quelle welt)
    hypothese.seed_hypothesen(conn)
    _isa(conn, "Wal", "konzept:saeugetier")
    vorher = _events(conn)
    e = hypothese.teste_konjektur(conn, "Wal", "is_a", "konzept:fisch")
    assert e["urteil"] == "widerlegt"
    assert e["unvereinbar_kette"] and e["unvereinbar_kette"]["quelle"] == "welt"
    assert _events(conn) == vorher            # der Test schreibt NICHTS


def test_unvereinbar_liest_beide_richtungen(conn):
    # Saat nur (fisch, unvereinbar_mit, saeugetier); die Gegenrichtung muss ebenso widerlegen
    hypothese.seed_hypothesen(conn)
    _isa(conn, "Hai", "konzept:fisch")
    e = hypothese.teste_konjektur(conn, "Hai", "is_a", "konzept:saeugetier")
    assert e["urteil"] == "widerlegt"


def test_disjunktheit_widerlegt_nur_is_a_kein_part_of(conn):
    # ein Metallteil kann Teil eines Holzdings sein — Disjunktheit widerlegt keine part_of-Konjektur
    hypothese.seed_hypothesen(conn)
    _isa(conn, "Schraube", "konzept:fisch")        # (künstlich: Schraube „ist ein" fisch-Klasse)
    e = hypothese.teste_konjektur(conn, "Schraube", "part_of", "konzept:saeugetier")
    assert e["urteil"] != "widerlegt"              # part_of wird von Klassen-Disjunktheit nicht berührt


def test_tiefe_widerlegung_ueber_lange_is_a_kette(conn):
    # Auf realen Wikidata-Leitern liegt die disjunkte Ober-Klasse viele Hops entfernt (> MAX_DEPTH=6).
    # Die Widerlegung muss trotzdem greifen, sonst würde eine geerdete Grenze als „offen" verkauft
    # (Review-Fund, mittel — der ehrlichkeits-kritische False-Negative).
    hypothese.seed_hypothesen(conn)
    kette = ["Wal"] + [f"Zwischen{i}" for i in range(10)] + ["konzept:saeugetier"]
    for unten, oben in zip(kette, kette[1:]):          # Wal -> Zwischen0 -> ... -> saeugetier (11 Hops)
        _isa(conn, unten, oben)
    e = hypothese.teste_konjektur(conn, "Wal", "is_a", "konzept:fisch")
    assert e["urteil"] == "widerlegt"                  # trotz 11 Hops bis zur disjunkten Klasse
    assert e["unvereinbar_kette"]["quelle"] == "welt"


def test_offen_ist_ehrlich_nicht_wahr(conn):
    _isa(conn, "Hund", "Haustier")
    e = hypothese.teste_konjektur(conn, "Hund", "is_a", "Wolf")     # konsistent, aber unbelegt
    assert e["urteil"] == "offen"
    text = hypothese.narrate_hypothese(conn, e)
    assert "nicht widerlegbar" in text and "wahr" in text


def test_ueber_nicht_transitives_praedikat_nicht_widerlegbar(conn):
    # used_for bleibt bewusst DRAUSSEN: keine Inverse, keine Azyklizität -> nicht ehrlich widerlegbar
    reactors.observe_relation(conn, "A", "used_for", "B", "wikidata")
    e = hypothese.teste_konjektur(conn, "A", "used_for", "C")
    assert e["widerlegbar"] is False and e["urteil"] != "widerlegt"
    assert "weder beweisen noch widerlegen" in hypothese.narrate_hypothese(conn, e)


def test_used_for_wird_nie_konjekturiert(conn):
    # der Generator übertraegt used_for NICHT (nicht in ANALOGIE_PRAEDIKATE), sonst waeren es
    # unwiderlegbare Vermutungen; nur is_a/part_of/causes/caused_by sind zugelassen
    for x in ("Saege", "Hammer", "Bohrer"):
        _isa(conn, x, "Werkzeug")
    for x in ("Hammer", "Bohrer"):
        reactors.observe_relation(conn, x, "used_for", "Bau", "wikidata")
    assert not any(v["praedikat"] == "used_for" for v in hypothese.vermute(conn, "Saege"))
    assert set(hypothese.ANALOGIE_PRAEDIKATE) == {"is_a", "part_of", "causes", "caused_by"}


def test_causes_bestaetigt_gleiche_richtung(conn):
    reactors.observe_relation(conn, "Regen", "causes", "Ueberschwemmung", "wikidata")
    e = hypothese.teste_konjektur(conn, "Regen", "causes", "Ueberschwemmung")
    assert e["urteil"] == "bestaetigt"
    # dieselbe Richtung auch als Inverse erkannt (B caused_by A == A causes B)
    reactors.observe_relation(conn, "Blitz", "caused_by", "Gewitter", "wikidata")
    assert hypothese.teste_konjektur(conn, "Gewitter", "causes", "Blitz")["urteil"] == "bestaetigt"


def test_causes_widerlegt_gegenrichtung(conn):
    # der Graph kennt „Ueberschwemmung causes Regen"? nein — aber die GEGENrichtung der Vermutung:
    reactors.observe_relation(conn, "Feuer", "causes", "Rauch", "wikidata")
    e = hypothese.teste_konjektur(conn, "Rauch", "causes", "Feuer")   # kehrt die Richtung um
    assert e["urteil"] == "widerlegt" and e["kausal"] == "widerlegt"
    assert "GEGENrichtung" in hypothese.narrate_hypothese(conn, e)
    assert "Rückkopplungs-Kreis" in hypothese.narrate_hypothese(conn, e)   # ehrlicher Vorbehalt
    # auch über die Inverse: A caused_by B  ==  B causes A  -> „A causes B" umgekehrt = widerlegt
    reactors.observe_relation(conn, "Krankheit", "caused_by", "Erreger", "wikidata")
    assert hypothese.teste_konjektur(conn, "Krankheit", "causes", "Erreger")["urteil"] == "widerlegt"


def test_caused_by_widerlegt_nennt_die_richtige_ursache(conn):
    # bei einer caused_by-Vermutung „A wird verursacht von B" (widerlegt, weil A causes B im Graphen)
    # ist A die bekannte Ursache — der Beweistext darf NICHT B als Ursache nennen (Review-Fund).
    reactors.observe_relation(conn, "Sturm", "causes", "Schaden", "wikidata")
    e = hypothese.teste_konjektur(conn, "Sturm", "caused_by", "Schaden")   # kehrt die Richtung um
    assert e["urteil"] == "widerlegt" and e["kausal"] == "widerlegt"
    text = hypothese.narrate_hypothese(conn, e)
    assert "»Sturm« steht als Ursache" in text          # A (Sturm) ist die Ursache, nicht B (Schaden)
    assert "»Schaden« steht als Ursache" not in text


def test_causes_offen_wenn_richtung_unbekannt(conn):
    reactors.observe_relation(conn, "X", "causes", "Y", "wikidata")   # unabhängiger Fakt
    e = hypothese.teste_konjektur(conn, "Duerre", "causes", "Missernte")
    assert e["urteil"] == "offen" and e["widerlegbar"] is True        # widerlegbar, aber kein Widerspruch


def test_vermute_erzeugt_kausal_konjektur(conn):
    # Geschwister teilen eine Wirkung -> der Generator vermutet sie auch fuer den Anker
    for x in ("Grippe", "Erkaeltung", "Angina"):
        _isa(conn, x, "Infektion")
    for x in ("Grippe", "Erkaeltung"):
        reactors.observe_relation(conn, x, "causes", "Fieber", "wikidata")
    treffer = [v for v in hypothese.vermute(conn, "Angina")
               if v["praedikat"] == "causes" and v["objekt"] == "Fieber"]
    assert treffer and treffer[0]["herleitung"]["k"] == 2


# --- Der eine Zug + die Emission ----------------------------------------------------------

def test_vermute_und_teste_gibt_die_widerlegte_grenze(conn):
    # der volle Wal-Bogen: die Analogie erzeugt „Wal is_a Fisch", der Test widerlegt sie
    hypothese.seed_hypothesen(conn)
    for tier in ("Wal", "Hai", "Thunfisch"):
        _isa(conn, tier, "konzept:meerestier")
    for fisch in ("Hai", "Thunfisch"):
        _isa(conn, fisch, "konzept:fisch")
    _isa(conn, "Wal", "konzept:saeugetier")
    e = hypothese.vermute_und_teste(conn, "Wal")
    assert e is not None and e["objekt"] == "konzept:fisch" and e["urteil"] == "widerlegt"


def test_readtime_kein_write(conn):
    hypothese.seed_hypothesen(conn)
    for tier in ("Hund", "Katze", "Pferd"):
        _isa(conn, tier, "Haustier")
    for tier in ("Hund", "Katze"):
        reactors.observe_relation(conn, tier, "part_of", "Haushalt", "wikidata")
    vorher = _events(conn)
    hypothese.vermute(conn, "Pferd")
    e = hypothese.vermute_und_teste(conn, "Pferd")
    hypothese.narrate_hypothese(conn, e)
    assert _events(conn) == vorher            # vermuten/testen/erzählen schreibt NICHTS


def test_tick_gedeckelt_und_idempotent(conn):
    for tier in ("Hund", "Katze", "Pferd"):
        _isa(conn, tier, "Haustier")
    for tier in ("Hund", "Katze"):
        reactors.observe_relation(conn, tier, "part_of", "Haushalt", "wikidata")
    e = hypothese.vermute_und_teste(conn, "Pferd")
    assert e["urteil"] == "offen"
    assert hypothese.emit_vermutung(conn, e) == 1          # neu ausgesprochen
    konf = sources.relation_confidence(conn, "Pferd", "part_of", "Haushalt")["confidence"]
    assert konf <= 0.25                                    # der model:-Deckel greift
    assert hypothese.emit_vermutung(conn, e) == 0          # kein Duplikat beim zweiten Tick


def test_widerlegte_wird_nie_ausgesprochen(conn):
    hypothese.seed_hypothesen(conn)
    _isa(conn, "Wal", "konzept:saeugetier")
    e = hypothese.teste_konjektur(conn, "Wal", "is_a", "konzept:fisch")
    e["herleitung"] = None
    assert hypothese.emit_vermutung(conn, e) == 0          # widerlegt -> Hand bleibt still


def test_kein_zweiter_speicher(conn):
    # keine neue Tabelle, kein hypothese_log: alle Schreibvorgänge sind relation_asserted-Events
    hypothese.seed_hypothesen(conn)
    for tier in ("Hund", "Katze", "Pferd"):
        _isa(conn, tier, "Haustier")
    for tier in ("Hund", "Katze"):
        reactors.observe_relation(conn, tier, "part_of", "Haushalt", "wikidata")
    hypothese.emit_vermutung(conn, hypothese.vermute_und_teste(conn, "Pferd"))
    typen = {r["event_type"] for r in conn.execute("SELECT DISTINCT event_type FROM event_log")}
    assert typen == {"relation_asserted"}


def test_herleitung_ist_sichtbar(conn):
    for tier in ("Hund", "Katze", "Pferd"):
        _isa(conn, tier, "Haustier")
    for tier in ("Hund", "Katze"):
        reactors.observe_relation(conn, tier, "part_of", "Haushalt", "wikidata")
    e = hypothese.vermute_und_teste(conn, "Pferd")
    text = hypothese.narrate_hypothese(conn, e)
    assert "2 von 2 Geschwistern" in text                 # der gelebte Zähler, kein Preset


def test_cli_nutzt_get_conn_keine_streudb(conn, tmp_path, monkeypatch):
    from click.testing import CliRunner
    from genus import cli, db

    dbpfad = tmp_path / "ledger.sqlite3"
    monkeypatch.setenv("GENUS_DB_PATH", str(dbpfad))
    c = db.connect(str(dbpfad))
    for tier in ("Hund", "Katze", "Pferd"):
        _isa(c, tier, "Haustier")
    for tier in ("Hund", "Katze"):
        reactors.observe_relation(c, tier, "part_of", "Haushalt", "wikidata")
    c.commit(); c.close()

    result = CliRunner().invoke(cli.main, ["hypothese", "Pferd"])
    assert result.exit_code == 0
    assert "Vermutung" in result.output
    assert not (tmp_path.parent / "genus.sqlite3").exists()   # keine Streu-DB
