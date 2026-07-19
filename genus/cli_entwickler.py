"""Click-Slice für den beaufsichtigten GENUS-Entwicklerloop."""
from __future__ import annotations

import json
import os
from pathlib import Path

import click

from genus import entwickler


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise click.ClickException(f"{path} enthält kein JSON-Objekt")
    return value


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _emit(value: dict, output: Path | None, prefix: str) -> None:
    if output is not None:
        _write(output, value)
        click.echo(f"[{prefix}] geschrieben: {output}")
    else:
        click.echo(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def register(main: click.Group) -> click.Group:
    @main.group("entwickler")
    def group() -> None:
        """GENUS' beaufsichtigter Selbstcoding-Loop — nie Merge oder Deploy."""

    @group.command("stand")
    @click.option("--json-output", is_flag=True, help="Vollständigen Status als JSON ausgeben.")
    def status(json_output: bool) -> None:
        """Zeigt Selbstkarte, Commit, Fähigkeiten und harte Autonomiegrenzen."""
        try:
            value = entwickler.stand()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise click.ClickException(str(exc)) from exc
        if json_output:
            click.echo(json.dumps(value, ensure_ascii=False, sort_keys=True))
            return
        summary = value["summary"]
        click.echo(
            "[ENTWICKLER] "
            f"Commit {(value['commit'] or 'unbekannt')[:12]} · Karte {value['map_sha256'][:16]} · "
            f"{summary['modules']} Module · {summary['edges']} Kanten"
        )
        click.echo("[ENTWICKLER] Entwurf: ja · Commit/Merge/Push/Deploy: nein")

    @group.command("diagnose")
    @click.argument("symptom")
    @click.option("--output", type=click.Path(path_type=Path, dir_okay=False))
    def diagnosis(symptom: str, output: Path | None) -> None:
        """Findet evidenzgebunden den wahrscheinlichen Quell- und Wirkungsraum."""
        try:
            value = entwickler.diagnose(symptom)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise click.ClickException(str(exc)) from exc
        _emit(value, output, "DIAGNOSE")

    @group.command("plan")
    @click.argument("goal")
    @click.option("--diagnose", "diagnosis_path", type=click.Path(path_type=Path, exists=True, dir_okay=False))
    @click.option("--allow", "allowed", multiple=True, help="Explizit begrenzter Repo-Pfad; wiederholbar.")
    @click.option("--test", "tests", multiple=True, help="Expliziter Testpfad unter tests/; wiederholbar.")
    @click.option("--output", required=True, type=click.Path(path_type=Path, dir_okay=False))
    def plan(goal: str, diagnosis_path: Path | None, allowed: tuple[str, ...],
             tests: tuple[str, ...], output: Path) -> None:
        """Schreibt eine risikogestufte Änderungsspezifikation; noch keine Schreibfreigabe."""
        diagnosis_value = _load(diagnosis_path) if diagnosis_path else None
        try:
            value = entwickler.make_change_spec(
                goal, diagnosis=diagnosis_value, allowed_files=allowed, required_tests=tests,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise click.ClickException(str(exc)) from exc
        _write(output, value)
        click.echo(
            f"[PLAN] {value['risk']} · {len(value['allowed_files'])} Dateien · "
            f"Spec {value['spec_sha256'][:16]} · geschrieben: {output}"
        )
        click.echo("[PLAN] Noch keine Rechte: zuerst `genus entwickler genehmige`.")

    @group.command("genehmige")
    @click.argument("spec_path", type=click.Path(path_type=Path, exists=True, dir_okay=False))
    @click.option("--reviewer", required=True, help="Menschlicher Reviewer.")
    @click.option("--output", required=True, type=click.Path(path_type=Path, dir_okay=False))
    def approve(spec_path: Path, reviewer: str, output: Path) -> None:
        """Gibt ausschließlich einen isolierten Entwurf frei — niemals Commit oder Deploy."""
        try:
            value = entwickler.approve(_load(spec_path), reviewer)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise click.ClickException(str(exc)) from exc
        _write(output, value)
        click.echo(
            f"[FREIGABE] draft_only · {value['reviewer']} · "
            f"Hash {value['approval_sha256'][:16]} · geschrieben: {output}"
        )

    @group.command("pruefe-patch")
    @click.argument("spec_path", type=click.Path(path_type=Path, exists=True, dir_okay=False))
    @click.argument("approval_path", type=click.Path(path_type=Path, exists=True, dir_okay=False))
    @click.argument("patch_path", type=click.Path(path_type=Path, exists=True, dir_okay=False))
    @click.option("--json-output", is_flag=True)
    def inspect(spec_path: Path, approval_path: Path, patch_path: Path, json_output: bool) -> None:
        """Prüft einen Entwurf hash-, scope- und budgetgebunden, ohne ihn anzuwenden."""
        spec, approval_value = _load(spec_path), _load(approval_path)
        approval_errors = entwickler.validate_approval(spec, approval_value)
        report = entwickler.inspect_patch(spec, patch_path.read_text(encoding="utf-8"))
        report["approval_errors"] = approval_errors
        report["ok"] = report["ok"] and not approval_errors
        if json_output:
            click.echo(json.dumps(report, ensure_ascii=False, sort_keys=True))
        else:
            click.echo(
                f"[PATCH] ok={report['ok']} · {len(report['paths'])} Dateien · "
                f"{report['changed_lines']} Zeilen · {report['patch_sha256'][:16]}"
            )
            for error in (*approval_errors, *report["errors"]):
                click.echo(f"[PATCH] BLOCKIERT: {error}")
        if not report["ok"]:
            raise click.exceptions.Exit(1)

    @group.command("lerne")
    @click.argument("spec_path", type=click.Path(path_type=Path, exists=True, dir_okay=False))
    @click.argument("approval_path", type=click.Path(path_type=Path, exists=True, dir_okay=False))
    @click.option("--outcome", type=click.Choice(sorted(entwickler.OUTCOMES)), required=True)
    @click.option("--reason", type=click.Choice(sorted(entwickler.REASONS)), required=True)
    @click.option("--reviewer", required=True)
    @click.option("--note", default="")
    def learn(spec_path: Path, approval_path: Path, outcome: str, reason: str,
              reviewer: str, note: str) -> None:
        """Speichert ein menschlich bestätigtes Ergebnis; es kann Rechte nur verschärfen."""
        try:
            value = entwickler.record_outcome(
                _load(spec_path), _load(approval_path), outcome=outcome, reason=reason,
                reviewer=reviewer, note=note,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(
            f"[LERNEN] {outcome}/{reason} · {value['outcome_sha256'][:16]} · "
            "Rechte bleiben unverändert"
        )

    @group.command("erfahrung")
    @click.option("--json-output", is_flag=True)
    def experience(json_output: bool) -> None:
        """Zeigt angenommene, abgelehnte und zur Laufzeit zurückgefallene Entwürfe."""
        value = entwickler.outcome_summary()
        if json_output:
            click.echo(json.dumps(value, ensure_ascii=False, sort_keys=True))
            return
        click.echo(f"[ERFAHRUNG] {value['total']} menschlich bestätigte Ergebnisse")
        for key, count in value["by_outcome"].items():
            click.echo(f"[ERFAHRUNG] {key}: {count}")
        click.echo("[ERFAHRUNG] Erfolg erweitert nie automatisch Rechte; Fehlschläge erhöhen Risiko.")

    return group
