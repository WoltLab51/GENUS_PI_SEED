"""Die kuratierte H1-Alltagsprobe: harte Verträge statt LLM-as-judge.

Ton und Nutzen bleiben eine hashgebundene menschliche Abnahme. Diese Tests pinnen
die hermetische Ausführung, die 85 harten Verträge, den Freigabe-Verfall und die
maschinen- wie menschenlesbaren Oberflächen.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from click.testing import CliRunner

from genus import alltagsprobe, cli


ROOT = Path(__file__).resolve().parents[1]
REPORT_ARTIFACT = ROOT / "docs" / "generated" / "ANTWORTQUALITAET.md"


@pytest.fixture(scope="module")
def report() -> alltagsprobe.SuiteResult:
    return alltagsprobe.run_suite(reviews={})


def test_suite_schema_is_complete_unique_and_fail_closed():
    alltagsprobe.validate_suite()
    assert len(alltagsprobe.ALLTAGSFAELLE) == 17
    assert len({case.id for case in alltagsprobe.ALLTAGSFAELLE}) == 17
    assert set(alltagsprobe.DIMENSION_LABELS) == {
        "treue", "ehrlichkeit", "provenienz", "transparenz",
        "dialog", "komposition", "alltagsform", "datenschutz",
    }

    first, second, *rest = alltagsprobe.ALLTAGSFAELLE
    duplicate = (replace(first, id=second.id), second, *rest)
    with pytest.raises(ValueError, match="eindeutig"):
        alltagsprobe.validate_suite(duplicate)
    with pytest.raises(ValueError, match="darf nicht leer"):
        alltagsprobe.validate_suite(())


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"dimension": "gefuehl"}, "Qualitaetsdimension"),
        ({"kind": "freie_heuristik"}, "Gate-Typ"),
        ({"description": "   "}, "lesbare Beschreibung"),
    ],
)
def test_gate_schema_rejects_uncontrolled_dimensions_and_checks(overrides, message):
    values = {
        "dimension": "treue",
        "kind": "outcome",
        "expected": "answered",
        "description": "Ein klarer Vertrag.",
    }
    values.update(overrides)
    with pytest.raises(ValueError, match=message):
        alltagsprobe.Gate(**values)


def test_review_file_schema_is_exact_and_rejects_unknown_fields(tmp_path):
    valid = tmp_path / "reviews.json"
    valid.write_text(
        json.dumps({"schema": alltagsprobe.SCHEMA, "reviews": []}),
        encoding="utf-8",
    )
    assert alltagsprobe.load_reviews(valid) == {}

    invalid = tmp_path / "invalid.json"
    invalid.write_text(
        json.dumps({"schema": alltagsprobe.SCHEMA, "reviews": [], "score": 100}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exakt schema und reviews"):
        alltagsprobe.load_reviews(invalid)


def test_all_85_hard_gates_pass_without_a_model_judge(report):
    passed = sum(values["passed"] for values in report.dimensions.values())
    failed = sum(values["failed"] for values in report.dimensions.values())
    total = sum(values["total"] for values in report.dimensions.values())

    assert (passed, failed, total) == (85, 0, 85)
    assert report.hard_ok
    assert all(case.hard_ok for case in report.cases)
    assert all(values["total"] > 0 for values in report.dimensions.values())
    assert report.human_statuses == {
        "accepted": 0,
        "needs_work": 0,
        "review_stale": 0,
        "review_pending": 17,
    }


def test_suite_is_order_independent_and_content_hash_is_deterministic(report):
    reversed_report = alltagsprobe.run_suite(
        tuple(reversed(alltagsprobe.ALLTAGSFAELLE)), reviews={},
    )

    assert alltagsprobe.report_dict(reversed_report) == alltagsprobe.report_dict(report)
    assert reversed_report.content_sha256 == report.content_sha256


def _matching_review(case: alltagsprobe.ScenarioResult) -> alltagsprobe.Review:
    return alltagsprobe.Review(
        case_id=case.id,
        case_fingerprint=case.case_fingerprint,
        response_sha256=case.response_sha256,
        ton="traegt",
        nutzen="traegt",
        reviewer="ronny",
        reviewed_at="2026-07-13T12:00:00+02:00",
        note="Bewusst freigegebener Testbeleg.",
    )


def test_human_review_is_bound_to_case_and_response_hash(report):
    scenario = alltagsprobe.ALLTAGSFAELLE[0]
    review = _matching_review(report.cases[0])

    accepted = alltagsprobe.run_scenario(scenario, review)
    stale_answer = alltagsprobe.run_scenario(
        scenario, replace(review, response_sha256="0" * 64),
    )
    changed_scenario = replace(scenario, human_prompt=scenario.human_prompt + " Wirklich?")
    stale_case = alltagsprobe.run_scenario(changed_scenario, review)

    assert accepted.human_status == "accepted"
    assert stale_answer.human_status == "review_stale"
    assert stale_case.human_status == "review_stale"
    assert stale_case.response_sha256 == accepted.response_sha256
    assert stale_case.case_fingerprint != accepted.case_fingerprint


def test_probe_only_opens_in_memory_sqlite_and_never_touches_live_db(
    tmp_path, monkeypatch,
):
    live_db = tmp_path / "live-genus.sqlite3"
    live_db.write_bytes(b"LIVE-DB-CANARY")
    monkeypatch.setenv("GENUS_DB_PATH", str(live_db))
    real_connect = alltagsprobe.sqlite3.connect
    opened: list[str] = []

    def guarded_connect(database, *args, **kwargs):
        opened.append(str(database))
        assert database == ":memory:"
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(alltagsprobe.sqlite3, "connect", guarded_connect)
    result = alltagsprobe.run_scenario(alltagsprobe.ALLTAGSFAELLE[0])

    assert result.hard_ok
    assert opened == [":memory:"]
    assert live_db.read_bytes() == b"LIVE-DB-CANARY"


def _cached_cli(monkeypatch, report):
    monkeypatch.setattr(alltagsprobe, "run_suite", lambda reviews=None: report)


def test_cli_exits_two_while_human_review_is_pending(report, monkeypatch):
    _cached_cli(monkeypatch, report)
    result = CliRunner().invoke(cli.main, ["alltagsprobe"])

    assert result.exit_code == 2
    assert "harte Verträge 85/85" in result.output
    assert "menschlich akzeptiert 0/17" in result.output
    assert "[OFFEN]" in result.output


def test_cli_contracts_only_exits_zero(report, monkeypatch):
    _cached_cli(monkeypatch, report)
    result = CliRunner().invoke(cli.main, ["alltagsprobe", "--contracts-only"])

    assert result.exit_code == 0, result.output
    assert "85/85" in result.output


def test_cli_json_is_complete_machine_readable_and_green(report, monkeypatch):
    _cached_cli(monkeypatch, report)
    result = CliRunner().invoke(
        cli.main, ["alltagsprobe", "--contracts-only", "--json-output"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema"] == alltagsprobe.SCHEMA
    assert len(payload["cases"]) == 17
    assert sum(values["total"] for values in payload["dimensions"].values()) == 85
    assert payload["hard_ok"] is True


def test_cli_markdown_is_the_human_review_surface(report, monkeypatch):
    _cached_cli(monkeypatch, report)
    result = CliRunner().invoke(
        cli.main, ["alltagsprobe", "--contracts-only", "--markdown"],
    )

    assert result.exit_code == 0, result.output
    assert result.output == alltagsprobe.render_markdown(report)
    assert result.output.startswith("# GENUS Alltagsprobe · Antwortqualität v1")
    assert "## Die Fälle" in result.output
    assert "LLM" not in result.output


def test_generated_answer_quality_report_is_byte_exact(report):
    assert REPORT_ARTIFACT.exists(), (
        "Kanonisches Alltagsproben-Artefakt fehlt: " + str(REPORT_ARTIFACT)
    )
    assert REPORT_ARTIFACT.read_bytes() == alltagsprobe.render_markdown(report).encode("utf-8")
