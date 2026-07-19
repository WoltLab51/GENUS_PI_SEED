#!/usr/bin/env python3
"""Äußere Werkbank für beaufsichtigte GENUS-Codeentwürfe.

Nur diese Membran darf Git-Prozesse und ein entferntes Coding-Modell aufrufen.  Sie kann einen
detached Worktree vorbereiten, einen hashgebunden freigegebenen Draft erzeugen, ihn anwenden und
allowlist-basierte Gates fahren.  Sie besitzt absichtlich keinen Codepfad für Commit, Merge,
Push oder Deploy.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from genus import entwickler  # noqa: E402
import model_gateway  # noqa: E402


CONSENT_VALUE = "github-models:repository-source:draft-only"
DEFAULT_CONSENT_FILE = Path.home() / ".genus" / "coder.enabled"
DEFAULT_WORK_ROOT = Path.home() / ".genus" / "entwickler" / "worktrees"
_SOURCE_LIMIT = 60_000
_PER_FILE_LIMIT = 24_000
_OUTPUT_LIMIT = 6_000
_MANUAL_GATES = frozenset({"security_review", "runtime_observation"})


class WorkerError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    gate: str
    argv: tuple[str, ...]
    returncode: int
    elapsed_ms: int
    output: str


RunFn = Callable[[Sequence[str], Path, float], CommandResult]


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise WorkerError(f"{path} enthält kein JSON-Objekt")
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


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _run(argv: Sequence[str], cwd: Path, timeout: float) -> CommandResult:
    if not argv or any(not isinstance(part, str) or not part for part in argv):
        raise WorkerError("Leerer oder ungültiger Prozessaufruf")
    started = time.monotonic()
    try:
        result = subprocess.run(
            list(argv), cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkerError(f"Prozess fehlgeschlagen: {argv[0]}") from exc
    elapsed = max(0, round((time.monotonic() - started) * 1000))
    combined = ((result.stdout or "") + (result.stderr or "")).strip()
    return CommandResult("process", tuple(argv), result.returncode, elapsed, combined)


def _as_gate(name: str, result: CommandResult) -> CommandResult:
    return CommandResult(name, result.argv, result.returncode, result.elapsed_ms,
                         result.output[-_OUTPUT_LIMIT:])


def _validate_pair(spec: dict, approval: dict) -> None:
    errors = entwickler.validate_approval(spec, approval)
    if errors:
        raise WorkerError("Freigabe verweigert:\n" + "\n".join(errors))


def _current_commit(repo: Path, runner: RunFn = _run) -> str:
    result = runner(("git", "rev-parse", "HEAD"), repo, 20)
    if result.returncode != 0:
        raise WorkerError("Git-Basiscommit ist nicht lesbar")
    value = result.output.splitlines()[-1].strip()
    if not value:
        raise WorkerError("Git-Basiscommit ist leer")
    return value


def _require_isolated_clean_checkout(repo: Path, base_commit: str, work_root: Path,
                                     runner: RunFn = _run) -> None:
    if not _inside(repo, work_root) or not (repo / ".git").is_file():
        raise WorkerError("Coding-Schritt ist nur in einem vorbereiteten detached Worktree erlaubt")
    if _current_commit(repo, runner) != base_commit:
        raise WorkerError("Worktree steht nicht auf dem freigegebenen Basis-Commit")
    status = runner(("git", "status", "--porcelain=v1", "--untracked-files=all"), repo, 30)
    if status.returncode != 0 or status.output.strip():
        raise WorkerError("Worktree ist vor dem Coding-Schritt nicht sauber")


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def prepare_workspace(spec: dict, approval: dict, workspace: Path, *, repo: Path = ROOT,
                      work_root: Path = DEFAULT_WORK_ROOT, runner: RunFn = _run) -> dict:
    """Erzeugt einen detached Worktree. Bestehende Ziele werden nie überschrieben."""
    _validate_pair(spec, approval)
    if _current_commit(repo, runner) != spec["base_commit"]:
        raise WorkerError("Repository steht nicht auf dem freigegebenen Basis-Commit")
    if not _inside(workspace, work_root):
        raise WorkerError(f"Worktree muss unter {work_root} liegen")
    if workspace.exists():
        raise WorkerError("Worktree-Ziel existiert bereits; Löschen bleibt menschlich")
    work_root.mkdir(parents=True, exist_ok=True)
    result = runner(
        ("git", "worktree", "add", "--detach", str(workspace), spec["base_commit"]),
        repo, 90,
    )
    if result.returncode != 0:
        raise WorkerError("Git konnte den isolierten Worktree nicht erzeugen: " + result.output)
    return {
        "schema": "genus-worktree-receipt-v1",
        "spec_sha256": spec["spec_sha256"],
        "approval_sha256": approval["approval_sha256"],
        "base_commit": spec["base_commit"],
        "workspace": str(workspace),
        "detached": True,
        "rights": {"commit": False, "merge": False, "push": False, "deploy": False},
    }


def _secure_consent(path: Path = DEFAULT_CONSENT_FILE) -> bool:
    if os.environ.get("GENUS_CODER_ENABLE") != "1":
        return False
    try:
        stat = path.stat()
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if path.is_symlink() or value != CONSENT_VALUE:
        return False
    if os.name == "posix" and (stat.st_mode & 0o077 or stat.st_uid != os.getuid()):
        return False
    return True


def source_bundle(spec: dict, *, repo: Path = ROOT) -> str:
    """Liest ausschließlich freigegebene Repo-Dateien, niemals Git, Umgebung oder Secrets."""
    chunks = []
    total = 0
    for relative in spec["allowed_files"]:
        path = repo / relative
        try:
            path.resolve(strict=False).relative_to(repo.resolve(strict=True))
        except (OSError, ValueError) as exc:
            raise WorkerError(f"Quellpfad verlässt das Repository: {relative}") from exc
        cursor = path
        while cursor != repo:
            if cursor.is_symlink():
                raise WorkerError(f"Symlink im freigegebenen Scope: {relative}")
            cursor = cursor.parent
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            if len(text) > _PER_FILE_LIMIT:
                text = text[:_PER_FILE_LIMIT] + "\n[GEDECKELT]\n"
        else:
            text = "[NEUE DATEI — noch nicht vorhanden]\n"
        chunk = f"\n--- {relative} ---\n{text}"
        if total + len(chunk) > _SOURCE_LIMIT:
            raise WorkerError("Freigegebener Quellumfang überschreitet das Remote-Budget")
        chunks.append(chunk)
        total += len(chunk)
    return "".join(chunks)


def _generation_schema() -> model_gateway.JsonSchema:
    return model_gateway.JsonSchema(
        "genus_code_draft",
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["patch", "summary", "tests"],
            "properties": {
                "patch": {"type": "string"},
                "summary": {"type": "string"},
                "tests": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
            },
        },
    )


def generate_patch(spec: dict, approval: dict, *, output: Path, receipt: Path | None = None,
                   repo: Path = ROOT, consent_file: Path = DEFAULT_CONSENT_FILE,
                   work_root: Path = DEFAULT_WORK_ROOT, runner: RunFn = _run,
                   gateway=None) -> dict:
    """Lässt ein Modell nur einen Unified-Diff vorschlagen; Anwendung und Abnahme sind getrennt."""
    _validate_pair(spec, approval)
    if not spec["draft_policy"]["external_model_may_propose"]:
        raise WorkerError("Kritischer Scope darf in v1 nicht an ein Coding-Modell gehen")
    _require_isolated_clean_checkout(repo, spec["base_commit"], work_root, runner)
    if not _secure_consent(consent_file):
        raise WorkerError("Repository-Quelltext ist für das Coding-Modell nicht explizit freigegeben")
    model = os.environ.get("GENUS_CODER_MODEL", "").strip()
    if not model:
        raise WorkerError("GENUS_CODER_MODEL ist nicht gesetzt")
    bundle = source_bundle(spec, repo=repo)
    system = (
        "Du bist ein begrenzter Code-Entwurfsworker. Gib ausschließlich JSON im Schema zurück. "
        "Der Patch muss ein Unified-Diff mit diff --git-Köpfen sein, darf nur allowed_files "
        "ändern, keine Dateien löschen/umbenennen und niemals Commit, Merge, Push oder Deploy "
        "ausführen. Erfülle das Ziel mit dem kleinsten tragfähigen Patch und ergänze die "
        "freigegebenen Tests."
    )
    user = json.dumps(
        {
            "goal": spec["goal"], "base_commit": spec["base_commit"],
            "risk": spec["risk"], "allowed_files": spec["allowed_files"],
            "required_tests": spec["required_tests"], "budget": spec["budget"],
            "source_bundle": bundle,
        },
        ensure_ascii=False, sort_keys=True,
    )
    if gateway is None:
        gateway = model_gateway.github_from_token_file(allow_repository_source=True)
    result = gateway.complete(
        model_gateway.ModelRequest(
            role="coding-draft", model=model,
            messages=(model_gateway.Message("system", system), model_gateway.Message("user", user)),
            privacy="repository_source", max_output_tokens=4096, temperature=0.0,
            schema=_generation_schema(),
        ),
        timeout=90,
    )
    try:
        payload = json.loads(result.content)
    except json.JSONDecodeError as exc:
        raise WorkerError("Coding-Modell lieferte kein gültiges JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {"patch", "summary", "tests"}:
        raise WorkerError("Coding-Modell verletzte das Antwortschema")
    if (not isinstance(payload["patch"], str) or not isinstance(payload["summary"], str)
            or not isinstance(payload["tests"], list)
            or any(not isinstance(item, str) for item in payload["tests"])
            or len(payload["tests"]) > 8):
        raise WorkerError("Coding-Modell lieferte ungültige Feldtypen")
    report = entwickler.inspect_patch(spec, payload.get("patch"))
    if not report["ok"]:
        raise WorkerError("Coding-Patch verletzt den Vertrag:\n" + "\n".join(report["errors"]))
    _write_text(output, payload["patch"])
    receipt_value = {
        "schema": "genus-code-generation-receipt-v1",
        "spec_sha256": spec["spec_sha256"],
        "approval_sha256": approval["approval_sha256"],
        "patch_sha256": report["patch_sha256"],
        "provider": result.receipt.provider,
        "model": result.receipt.model,
        "elapsed_ms": result.receipt.elapsed_ms,
        "input_tokens": result.receipt.input_tokens,
        "output_tokens": result.receipt.output_tokens,
        "summary": " ".join(str(payload["summary"]).split())[:500],
        "claimed_tests": [str(item)[:200] for item in payload["tests"][:8]],
        "rights": {"commit": False, "merge": False, "push": False, "deploy": False},
    }
    if receipt:
        _write(receipt, receipt_value)
    return receipt_value


def gate_commands(spec: dict) -> list[tuple[str, tuple[str, ...]]]:
    """Nur registrierte argv-Listen; eine Spezifikation kann nie Shelltext einschleusen."""
    py = sys.executable
    commands: list[tuple[str, tuple[str, ...]]] = []
    gates = set(spec["gates"])
    if "ruff" in gates:
        commands.append(("ruff", (py, "-m", "ruff", "check", "genus", "deploy", "tests")))
    if "pytest_targeted" in gates:
        commands.append((
            "pytest_targeted",
            (py, "-m", "pytest", "-q", "--basetemp", ".audit_tmp/entwickler-targeted",
             *spec["required_tests"]),
        ))
    if "alltagsprobe" in gates:
        commands.append(("alltagsprobe", (py, "-m", "genus.cli", "alltagsprobe", "--contracts-only")))
    if "architecture_budget" in gates:
        commands.append((
            "architecture_budget",
            (py, "-m", "pytest", "-q", "--basetemp", ".audit_tmp/entwickler-architecture",
             "tests/test_architecture_budget.py"),
        ))
    if "pytest_full" in gates:
        commands.append((
            "pytest_full",
            (py, "-m", "pytest", "-q", "--basetemp", ".audit_tmp/entwickler-full"),
        ))
    if "kartografie" in gates:
        commands.extend([
            ("kartografie_build", (py, "-m", "genus.cli", "kartografie", "build")),
            ("kartografie_check", (py, "-m", "genus.cli", "kartografie", "check")),
        ])
    commands.append(("diff_check", ("git", "diff", "--check")))
    return commands


def apply_and_verify(spec: dict, approval: dict, patch: str, *, workspace: Path,
                     receipt: Path | None = None, work_root: Path = DEFAULT_WORK_ROOT,
                     runner: RunFn = _run) -> dict:
    """Wendet den geprüften Draft im detached Worktree an und erstellt ein Reviewpaket."""
    _validate_pair(spec, approval)
    if not workspace.is_dir():
        raise WorkerError("Worktree fehlt")
    _require_isolated_clean_checkout(workspace, spec["base_commit"], work_root, runner)
    initial = entwickler.inspect_patch(spec, patch)
    if not initial["ok"]:
        raise WorkerError("Patch vor Anwendung blockiert:\n" + "\n".join(initial["errors"]))
    patch_file = workspace.parent / f"{spec['spec_sha256'][:16]}.patch"
    _write_text(patch_file, patch)
    check = runner(("git", "apply", "--check", str(patch_file)), workspace, 30)
    if check.returncode != 0:
        raise WorkerError("git apply --check verweigert den Patch: " + check.output)
    applied = runner(("git", "apply", "--whitespace=error-all", str(patch_file)), workspace, 30)
    if applied.returncode != 0:
        raise WorkerError("Patch konnte nicht angewendet werden: " + applied.output)

    deadline = time.monotonic() + int(spec["budget"]["max_minutes"]) * 60
    results = []
    for gate, argv in gate_commands(spec):
        if time.monotonic() >= deadline:
            results.append(CommandResult(gate, argv, 124, 0, "Gesamtzeitbudget erschöpft"))
            break
        timeout = max(10.0, min(600.0, deadline - time.monotonic()))
        results.append(_as_gate(gate, runner(argv, workspace, timeout)))

    diff = runner(("git", "diff", "--no-ext-diff", "--binary"), workspace, 30)
    if diff.returncode != 0:
        raise WorkerError("Finaler Worktree-Diff ist nicht lesbar")
    final = entwickler.inspect_patch(spec, diff.output, allow_generated=True)
    automated_ready = final["ok"] and all(result.returncode == 0 for result in results)
    manual = sorted(set(spec["gates"]) & _MANUAL_GATES)
    value = {
        "schema": "genus-code-review-v1",
        "spec_sha256": spec["spec_sha256"],
        "approval_sha256": approval["approval_sha256"],
        "base_commit": spec["base_commit"],
        "workspace": str(workspace),
        "initial_patch": initial,
        "final_patch": final,
        "gates": [asdict(result) for result in results],
        "automated_ready_for_human_review": automated_ready,
        "manual_gates": manual,
        "merge_ready": False,
        "rights": {"commit": False, "merge": False, "push": False, "deploy": False},
    }
    if receipt:
        _write(receipt, value)
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--spec", type=Path, required=True)
    prepare.add_argument("--approval", type=Path, required=True)
    prepare.add_argument("--workspace", type=Path, required=True)
    prepare.add_argument("--receipt", type=Path)
    generate = commands.add_parser("generate")
    generate.add_argument("--spec", type=Path, required=True)
    generate.add_argument("--approval", type=Path, required=True)
    generate.add_argument("--workspace", type=Path, required=True)
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--receipt", type=Path)
    apply = commands.add_parser("apply")
    apply.add_argument("--spec", type=Path, required=True)
    apply.add_argument("--approval", type=Path, required=True)
    apply.add_argument("--patch", type=Path, required=True)
    apply.add_argument("--workspace", type=Path, required=True)
    apply.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        spec, approval = _load(args.spec), _load(args.approval)
        if args.command == "prepare":
            value = prepare_workspace(spec, approval, args.workspace)
            if args.receipt:
                _write(args.receipt, value)
        elif args.command == "generate":
            value = generate_patch(
                spec, approval, output=args.output, receipt=args.receipt, repo=args.workspace,
            )
        else:
            value = apply_and_verify(
                spec, approval, args.patch.read_text(encoding="utf-8"),
                workspace=args.workspace, receipt=args.receipt,
            )
    except (OSError, ValueError, json.JSONDecodeError, WorkerError, model_gateway.GatewayError) as exc:
        print(f"[ENTWICKLER-WORKER] BLOCKIERT: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
