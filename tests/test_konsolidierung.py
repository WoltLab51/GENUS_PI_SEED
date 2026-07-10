"""Nacht-Konsolidierung + Morgen-Nachricht (docs/GENUS_GEDAECHTNIS.md Punkt ④, Ronnys
Entscheidungen 2026-07-04): Themen deterministisch, Episoden gedeckelt (model:nacht),
die eine Nachricht warm und nativ — nie kryptisch, nie leer."""
from genus import inquiries, konsolidierung, proposals, reactors, sources, ziele


def _zug(frage: str) -> dict:
    return {"ts": "2026-07-04T10:00:00Z", "question": frage, "answer": "…", "gelesen": []}


def test_konsolidierung_findet_themen_und_merkt_gedeckelt(conn):
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Q144", "label", "Hund@de", "wikidata")
    zuege = [_zug("Was ist ein Hund?"), _zug("Bellt ein Hund nachts?"),
             _zug("Wie wird das Wetter?")]
    bericht = konsolidierung.konsolidiere(conn, zuege)
    assert bericht["zuege"] == 3
    assert [t["konzept"] for t in bericht["themen"]] == ["Q144"]   # 2x Hund = Thema
    assert bericht["themen"][0]["anzahl"] == 2
    # die still gemerkte Episode traegt die gedeckelte Nacht-Quelle -- korrigierbar
    kanten = sources.relations(conn, predicate="inhalt")
    nacht = [k for k in kanten if k["source"] == konsolidierung.NACHT_QUELLE]
    assert len(nacht) == 1 and "Hund" in nacht[0]["object"]


def test_ein_einzelnes_vorkommen_ist_kein_thema(conn):
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    bericht = konsolidierung.konsolidiere(conn, [_zug("Was ist ein Hund?")])
    assert bericht["themen"] == [] and bericht["episoden"] == []


def test_warum_folgen_werden_gezaehlt(conn):
    bericht = konsolidierung.konsolidiere(conn, [_zug("Was ist ein Hund?"), _zug("warum?")])
    assert bericht["warum_folgen"] == 1


def test_morgen_nachricht_ist_warm_und_nennt_themen(conn):
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    bericht = {"themen": [{"konzept": "Q144", "label": "Hund", "anzahl": 3}],
               "warum_folgen": 0, "episoden": [], "zuege": 5}
    text = konsolidierung.morgen_nachricht(conn, bericht)
    assert text.startswith("Guten Morgen, Ronny!")
    assert "„Hund“" in text and "still gemerkt" in text
    assert "guten Start" in text
    # nativ, nie kryptisch: keine internen Knoten-Namen im Klartext
    assert "Q144" not in text and "faehigkeit:" not in text


def _op_proposal(conn, claim_key, claim_value="unstable"):
    proposals.record_proposal_created_event(
        conn, proposal_id=proposals.next_proposal_id(conn),
        proposal_type="OperationProposal", claim_key=claim_key, claim_value=claim_value,
        source_belief=None, source_event=1,
        payload={"description": "op", "action_required": False, "review_recommended": True})


def test_morgen_bleibt_warm_ohne_vorschlaege(conn):
    # Ronny 2026-07-08: „der Morgengruß soll ein schöner Gruß sein" -- Vorschläge und offene Fragen
    # wandern NICHT mehr in den Gruß, sie kommen proaktiv (genus/gedanke.py). Der Gruß bleibt warm.
    proposals.record_proposal_created_event(
        conn, proposal_id=proposals.next_proposal_id(conn),
        proposal_type="ExperienceProposal", claim_key="verstehen.weltfrage",
        claim_value="verstehens_luecke", source_belief=None, source_event=1,
        payload={"description": "Darf ich das priorisieren?",
                 "action_required": True, "review_recommended": True})
    text = konsolidierung.morgen_nachricht(conn, None)
    assert text.startswith("Guten Morgen, Ronny")
    assert "Vorschlag #" not in text and "offene Fragen" not in text


def test_morgen_nachricht_warnt_bei_ueberfaelliger_ungesendeter_hand(conn):
    # Herzschlag-Waechter ueber den UNABHAENGIGEN Melde-Kanal (die Morgen-Nachricht laeuft ueber
    # morgen_push.sh, NICHT ueber den Sende-Tick): steht der Sender still, erfaehrt Ronny es trotzdem
    from genus import hand
    hid = hand.vorschlagen(conn, "nachricht", "laengst faellig",
                           faellig_um="2020-01-01T00:00:00")["hand_id"]
    hand.bestaetigen(conn, hid)
    text = konsolidierung.morgen_nachricht(conn, None, jetzt_iso="2020-01-01T12:00:00")
    assert "überfällig" in text and "noch nicht gesendet" in text


def test_morgen_nachricht_schweigt_im_normalen_sendefenster(conn):
    # eine gerade eben faellige Hand (unter der Schwelle) ist KEIN Stillstand -> keine Warnung
    from genus import hand
    hid = hand.vorschlagen(conn, "nachricht", "gleich",
                           faellig_um="2020-01-01T12:00:00")["hand_id"]
    hand.bestaetigen(conn, hid)
    text = konsolidierung.morgen_nachricht(conn, None, jetzt_iso="2020-01-01T12:01:00")
    assert "überfällig" not in text


