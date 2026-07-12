"""Die Verwandtschafts-Weberei (deploy/verwandtschaft.py): die reine GRAPH-Logik — Kandidaten-
Kreis + Bedeutungs-Fingerabdruck — deterministisch gegen ein geseedetes Mini-Netz. Der eigentliche
Wiege-Lauf braucht die embed-venv und wird live am Pi geprüft; hier nur, dass GENUS die richtigen
Nachbarn zum Wiegen AUSWÄHLT und dass die --derivation-CLI das Gewicht wirklich speichert."""
import sqlite3
import sys
from pathlib import Path

from click.testing import CliRunner

from genus import cli, reactors, verwandt
from genus.db import init_schema

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
import verwandtschaft  # noqa: E402


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _rel(conn, s, p, o):
    reactors.observe_relation(conn, s, p, o, "wikidata")


def _tier_taxonomie(conn):
    # Q_tier -> {Q_saeuger -> {Hund, Wolf, Katze}, Q_fisch -> {Goldfisch}}
    for q, w in [("Q144", "Hund"), ("Q18498", "Wolf"), ("Q146", "Katze"),
                 ("Q123599", "Goldfisch"), ("Qsaeuger", "Säugetier"), ("Qfisch", "Fisch"),
                 ("Qtier", "Tier")]:
        _rel(conn, f"{w}@de", "expresses", q)
    for kind in ("Q144", "Q18498", "Q146"):
        _rel(conn, kind, "is_a", "Qsaeuger")
    _rel(conn, "Q123599", "is_a", "Qfisch")
    _rel(conn, "Qsaeuger", "is_a", "Qtier")
    _rel(conn, "Qfisch", "is_a", "Qtier")
    return conn


def test_concept_desc_ist_label_plus_eltern():
    conn = _tier_taxonomie(_fresh())
    assert verwandtschaft.concept_desc(conn, "Q144") == "Hund · Säugetier"
    assert verwandtschaft.concept_desc(conn, "Qxxx") is None      # kein deutsches Label


def test_kandidaten_sind_geschwister_und_cousins():
    conn = _tier_taxonomie(_fresh())
    kand = set(verwandtschaft.kandidaten(conn, "Q144"))
    assert "Q18498" in kand and "Q146" in kand        # Geschwister unter Säugetier
    assert "Q123599" in kand                          # Cousin (über Großeltern Tier)
    assert "Q144" not in kand                         # nie sich selbst


def test_kandidaten_ohne_eltern_ist_leer():
    conn = _fresh()
    reactors.observe_relation(conn, "Solo@de", "expresses", "Qsolo", "wikidata")
    assert verwandtschaft.kandidaten(conn, "Qsolo") == []


def test_ueberbreite_kategorie_wird_uebersprungen(monkeypatch):
    # ein Elternteil mit zu vielen Kindern (generische Kategorie) liefert keinen Nachbarschafts-
    # Kreis -- sonst wären es Tausende Gemischtwaren statt echter Verwandter
    monkeypatch.setattr(verwandtschaft, "MAX_FANOUT", 3)
    conn = _fresh()
    reactors.observe_relation(conn, "Messer@de", "expresses", "Qmesser", "wikidata")
    reactors.observe_relation(conn, "Qmesser", "is_a", "Qartefakt", "wikidata")   # über-breit
    reactors.observe_relation(conn, "Qmesser", "is_a", "Qstichwaffe", "wikidata")  # eng
    for i in range(6):   # Qartefakt hat 6 Kinder > MAX_FANOUT 3 -> übersprungen
        reactors.observe_relation(conn, f"Qkrimskram{i}", "is_a", "Qartefakt", "wikidata")
    reactors.observe_relation(conn, "Qdolch", "is_a", "Qstichwaffe", "wikidata")   # echtes Geschwister
    kand = set(verwandtschaft.kandidaten(conn, "Qmesser"))
    assert "Qdolch" in kand                       # aus der engen „Stichwaffe"
    assert not any(k.startswith("Qkrimskram") for k in kand)   # NICHT aus dem breiten „Artefakt"


def test_konzepte_von_wort():
    conn = _tier_taxonomie(_fresh())
    assert verwandtschaft._konzepte_von(conn, "Hund") == ["Q144"]


def test_relate_cli_speichert_das_gewicht_in_der_herleitung(tmp_path, monkeypatch):
    # der Schreibweg der Weberei: `genus relate ... --derivation cos=..` muss das Gewicht ablegen,
    # und das Lese-Ende (verwandt) muss es zurücklesen -- der End-zu-End-Vertrag der Kante
    db = tmp_path / "genus.sqlite3"
    monkeypatch.setenv("GENUS_DB_PATH", str(db))
    r = CliRunner().invoke(cli.main, ["relate", "Q144", "verwandt", "Q18498",
                                      "--source", "model:embedder", "--derivation", "cos=0.71"])
    assert r.exit_code == 0
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    reactors.observe_relation(conn, "Hund@de", "expresses", "Q144", "wikidata")
    reactors.observe_relation(conn, "Wolf@de", "expresses", "Q18498", "wikidata")
    res = verwandt.verwandte(conn, "Hund")
    assert res["verwandte"] == [{"name": "Wolf", "gewicht": 0.71}]
