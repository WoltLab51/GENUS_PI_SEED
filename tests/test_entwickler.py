"""Verträge des allgemeinen, beaufsichtigten GENUS-Entwicklerloops."""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from genus import cli, entwickler


ROOT = Path(__file__).resolve().parents[1]


def _spec(path: str = "docs/NOW.md", *, history_path=None):
    return entwickler.make_change_spec(
        "Eine kleine, geprüfte Verbesserung", allowed_files=[path],
        history_path=history_path,
    )


def _patch(path: str = "docs/NOW.md", line: str = "+Neue geprüfte Zeile.") -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1,1 +1,2 @@\n"
        " # GENUS\n"
        f"{line}\n"
    )


def test_stand_kennt_faehigkeiten_und_harte_autonomiegrenzen():
    value = entwickler.stand()
    assert value["commit"] == entwickler.git_commit(ROOT)
    assert value["summary"]["modules"] >= 100
    assert value["capabilities"]["evidence_diagnosis"] is True
    assert value["capabilities"]["automatic_commit"] is False
    assert value["capabilities"]["automatic_merge"] is False
    assert value["capabilities"]["automatic_deploy"] is False


def test_diagnose_ist_deterministisch_evidenzgebunden_und_behauptet_keine_root_cause():
    symptom = "GENUS Antworten klingen unnatürlich und der Säugetier-Pfad ist falsch"
    first = entwickler.diagnose(symptom)
    second = entwickler.diagnose(symptom)
    assert first == second
    assert first["evidence"] and first["suspected_modules"]
    assert any(item["file"] == "genus/antwort.py" for item in first["evidence"])
    assert "keine bewiesene Root Cause" in first["claim"]
    assert first["diagnosis_sha256"] == second["diagnosis_sha256"]


def test_change_spec_verweigert_manipulierte_oder_veraltete_diagnose():
    diagnosis = entwickler.diagnose("Antwort natürlich formulieren")
    diagnosis["symptom"] = "nachträglich verändertes Symptom"
    try:
        entwickler.make_change_spec(
            "Antwort verbessern", diagnosis=diagnosis, allowed_files=["genus/antwort.py"],
        )
    except ValueError as exc:
        assert "Diagnose-Hash stimmt nicht" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Manipulierte Diagnose wurde akzeptiert")


def test_spec_ist_risikogestuft_begrenzt_und_verbietet_aussenwirkung():
    diagnosis = entwickler.diagnose("Antwort natürlich formulieren")
    spec = entwickler.make_change_spec(
        "Antwortplan natürlicher aussprechen", diagnosis=diagnosis,
        allowed_files=["genus/antwort.py", "tests/test_antwort.py"],
        required_tests=["tests/test_antwort.py"],
    )
    assert entwickler.validate_spec(spec) == []
    assert spec["risk"] == "medium"
    assert {"ruff", "pytest_targeted", "kartografie", "alltagsprobe"} <= set(spec["gates"])
    assert spec["draft_policy"] == {
        "external_model_may_propose": True,
        "may_commit": False, "may_merge": False, "may_push": False, "may_deploy": False,
    }
    assert len(spec["spec_sha256"]) == 64


def test_critical_scope_bleibt_vom_externen_coder_geschlossen():
    spec = _spec("genus/ledger.py")
    assert spec["risk"] == "critical"
    assert spec["draft_policy"]["external_model_may_propose"] is False
    assert {"pytest_full", "security_review"} <= set(spec["gates"])
    assert entwickler.validate_spec(spec) == []


def test_spec_laesst_sich_nicht_durch_entfernte_pflicht_gates_abschwaechen():
    spec = _spec("genus/antwort.py")
    spec["gates"].remove("kartografie")
    spec["spec_sha256"] = entwickler._sha(spec, "spec_sha256")
    assert "Gates passen nicht zu Scope, Risiko und Prüffällen" in entwickler.validate_spec(spec)


def test_unsichere_und_geheime_pfade_werden_verweigert():
    for path in ("../x.py", ".git/config", ".venv/x.py", "/tmp/x.py", "github_models_token"):
        try:
            _spec(path)
        except ValueError as exc:
            assert "Pfad" in str(exc)
        else:  # pragma: no cover - Schutzbehauptung
            raise AssertionError(path)


def test_freigabe_ist_an_spec_und_basiscommit_gebunden():
    spec = _spec()
    approval = entwickler.approve(spec, "ronny", approved_at="2026-07-15T17:30:00Z")
    assert entwickler.validate_approval(spec, approval) == []
    changed = dict(spec, goal="anderes Ziel")
    errors = entwickler.validate_approval(changed, approval)
    assert "Spec-Hash stimmt nicht" in errors
    assert "Freigabe gehört zu einer anderen Spezifikation" not in errors
    changed["spec_sha256"] = "0" * 64
    assert "Freigabe gehört zu einer anderen Spezifikation" in entwickler.validate_approval(
        changed, approval,
    )