def test_triagiere_proposals_trennt_nach_action_required():
    dringend, betrieb = konsolidierung.triagiere_proposals([
        {"claim_key": "a", "payload": '{"action_required": true}'},
        {"claim_key": "system.network", "payload": '{"action_required": false}'},
        {"claim_key": "system.network", "payload": "kaputtes json"},   # robust -> Betrieb
    ])
    assert len(dringend) == 1 and len(betrieb) == 2
    assert konsolidierung.betrieb_zeile(betrieb) == (
        "Fürs Protokoll (nichts, was du tun musst): das Netzwerk war zweimal instabil.")


def test_proposal_payload_robust_gegen_nicht_dict_json():
    # Review-Fund: gültiges, aber NICHT-Objekt-JSON (null/Zahl/Liste) darf nicht crashen ->
    # als leeres Dict behandelt, also automatisch Betrieb/nicht-dringend
    for roh in ("null", "5", "[1,2]", '"x"', "true", "kaputt", None, ""):
        assert konsolidierung._proposal_payload({"payload": roh}) == {}
    dringend, betrieb = konsolidierung.triagiere_proposals(
        [{"claim_key": "system.network", "payload": "null"}])   # kein AttributeError
    assert not dringend and len(betrieb) == 1


def test_betrieb_zeile_leakt_keinen_rohen_key_und_crasht_nicht_bei_klammern():
    # Review-Fund 2+3: ein unbekannter Claim wird generisch gezählt (kein roher Knoten-Name im
    # Klartext) UND ein Key mit Format-Klammern crasht nicht (kein .format auf Daten)
    zeile = konsolidierung.betrieb_zeile([
        {"claim_key": "system.activity"}, {"claim_key": "metric{0}"}])
    assert "system.activity" not in zeile and "metric{0}" not in zeile
    assert "es gab 2 weitere Betriebs-Hinweise" in zeile
    # bekannt + unbekannt gemischt: bekannt benannt, unbekannt generisch angehängt
    gemischt = konsolidierung.betrieb_zeile([
        {"claim_key": "system.network"}, {"claim_key": "system.activity"}])
    assert "das Netzwerk war einmal instabil" in gemischt
    assert "einen weiteren Betriebs-Hinweis" in gemischt and "system.activity" not in gemischt


def test_morgen_briefing_webt_wetter_und_schlagzeile(conn, tmp_path, monkeypatch):
    # P4-Weave: frisches Wetter + oberste Schlagzeile beilaeufig in den Morgen-Gruss
    import json
    import time

    from genus import sensor
    reactors.observe_weather_reading(conn, sensor.weather_reading(16.0, "open-meteo"))
    pfad = tmp_path / "news.json"
    pfad.write_text(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "quelle": "Tagesschau",
                                "schlagzeilen": [{"titel": "Wichtige Nachricht heute"}]}),
                    encoding="utf-8")
    monkeypatch.setenv("GENUS_NEWS_PUFFER", str(pfad))
    text = konsolidierung.morgen_nachricht(conn, None)
    assert "Draußen ist es" in text and "16,0 °C" in text
    assert "In den Nachrichten:" in text and "Wichtige Nachricht heute" in text


def test_leerer_morgen_ist_nie_leer_sondern_erzaehlt_das_gelernte(conn, tmp_path, monkeypatch):
    # Ronnys Entscheidung: kein Schweigen -- wenn nichts wartet, erzaehlt GENUS,
    # was der Nacht-Lerner zuletzt gelernt hat.
    # Hermetisch: den echten Live-News-Puffer aussperren (auf dem Pi gefüllt) -- sonst
    # verdrängt eine frische Schlagzeile das gelernte Wort und der Test bricht (live gefunden).
    monkeypatch.setenv("GENUS_NEWS_PUFFER", str(tmp_path / "keine_news.json"))
    reactors.observe_relation(conn, "Fernweh@de", "expresses", "Q_fernweh", "wikidata")
    reactors.observe_relation(conn, "Fernweh@de", "primary_gloss",
                              "Sehnsucht nach der Ferne", "dbnary")
    text = konsolidierung.morgen_nachricht(conn, None)
    assert "„Fernweh“" in text and "Sehnsucht nach der Ferne" in text
    assert text.startswith("Guten Morgen, Ronny!") and "guten Start" in text


def test_voellig_frischer_kern_bleibt_trotzdem_warm(conn, tmp_path, monkeypatch):
    # dieselbe Isolation: ein völlig frischer Kern darf nicht heimlich Live-News einweben
    monkeypatch.setenv("GENUS_NEWS_PUFFER", str(tmp_path / "keine_news.json"))
    text = konsolidierung.morgen_nachricht(conn, None)
    assert text.startswith("Guten Morgen, Ronny!") and "guten Start" in text
