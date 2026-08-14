"""Die Verwandtschafts-Weberei (deploy/verwandtschaft.py): die reine GRAPH-Logik — Kandidaten-
Kreis + Bedeutungs-Fingerabdruck — deterministisch gegen ein geseedetes Mini-Netz. Der eigentliche
Wiege-Lauf braucht die embed-venv und wird live am Pi geprüft; hier nur, dass GENUS die richtigen
Nachbarn zum Wiegen AUSWÄHLT und dass die --derivation-CLI das Gewicht wirklich speichert."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import sys
from threading import Barrier
from pathlib import Path

from click.testing import CliRunner

from genus import cli, integrity, ledger, projection, reactors, verwandt
from genus.db import init_schema

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
import verwandtschaft  # noqa: E402


def _fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _provision_current(path: Path) -> None:
    conn = sqlite3.connect(path)
    init_schema(conn)
    conn.close()


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
    netz = verwandtschaft.lade_netz(_tier_taxonomie(_fresh()))
    assert verwandtschaft.concept_desc(netz, "Q144") == "Hund · Säugetier"
    assert verwandtschaft.concept_desc(netz, "Qxxx") is None      # kein deutsches Label


def test_kandidaten_sind_geschwister_und_cousins():
    netz = verwandtschaft.lade_netz(_tier_taxonomie(_fresh()))
    kand = set(verwandtschaft.kandidaten(netz, "Q144"))
    assert "Q18498" in kand and "Q146" in kand        # Geschwister unter Säugetier
    assert "Q123599" in kand                          # Cousin (über Großeltern Tier)
    assert "Q144" not in kand                         # nie sich selbst


def test_kandidaten_ohne_eltern_ist_leer():
    conn = _fresh()
    reactors.observe_relation(conn, "Solo@de", "expresses", "Qsolo", "wikidata")
    assert verwandtschaft.kandidaten(verwandtschaft.lade_netz(conn), "Qsolo") == []


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
    kand = set(verwandtschaft.kandidaten(verwandtschaft.lade_netz(conn), "Qmesser"))
    assert "Qdolch" in kand                       # aus der engen „Stichwaffe"
    assert not any(k.startswith("Qkrimskram") for k in kand)   # NICHT aus dem breiten „Artefakt"


def test_konzepte_von_wort():
    conn = _tier_taxonomie(_fresh())
    assert verwandtschaft._konzepte_von(conn, "Hund") == ["Q144"]


def test_verwandt_pair_has_one_canonical_orientation():
    assert verwandtschaft.kanonisches_paar("Q9", "Q1") == ("Q1", "Q9")
    assert verwandtschaft.kanonisches_paar("Q1", "Q9") == ("Q1", "Q9")


def test_relate_bulk_schreibt_viele_kanten_in_einem_lauf(tmp_path, monkeypatch):
    # der Nachtlauf-Schreibweg: JSONL auf stdin -> viele gewichtete Kanten in EINEM Prozess
    db = tmp_path / "genus.sqlite3"
    _provision_current(db)
    monkeypatch.setenv("GENUS_DB_PATH", str(db))
    jsonl = "\n".join([
        '{"subject":"Q144","predicate":"verwandt","object":"Q18498","source":"model:embedder","derivation":"cos=0.71"}',
        '{"subject":"Q144","predicate":"verwandt","object":"Q146","source":"model:embedder","derivation":"cos=0.66"}',
        'kaputte zeile',                       # muss übersprungen werden, nicht den Lauf kippen
        '{"subject":"Q144","predicate":"verwandt","object":"Q123599","source":"model:embedder","derivation":"cos=0.41"}',
    ])
    r = CliRunner().invoke(cli.main, ["relate-bulk", "--chunk", "2"], input=jsonl)
    assert r.exit_code == 0
    assert "3 Kante(n)" in r.output and "1 Zeile(n) übersprungen" in r.output
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    for w, q in [("Hund", "Q144"), ("Wolf", "Q18498"), ("Katze", "Q146"), ("Goldfisch", "Q123599")]:
        reactors.observe_relation(conn, f"{w}@de", "expresses", q, "wikidata")
    res = verwandt.verwandte(conn, "Hund")
    assert [v["name"] for v in res["verwandte"]] == ["Wolf", "Katze", "Goldfisch"]   # nach Gewicht

    events_before = conn.execute(
        "SELECT COUNT(*) FROM event_log WHERE event_type='relation_asserted'"
    ).fetchone()[0]
    again = CliRunner().invoke(cli.main, ["relate-bulk", "--chunk", "2"], input=jsonl)
    events_after = conn.execute(
        "SELECT COUNT(*) FROM event_log WHERE event_type='relation_asserted'"
    ).fetchone()[0]
    assert again.exit_code == 0
    assert "0 Kante(n) geschrieben" in again.output
    assert "3 unverändert" in again.output
    assert events_after == events_before


def test_relate_bulk_deduplicates_inside_one_open_chunk(tmp_path, monkeypatch):
    db = tmp_path / "genus.sqlite3"
    _provision_current(db)
    monkeypatch.setenv("GENUS_DB_PATH", str(db))
    edge = (
        '{"subject":"Q9","predicate":"verwandt","object":"Q1",'
        '"source":"model:embedder","derivation":"cos=0.7100"}'
    )

    result = CliRunner().invoke(
        cli.main, ["relate-bulk", "--chunk", "50"], input=f"{edge}\n{edge}\n"
    )

    assert result.exit_code == 0
    assert "1 Kante(n) geschrieben, 1 unverändert" in result.output
    conn = sqlite3.connect(str(db))
    assert conn.execute(
        "SELECT COUNT(*) FROM event_log WHERE event_type='relation_asserted'"
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT subject, object FROM relation_projection WHERE predicate='verwandt'"
    ).fetchone() == ("Q1", "Q9")


def test_bad_bulk_row_does_not_rollback_prior_valid_rows(tmp_path, monkeypatch):
    db = tmp_path / "genus.sqlite3"
    _provision_current(db)
    monkeypatch.setenv("GENUS_DB_PATH", str(db))
    lines = [
        '{"subject":"A","predicate":"is_a","object":"B"}',
        '{"subject":"missing-object","predicate":"is_a"}',
        '{"subject":["bad"],"predicate":"is_a","object":"ignored"}',
        '{"subject":"C","predicate":"is_a","object":"D"}',
    ]

    result = CliRunner().invoke(
        cli.main, ["relate-bulk", "--chunk", "50"], input="\n".join(lines)
    )

    assert result.exit_code == 0
    assert "2 Kante(n) geschrieben, 2 Zeile(n) übersprungen" in result.output
    conn = sqlite3.connect(str(db))
    assert conn.execute(
        "SELECT COUNT(*) FROM event_log WHERE event_type='relation_asserted'"
    ).fetchone()[0] == 2


def test_bulk_writer_returns_actual_written_count(monkeypatch, capsys):
    completed = verwandtschaft.subprocess.CompletedProcess(
        args=["genus", "relate-bulk"], returncode=0,
        stdout=b"[REL-BULK] 2 Kante(n) geschrieben, 8 unveraendert\n",
    )
    monkeypatch.setattr(verwandtschaft.subprocess, "run", lambda *args, **kwargs: completed)

    assert verwandtschaft._schreibe_gebuendelt([{"subject": "Q1"}] * 10) == 2
    assert "2 Kante(n) geschrieben" in capsys.readouterr().out


def test_relate_cli_reports_canonical_noop_truthfully(tmp_path, monkeypatch):
    db = tmp_path / "genus.sqlite3"
    _provision_current(db)
    monkeypatch.setenv("GENUS_DB_PATH", str(db))
    args = [
        "relate", "Q9", "verwandt", "Q1", "--source", "model:embedder",
        "--derivation", "cos=0.7100",
    ]

    first = CliRunner().invoke(cli.main, args)
    second = CliRunner().invoke(cli.main, args)

    assert first.exit_code == second.exit_code == 0
    assert "[REL] Q1 -[verwandt]-> Q9" in first.output
    assert "[REL] unchanged Q1 -[verwandt]-> Q9" in second.output
    conn = sqlite3.connect(str(db))
    assert conn.execute(
        "SELECT COUNT(*) FROM event_log WHERE event_type='relation_asserted'"
    ).fetchone()[0] == 1


def test_relation_weight_change_is_a_real_event_and_updates_projection():
    conn = _fresh()
    first = reactors.observe_relation(
        conn, "Q144", "verwandt", "Q18498", "model:embedder", derivation="cos=0.7100"
    )
    same = reactors.observe_relation(
        conn, "Q144", "verwandt", "Q18498", "model:embedder", derivation="cos=0.7100"
    )
    changed = reactors.observe_relation(
        conn, "Q144", "verwandt", "Q18498", "model:embedder", derivation="cos=0.7300"
    )

    assert first["event_id"] is not None
    assert same == {"event_id": None, "events": [], "unchanged": True}
    assert changed["event_id"] is not None
    assert conn.execute(
        "SELECT derivation FROM relation_projection WHERE subject='Q144' "
        "AND predicate='verwandt' AND object='Q18498'"
    ).fetchone()[0] == "cos=0.7300"
    assert conn.execute(
        "SELECT COUNT(*) FROM event_log WHERE event_type='relation_asserted'"
    ).fetchone()[0] == 2
    assert integrity.check(conn)["ok"] is True


def test_core_canonicalizes_similarity_and_recognizes_the_reverse_order():
    conn = _fresh()
    first = reactors.observe_relation(
        conn, "Q9", "verwandt", "Q1", "model:embedder", derivation="cos=0.7100"
    )
    reverse = reactors.observe_relation(
        conn, "Q1", "verwandt", "Q9", "model:embedder", derivation="cos=0.7100"
    )

    assert first["unchanged"] is False
    assert reverse["unchanged"] is True
    row = conn.execute(
        "SELECT subject, object FROM relation_projection WHERE predicate='verwandt'"
    ).fetchone()
    assert tuple(row) == ("Q1", "Q9")
    assert conn.execute(
        "SELECT COUNT(*) FROM event_log WHERE event_type='relation_asserted'"
    ).fetchone()[0] == 1


def test_reverse_spelling_retracts_the_canonical_similarity():
    conn = _fresh()
    reactors.observe_relation(
        conn, "Q9", "verwandt", "Q1", "model:embedder", derivation="cos=0.7100"
    )

    reactors.retract_relation(conn, "Q9", "verwandt", "Q1", "model:embedder")

    assert conn.execute(
        "SELECT COUNT(*) FROM relation_projection WHERE predicate='verwandt'"
    ).fetchone()[0] == 0
    assert integrity.check(conn)["ok"] is True


def test_legacy_reverse_similarity_is_seen_as_unchanged():
    conn = _fresh()
    payload = {
        "subject": "Q9", "predicate": "verwandt", "object": "Q1",
        "source": "model:embedder", "derivation": "cos=0.7100",
    }
    event_id = ledger.append(conn, "relation_asserted", payload)
    payload["_event_created_at"] = ledger.event_created_at(conn, event_id)
    projection.apply_relation_asserted(conn, payload)
    conn.commit()

    result = reactors.observe_relation(
        conn, "Q1", "verwandt", "Q9", "model:embedder", derivation="cos=0.7100"
    )

    assert result["unchanged"] is True
    assert conn.execute(
        "SELECT COUNT(*) FROM event_log WHERE event_type='relation_asserted'"
    ).fetchone()[0] == 1


def test_changed_weight_migrates_a_legacy_reverse_projection_and_replays():
    conn = _fresh()
    old_payload = {
        "subject": "Q9", "predicate": "verwandt", "object": "Q1",
        "source": "model:embedder", "derivation": "cos=0.7100",
    }
    old_event = ledger.append(conn, "relation_asserted", old_payload)
    created_at = ledger.event_created_at(conn, old_event)
    # Reproduce a projection created by the pre-canonical release while keeping the
    # authentic historical event that a fresh replay will normalize.
    conn.execute(
        "INSERT INTO relation_projection "
        "(subject, predicate, object, source, derivation, created_at, last_updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("Q9", "verwandt", "Q1", "model:embedder", "cos=0.7100", created_at, created_at),
    )
    conn.commit()

    reactors.observe_relation(
        conn, "Q1", "verwandt", "Q9", "model:embedder", derivation="cos=0.7300"
    )

    rows = conn.execute(
        "SELECT subject, object, derivation FROM relation_projection "
        "WHERE predicate='verwandt'"
    ).fetchall()
    assert [tuple(row) for row in rows] == [("Q1", "Q9", "cos=0.7300")]
    assert integrity.check(conn)["ok"] is True


def test_changed_weight_merges_both_legacy_orientations_replay_stably():
    conn = _fresh()
    for subject, object_ in (("Q9", "Q1"), ("Q1", "Q9")):
        payload = {
            "subject": subject, "predicate": "verwandt", "object": object_,
            "source": "model:embedder", "derivation": "cos=0.7100",
        }
        event_id = ledger.append(conn, "relation_asserted", payload)
        created_at = ledger.event_created_at(conn, event_id)
        conn.execute(
            "INSERT INTO relation_projection "
            "(subject, predicate, object, source, derivation, created_at, last_updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (subject, "verwandt", object_, "model:embedder", "cos=0.7100",
             created_at, created_at),
        )
    conn.commit()

    reactors.observe_relation(
        conn, "Q9", "verwandt", "Q1", "model:embedder", derivation="cos=0.7300"
    )

    rows = conn.execute(
        "SELECT id, subject, object, derivation FROM relation_projection "
        "WHERE predicate='verwandt'"
    ).fetchall()
    assert [tuple(row) for row in rows] == [(1, "Q1", "Q9", "cos=0.7300")]
    assert integrity.check(conn)["ok"] is True


def test_concurrent_similarity_materializers_append_once(tmp_path):
    db = tmp_path / "genus.sqlite3"
    initial = sqlite3.connect(str(db))
    init_schema(initial)
    initial.close()
    ready = Barrier(2)

    def write_once() -> bool:
        conn = sqlite3.connect(str(db), timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            ready.wait()
            return reactors.observe_relation(
                conn, "Q9", "verwandt", "Q1", "model:embedder",
                derivation="cos=0.7100",
            )["unchanged"]
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: write_once(), range(2)))

    assert sorted(results) == [False, True]
    check = sqlite3.connect(str(db))
    assert check.execute(
        "SELECT COUNT(*) FROM event_log WHERE event_type='relation_asserted'"
    ).fetchone()[0] == 1


def test_countable_relation_stream_is_never_deduplicated():
    conn = _fresh()
    first = reactors.observe_relation(
        conn, "material:buch", "gelesen", "bedarf:verstehen", "muster",
        derivation="source:muster",
    )
    second = reactors.observe_relation(
        conn, "material:buch", "gelesen", "bedarf:verstehen", "muster",
        derivation="source:muster",
    )

    assert first["event_id"] is not None
    assert second["event_id"] is not None
    assert conn.execute(
        "SELECT COUNT(*) FROM event_log WHERE event_type='relation_asserted'"
    ).fetchone()[0] == 2


def test_directed_reverse_relations_remain_two_distinct_edges():
    conn = _fresh()
    reactors.observe_relation(conn, "A", "causes", "B", "test")
    reactors.observe_relation(conn, "B", "causes", "A", "test")

    assert conn.execute(
        "SELECT COUNT(*) FROM relation_projection WHERE predicate='causes'"
    ).fetchone()[0] == 2


def test_observe_relation_commit_false_wartet_auf_den_aufrufer():
    conn = _fresh()
    reactors.observe_relation(conn, "Q144", "verwandt", "Q18498", "model:embedder",
                              derivation="cos=0.71", commit=False)
    # noch nicht committet -> ein zweiter Reader sieht die Kante nicht, der eigene schon (gleiche tx)
    assert conn.execute("SELECT COUNT(*) FROM relation_projection WHERE predicate='verwandt'"
                        ).fetchone()[0] == 1
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM relation_projection WHERE predicate='verwandt'"
                        ).fetchone()[0] == 1


def test_relate_cli_speichert_das_gewicht_in_der_herleitung(tmp_path, monkeypatch):
    # der Schreibweg der Weberei: `genus relate ... --derivation cos=..` muss das Gewicht ablegen,
    # und das Lese-Ende (verwandt) muss es zurücklesen -- der End-zu-End-Vertrag der Kante
    db = tmp_path / "genus.sqlite3"
    _provision_current(db)
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
