"""Die äußere Coding-Werkbank bleibt isoliert, allowlist-basiert und ohne Git-Autorität."""
from __future__ import annotations

import importlib
from pathlib import Path
import sys

from genus import entwickler


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"
if str(DEPLOY) not in sys.path:
    sys.path.insert(0, str(DEPLOY))


def _worker():
    return importlib.import_module("entwickler_worker")


def _spec(path="docs/NOW.md", tests=()):
    return entwickler.make_change_spec(
        "Kleiner beaufsichtigter Entwurf", allowed_files=[path], required_tests=tests,
    )


def _patch(path="docs/NOW.md"):
    return (
        f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
        "@@ -1,1 +1,2 @@\n # GENUS\n+Beaufsichtigter Entwurf.\n"
    )


def test_remote_coder_braucht_umgebung_sichere_datei_und_exakten_wert(tmp_path, monkeypatch):
    worker = _worker()
    consent = tmp_path / "coder.enabled"
    consent.write_text(worker.CONSENT_VALUE, encoding="utf-8")
    consent.chmod(0o600)
    monkeypatch.delenv("GENUS_CODER_ENABLE", raising=False)
    assert worker._secure_consent(consent) is False
    monkeypatch.setenv("GENUS_CODER_ENABLE", "1")
    assert worker._secure_consent(consent) is True
    consent.write_text("zu weit", encoding="utf-8")
    assert worker._secure_consent(consent) is False


def test_source_bundle_liest_nur_explizit_freigegebene_dateien():
    worker = _worker()
    spec = _spec()
    bundle = worker.source_bundle(spec)
    assert "--- docs/NOW.md ---" in bundle
    assert "telegram_bot_token" not in bundle
    assert "--- genus/" not in bundle


def test_gate_registry_enthaelt_nur_argv_und_keinen_freien_shelltext():
    worker = _worker()
    spec = _spec("genus/antwort.py", tests=("tests/test_antwort.py",))
    commands = worker.gate_commands(spec)
    names = {name for name, _ in commands}
    assert {"ruff", "pytest_targeted", "alltagsprobe", "kartografie_build",
            "kartografie_check", "diff_check"} <= names
    for _, argv in commands:
        assert isinstance(argv, tuple) and argv
        assert not any(part in {"bash", "sh", "-c", "&&", ";"} for part in argv)


def test_prepare_erzeugt_nur_detached_worktree_ohne_git_rechte(tmp_path):
    worker = _worker()
    spec = _spec()
    approval = entwickler.approve(spec, "ronny", approved_at="2026-07-15T18:00:00Z")
    calls = []

    def fake(argv, cwd, timeout):
        calls.append(tuple(argv))
        output = spec["base_commit"] if tuple(argv[:3]) == ("git", "rev-parse", "HEAD") else "ok"
        return worker.CommandResult("process", tuple(argv), 0, 1, output)

    root = tmp_path / "worktrees"
    receipt = worker.prepare_workspace(
        spec, approval, root / "job", work_root=root, runner=fake,
    )
    assert calls[-1][:4] == ("git", "worktree", "add", "--detach")
    assert receipt["detached"] is True
    assert not any(receipt["rights"].values())


def test_prepare_verweigert_ziel_ausserhalb_des_werkstattwurzel(tmp_path):
    worker = _worker()
    spec = _spec()
    approval = entwickler.approve(spec, "ronny")

    def fake(argv, cwd, timeout):
        return worker.CommandResult("process", tuple(argv), 0, 1, spec["base_commit"])

    try:
        worker.prepare_workspace(
            spec, approval, tmp_path / "fremd", work_root=tmp_path / "erlaubt", runner=fake,
        )
    except worker.WorkerError as exc:
        assert "unter" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Scope-Escape wurde akzeptiert")


