"""③ Scheibe C: der deduktive Planer als PRIMÄRPFAD der Beziehungsfrage. Beide Rufer
(Deuter-Zelle UND Regex-Erkenner) laufen durch relate_geplant: der selbst-deduzierte Plan
antwortet; jedes Scheitern fällt GEZÄHLT aufs handgebaute Netz (der Nutzer merkt nichts,
das Zählwerk alles). Dazu die Anker-Leine (modell-extrahierte Begriffe müssen Wörter der
Nachricht sein) und das fail-silente Zählwerk (Telemetrie bricht nie eine Antwort)."""
import json

from genus import auskunft, companion, reactors, werkplan, werkzeuge_auskunft, zaehlwerk


def _hierarchie(conn):
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Q144", "is_a", "Q_haustier", "wikidata")
    reactors.observe_relation(conn, "Haustier@de", "expresses", "Q_haustier", "wikidata")
    reactors.observe_relation(conn, "Q_haustier", "is_a", "Q_tier", "wikidata")
    reactors.observe_relation(conn, "Tier@de", "expresses", "Q_tier", "wikidata")


def _zaehlwerk_datei(tmp_path, monkeypatch):
    pfad = tmp_path / "zaehlwerk.jsonl"
    monkeypatch.setenv("GENUS_PLANER_ZAEHLWERK", str(pfad))
    return pfad


def test_relate_geplant_ist_drop_in_gleich_und_zaehlt_treffer(conn, tmp_path, monkeypatch):
    _zaehlwerk_datei(tmp_path, monkeypatch)
    _hierarchie(conn)
    geplant = werkzeuge_auskunft.relate_geplant(conn, "Hund", "Tier")
    assert geplant == auskunft._relate_terms(conn, "Hund", "Tier")   # Zeichen für Zeichen
    assert zaehlwerk.stand().get("beziehung:treffer", 0) >= 1


def test_regex_erkenner_laeuft_planer_zuerst(conn, tmp_path, monkeypatch):
    # auch der CLI-/Muster-Pfad rechnet über den Plan -- die Regex ist nur noch der Erkenner
    _zaehlwerk_datei(tmp_path, monkeypatch)
    _hierarchie(conn)
    r = auskunft.relate(conn, "Ist ein Hund ein Tier?")
    assert r["verdict"] == "yes" and r["target"] == "Q_tier"
    assert zaehlwerk.stand().get("beziehung:treffer", 0) >= 1


def test_netz_faengt_wenn_kein_plan_da_ist(conn, tmp_path, monkeypatch):
    _zaehlwerk_datei(tmp_path, monkeypatch)
    _hierarchie(conn)
    monkeypatch.setattr(werkzeuge_auskunft, "beziehungs_plan", lambda: None)
    r = werkzeuge_auskunft.relate_geplant(conn, "Hund", "Tier")
    assert r == auskunft._relate_terms(conn, "Hund", "Tier")   # Antwort unverändert richtig
    assert zaehlwerk.stand().get("beziehung:rueckfall", 0) >= 1


def test_netz_faengt_einen_ausfuehrungsfehler(conn, tmp_path, monkeypatch):
    _zaehlwerk_datei(tmp_path, monkeypatch)
    _hierarchie(conn)

    def kracht(*a, **k):
        raise RuntimeError("kaputt")
    monkeypatch.setattr(werkplan, "fuehre_aus", kracht)
    r = werkzeuge_auskunft.relate_geplant(conn, "Hund", "Tier")
    assert r["verdict"] == "yes"   # das Netz trägt
    assert zaehlwerk.stand().get("beziehung:rueckfall", 0) >= 1


def test_anker_sensor_zaehlt_gedeutete_begriffe_blockt_aber_nie(conn, tmp_path, monkeypatch):
    # die Deuter-KERNFÄHIGKEIT bleibt: „wuffwuff" -> Hund wird beantwortet (die Antwort nennt
    # ihre Begriffe selbst -- ein fremder wäre sichtbar); der Sensor zählt nur, dass gedeutet
    # statt zitiert wurde (Rohdaten für ④)
    _zaehlwerk_datei(tmp_path, monkeypatch)
    _hierarchie(conn)
    guess = {"subject": "Hund", "object": "Tier"}
    antwort = companion._zelle_beziehung(
        conn, guess, "gehört sowas wie ein wuffwuff eigentlich dahin?", None, None)
    assert antwort and "Ja" in antwort and "»Hund«" in antwort   # Fähigkeit unangetastet
    assert zaehlwerk.stand().get("beziehung:anker_frei", 0) == 1


def test_anker_sensor_schweigt_bei_verankerten_begriffen(conn, tmp_path, monkeypatch):
    _zaehlwerk_datei(tmp_path, monkeypatch)
    _hierarchie(conn)
    guess = {"subject": "Hund", "object": "Tier"}
    antwort = companion._zelle_beziehung(conn, guess, "Ist ein Hund ein Tier?", None, None)
    assert antwort and "Ja" in antwort and "»Hund«" in antwort
    assert "beziehung:anker_frei" not in zaehlwerk.stand()
    # case-lenient: kleingeschriebenes Fragewort verankert das großgeschriebene Subjekt
    antwort2 = companion._zelle_beziehung(conn, guess, "ist ein hund ein tier?", None, None)
    assert antwort2 and "Ja" in antwort2
    assert "beziehung:anker_frei" not in zaehlwerk.stand()


def test_zaehlwerk_ist_fail_silent_die_antwort_leidet_nie(conn, tmp_path, monkeypatch):
    # Telemetrie-Pfad zeigt auf eine DATEI als Verzeichnis -> jede Zählung scheitert still;
    # die Antwort kommt trotzdem
    kaputt = tmp_path / "datei"
    kaputt.write_text("ich bin keine richtung", encoding="utf-8")
    monkeypatch.setenv("GENUS_PLANER_ZAEHLWERK", str(kaputt / "unmoeglich.jsonl"))
    _hierarchie(conn)
    r = werkzeuge_auskunft.relate_geplant(conn, "Hund", "Tier")
    assert r["verdict"] == "yes"
    assert zaehlwerk.stand() == {}   # auch das Lesen bleibt still


def test_stand_liest_robust_ueber_kaputte_zeilen(tmp_path, monkeypatch):
    pfad = _zaehlwerk_datei(tmp_path, monkeypatch)
    pfad.write_text(
        json.dumps({"absicht": "beziehung", "ereignis": "treffer"}) + "\n"
        + "das ist kein json\n"
        + json.dumps({"absicht": "beziehung", "ereignis": "treffer"}) + "\n",
        encoding="utf-8")
    assert zaehlwerk.stand() == {"beziehung:treffer": 2}