def test_patchpruefung_akzeptiert_scope_und_blockiert_scope_escape():
    spec = _spec()
    good = entwickler.inspect_patch(spec, _patch())
    assert good["ok"] and good["paths"] == ["docs/NOW.md"]
    outside = entwickler.inspect_patch(spec, _patch("README.md"))
    assert not outside["ok"] and any("außerhalb" in error for error in outside["errors"])


def test_patchpruefung_blockiert_secrets_loeschungen_und_kern_netzwirkung():
    docs_spec = _spec()
    secret = entwickler.inspect_patch(docs_spec, _patch(line="+token = 'ghp_abcdefghijklmnopqrstuvwxyz1234'"))
    assert not secret["ok"] and "Patch enthält ein mögliches Secret" in secret["errors"]
    deletion = _patch().replace("@@ -1,1 +1,2 @@", "deleted file mode 100644\n@@ -1,1 +0,0 @@")
    assert not entwickler.inspect_patch(docs_spec, deletion)["ok"]
    core_spec = _spec("genus/antwort.py")
    escape = entwickler.inspect_patch(core_spec, _patch("genus/antwort.py", "+import subprocess"))
    assert not escape["ok"] and any("Kernpfad" in error for error in escape["errors"])


def test_patchpruefung_blockiert_gefaelschte_header_und_dateimoduswechsel():
    spec = _spec()
    forged = _patch().replace("--- a/docs/NOW.md", "--- a/README.md")
    assert not entwickler.inspect_patch(spec, forged)["ok"]
    mode_change = _patch().replace(
        "--- a/docs/NOW.md", "old mode 100644\nnew mode 100755\n--- a/docs/NOW.md",
    )
    assert not entwickler.inspect_patch(spec, mode_change)["ok"]
    symlink = _patch().replace(
        "--- a/docs/NOW.md", "new file mode 120000\n--- /dev/null",
    )
    assert not entwickler.inspect_patch(spec, symlink)["ok"]


def test_deterministisch_generierte_kartografie_zaehlt_nicht_gegen_modellbudget():
    spec = _spec("genus/antwort.py")
    generated = "docs/generated/GENUS_KARTOGRAFIE.json"
    patch = _patch("genus/antwort.py") + (
        f"diff --git a/{generated} b/{generated}\n--- a/{generated}\n+++ b/{generated}\n"
        "@@ -1,1 +1,501 @@\n {}\n" + "".join(f"+generated-{i}\n" for i in range(500))
    )
    blocked = entwickler.inspect_patch(spec, patch)
    assert not blocked["ok"] and any("außerhalb" in error for error in blocked["errors"])
    final = entwickler.inspect_patch(spec, patch, allow_generated=True)
    assert final["ok"] and final["scoped_changed_lines"] == 1


def test_menschliches_ergebnis_kann_folgescope_nur_verschaerfen(tmp_path):
    history = tmp_path / "outcomes.jsonl"
    initial = _spec(history_path=history)
    approval = entwickler.approve(initial, "ronny", approved_at="2026-07-15T17:30:00Z")
    entwickler.record_outcome(
        initial, approval, outcome="runtime_regression", reason="runtime", reviewer="ronny",
        path=history, recorded_at="2026-07-15T18:00:00Z",
    )
    next_spec = _spec(history_path=history)
    assert initial["risk"] == "low" and next_spec["risk"] == "medium"
    assert next_spec["learned_caution"] == ["docs/NOW.md"]
    assert "runtime_observation" in next_spec["gates"]
    summary = entwickler.outcome_summary(history)
    assert summary["by_outcome"] == {"runtime_regression": 1}
    assert "never widen permissions" in summary["autonomy_effect"]


def test_entwickler_cli_status_diagnose_plan_und_freigabe(tmp_path):
    runner = CliRunner()
    status = runner.invoke(cli.main, ["entwickler", "stand"])
    assert status.exit_code == 0 and "Commit/Merge/Push/Deploy: nein" in status.output
    diagnosis_path = tmp_path / "diagnosis.json"
    diagnosis = runner.invoke(
        cli.main, ["entwickler", "diagnose", "Antwort klingt mechanisch", "--output", str(diagnosis_path)],
    )
    assert diagnosis.exit_code == 0, diagnosis.output
    spec_path = tmp_path / "spec.json"
    plan = runner.invoke(
        cli.main,
        ["entwickler", "plan", "Antwort verbessern", "--diagnose", str(diagnosis_path),
         "--allow", "genus/antwort.py", "--test", "tests/test_antwort.py",
         "--output", str(spec_path)],
    )
    assert plan.exit_code == 0, plan.output
    approval_path = tmp_path / "approval.json"
    approval = runner.invoke(
        cli.main, ["entwickler", "genehmige", str(spec_path), "--reviewer", "ronny",
                   "--output", str(approval_path)],
    )
    assert approval.exit_code == 0 and "draft_only" in approval.output
    assert entwickler.validate_approval(
        json.loads(spec_path.read_text(encoding="utf-8")),
        json.loads(approval_path.read_text(encoding="utf-8")),
    ) == []