def test_generate_liefert_nur_geprueften_patch_und_beleg(tmp_path, monkeypatch):
    worker = _worker()
    import model_gateway

    spec = _spec()
    approval = entwickler.approve(spec, "ronny", approved_at="2026-07-15T18:00:00Z")
    consent = tmp_path / "coder.enabled"
    consent.write_text(worker.CONSENT_VALUE, encoding="utf-8")
    consent.chmod(0o600)
    monkeypatch.setenv("GENUS_CODER_ENABLE", "1")
    monkeypatch.setenv("GENUS_CODER_MODEL", "test/model")
    workspace = tmp_path / "worktrees" / "job"
    (workspace / "docs").mkdir(parents=True)
    (workspace / ".git").write_text("gitdir: test", encoding="utf-8")
    (workspace / "docs" / "NOW.md").write_text("# GENUS\n", encoding="utf-8")

    def fake(argv, cwd, timeout):
        output = spec["base_commit"] if tuple(argv[:3]) == ("git", "rev-parse", "HEAD") else ""
        return worker.CommandResult("process", tuple(argv), 0, 1, output)

    class Gateway:
        def complete(self, request, timeout):
            assert request.privacy == "repository_source" and request.temperature == 0.0
            content = '{"patch":' + __import__("json").dumps(_patch()) + \
                      ',"summary":"klein","tests":[]}'
            return model_gateway.ModelResult(
                content,
                model_gateway.ModelReceipt("fake", "test/model", None, 5, 100, 20, "stop"),
            )

    out = tmp_path / "draft.patch"
    receipt = worker.generate_patch(
        spec, approval, output=out, consent_file=consent, repo=workspace,
        work_root=tmp_path / "worktrees", runner=fake, gateway=Gateway(),
    )
    assert out.read_text(encoding="utf-8") == _patch()
    assert receipt["patch_sha256"] == entwickler.inspect_patch(spec, _patch())["patch_sha256"]
    assert not any(receipt["rights"].values())


def test_kritischer_scope_geht_nie_an_das_modell(tmp_path, monkeypatch):
    worker = _worker()
    spec = _spec("genus/ledger.py")
    approval = entwickler.approve(spec, "ronny")
    monkeypatch.setenv("GENUS_CODER_ENABLE", "1")
    monkeypatch.setenv("GENUS_CODER_MODEL", "test/model")
    try:
        worker.generate_patch(spec, approval, output=tmp_path / "x.patch", gateway=object())
    except worker.WorkerError as exc:
        assert "Kritischer Scope" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("kritischer Scope wurde nach außen gegeben")


def test_apply_and_verify_endet_vor_menschlichem_merge(tmp_path):
    worker = _worker()
    spec = _spec()
    approval = entwickler.approve(spec, "ronny", approved_at="2026-07-15T18:00:00Z")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").write_text("gitdir: test", encoding="utf-8")
    patch = _patch()

    def fake(argv, cwd, timeout):
        command = tuple(argv)
        if command[:3] == ("git", "rev-parse", "HEAD"):
            output = spec["base_commit"]
        elif command[:3] == ("git", "status", "--porcelain=v1"):
            output = ""
        elif command[:4] == ("git", "diff", "--no-ext-diff", "--binary"):
            output = patch
        else:
            output = "ok"
        return worker.CommandResult("process", command, 0, 1, output)

    receipt = worker.apply_and_verify(
        spec, approval, patch, workspace=workspace, work_root=tmp_path, runner=fake,
    )
    assert receipt["automated_ready_for_human_review"] is True
    assert receipt["merge_ready"] is False
    assert not any(receipt["rights"].values())
    assert all(result["returncode"] == 0 for result in receipt["gates"])


def test_apply_verweigert_hauptrepository_und_schmutzigen_worktree(tmp_path):
    worker = _worker()
    spec = _spec()
    approval = entwickler.approve(spec, "ronny")

    try:
        worker.apply_and_verify(spec, approval, _patch(), workspace=ROOT, work_root=tmp_path)
    except worker.WorkerError as exc:
        assert "detached Worktree" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Hauptrepository wurde als Coding-Worktree akzeptiert")

    workspace = tmp_path / "worktrees" / "dirty"
    workspace.mkdir(parents=True)
    (workspace / ".git").write_text("gitdir: test", encoding="utf-8")

    def fake(argv, cwd, timeout):
        output = spec["base_commit"] if tuple(argv[:3]) == ("git", "rev-parse", "HEAD") else " M x"
        return worker.CommandResult("process", tuple(argv), 0, 1, output)

    try:
        worker.apply_and_verify(
            spec, approval, _patch(), workspace=workspace,
            work_root=tmp_path / "worktrees", runner=fake,
        )
    except worker.WorkerError as exc:
        assert "nicht sauber" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Schmutziger Worktree wurde akzeptiert")
