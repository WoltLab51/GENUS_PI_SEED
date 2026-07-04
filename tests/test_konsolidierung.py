"""Nacht-Konsolidierung + Morgen-Nachricht (docs/GENUS_GEDAECHTNIS.md Punkt ④, Ronnys
Entscheidungen 2026-07-04): Themen deterministisch, Episoden gedeckelt (model:nacht),
die eine Nachricht warm und nativ — nie kryptisch, nie leer."""
from genus import konsolidierung, proposals, reactors, sources, ziele


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


def test_morgen_nachricht_nennt_wartende_freigaben(conn):
    proposals.record_proposal_created_event(
        conn, proposal_id=proposals.next_proposal_id(conn),
        proposal_type="ResourceProposal", claim_key="test", claim_value="x",
        source_belief=None, source_event=1,
        payload={"description": "t", "action_required": True, "review_recommended": True},
    )
    text = konsolidierung.morgen_nachricht(conn, None)
    assert "Freigabe" in text and "Proposal #" in text


def test_leerer_morgen_ist_nie_leer_sondern_erzaehlt_das_gelernte(conn):
    # Ronnys Entscheidung: kein Schweigen -- wenn nichts wartet, erzaehlt GENUS,
    # was der Nacht-Lerner zuletzt gelernt hat.
    reactors.observe_relation(conn, "Fernweh@de", "expresses", "Q_fernweh", "wikidata")
    reactors.observe_relation(conn, "Fernweh@de", "primary_gloss",
                              "Sehnsucht nach der Ferne", "dbnary")
    text = konsolidierung.morgen_nachricht(conn, None)
    assert "„Fernweh“" in text and "Sehnsucht nach der Ferne" in text
    assert text.startswith("Guten Morgen, Ronny!") and "guten Start" in text


def test_voellig_frischer_kern_bleibt_trotzdem_warm(conn):
    text = konsolidierung.morgen_nachricht(conn, None)
    assert text.startswith("Guten Morgen, Ronny!") and "guten Start" in text
