"""Der allgemeine GENUS-Entwicklervertrag.

Dieses Modul verbindet die vorhandene Selbstkarte mit Diagnose, Änderungsspezifikation,
hashgebundener menschlicher Freigabe und einer fail-closed Patchprüfung.  Es führt weder
Modelle noch Prozesse aus und verändert keinen Git-Arbeitsbaum: Außenwirkung bleibt in der
Membran ``deploy/entwickler_worker.py``.  Damit gilt auch beim Selbst-Codieren unverändert
``Vorschlag != Änderung != Vertrauen``.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
KARTE = ROOT / "docs" / "generated" / "GENUS_KARTOGRAFIE.json"
SPEC_SCHEMA = "genus-change-spec-v1"
APPROVAL_SCHEMA = "genus-change-approval-v1"
OUTCOME_SCHEMA = "genus-change-outcome-v1"

RISKS = ("low", "medium", "high", "critical")
OUTCOMES = frozenset({"accepted", "rejected", "runtime_regression", "withdrawn"})
REASONS = frozenset({
    "quality", "factuality", "security", "scope", "tests", "runtime",
    "user_direction", "other",
})
GATES = frozenset({
    "diff_check", "ruff", "pytest_targeted", "pytest_full", "kartografie",
    "alltagsprobe", "architecture_budget", "runtime_observation", "security_review",
})

_ALLOWED_SUFFIXES = frozenset({
    ".py", ".md", ".html", ".json", ".toml", ".txt", ".sh", ".ps1", ".yml", ".yaml", ".sql",
})
_FORBIDDEN_PREFIXES = (
    ".git/", ".venv/", ".audit_tmp/", "docs/reports/", "docs/archive/",
)
_ALWAYS_FORBIDDEN = frozenset({
    ".env", "id_rsa", "id_ed25519", "telegram_bot_token", "github_models_token",
})
_CRITICAL_PATHS = (
    "schema.sql", "genus/db.py", "genus/ledger.py", "genus/sealing.py",
    "genus/integrity.py", "genus/governance.py", "genus/operation.py",
    "deploy/pi_deploy.sh", "deploy/deploy_to_pi.ps1", ".github/",
)
_HIGH_PATHS = (
    "deploy/telegram_bot.py", "deploy/model_gateway.py", "deploy/remote_deuter.py",
    "deploy/pi_install_", "genus/control.py", "genus/hand.py", "genus/proposals.py",
    "docs/SECURITY_MODEL.md", "SECURITY.md",
)
_ANSWER_PATHS = (
    "genus/antwort.py", "genus/auskunft.py", "genus/companion.py",
    "genus/dialogplanung.py", "deploy/stimme.py", "deploy/telegram_bot.py",
)
_GENERATED_MAP_FILES = (
    "docs/generated/GENUS_KARTOGRAFIE.json",
    "docs/generated/GENUS_KARTOGRAFIE.md",
    "docs/visual/GENUS_KARTOGRAFIE.html",
)
_BUDGETS = {
    "low": {"max_files": 6, "max_changed_lines": 300, "max_patch_bytes": 80_000,
            "max_minutes": 12},
    "medium": {"max_files": 5, "max_changed_lines": 220, "max_patch_bytes": 60_000,
               "max_minutes": 18},
    "high": {"max_files": 3, "max_changed_lines": 140, "max_patch_bytes": 45_000,
             "max_minutes": 25},
    "critical": {"max_files": 2, "max_changed_lines": 90, "max_patch_bytes": 30_000,
                 "max_minutes": 30},
}

_WORD = re.compile(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß0-9_-]{2,}")
_STOP = frozenset({
    "aber", "alle", "auch", "dass", "denn", "der", "die", "das", "ein", "eine",
    "einer", "eines", "für", "haben", "hier", "ist", "kann", "machen", "mehr", "mit",
    "nicht", "oder", "sich", "sind", "soll", "sollte", "über", "und", "von", "was",
    "werden", "wie", "wir", "wird", "würde", "zum", "zur", "genus",
})
_SUFFIXES = (
    "lichkeiten", "lichkeit", "ungen", "igkeit", "keiten", "heit", "keit", "isch",
    "lich", "ung", "ern", "est", "en", "er", "es", "em", "e", "n", "s",
)

_DIFF_HEADER = re.compile(r"^diff --git a/([^\s]+) b/([^\s]+)$")
_CORE_ESCAPE = (
    re.compile(r"^\+\s*(?:from|import)\s+(?:subprocess|socket|urllib|requests)\b"),
    re.compile(r"^\+.*\bos\.system\s*\("),
)
_SECRET_ADDITION = (
    re.compile(r"^\+.*-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"^\+.*\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"^\+.*\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"^\+.*\b\d{8,12}:[A-Za-z0-9_-]{25,}\b"),
)


def _canonical(data: dict, hash_field: str | None = None) -> bytes:
    payload = dict(data)
    if hash_field:
        payload.pop(hash_field, None)
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _sha(data: dict, hash_field: str | None = None) -> str:
    return hashlib.sha256(_canonical(data, hash_field)).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _git_dir(root: Path) -> Path | None:
    marker = root / ".git"
    if marker.is_dir():
        return marker
    if marker.is_file():
        text = marker.read_text(encoding="utf-8", errors="replace").strip()
        if text.startswith("gitdir:"):
            path = Path(text.split(":", 1)[1].strip())
            return path if path.is_absolute() else (root / path).resolve()
    return None


def git_commit(root: Path = ROOT) -> str | None:
    """Liest den Commit ohne Prozessstart; funktioniert auch in einem Git-Worktree."""
    git_dir = _git_dir(root)
    if git_dir is None:
        return None
    try:
        head = (git_dir / "HEAD").read_text(encoding="ascii").strip()
    except OSError:
        return None
    if not head.startswith("ref:"):
        return head if re.fullmatch(r"[0-9a-f]{40,64}", head) else None
    ref = head.split(None, 1)[1]
    candidates = [git_dir / ref]
    common_dirs: list[Path] = []
    # Linked worktrees keep refs in the common git directory.
    common = git_dir / "commondir"
    if common.exists():
        common_dir = (git_dir / common.read_text(encoding="ascii").strip()).resolve()
        common_dirs.append(common_dir)
        candidates.append(common_dir / ref)
    for candidate in candidates:
        try:
            value = candidate.read_text(encoding="ascii").strip()
        except OSError:
            continue
        if re.fullmatch(r"[0-9a-f]{40,64}", value):
            return value
    for base in (git_dir, *common_dirs):
        packed = base / "packed-refs"
        try:
            lines = packed.read_text(encoding="ascii").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line.startswith(("#", "^")) and line.endswith(" " + ref):
                return line.split(" ", 1)[0]
    return None


def load_map(path: Path = KARTE) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {"schema_version", "content_sha256", "nodes", "edges", "summary", "findings"}
    if not isinstance(data, dict) or not required <= set(data):
        raise ValueError("Selbstkarte ist unvollständig oder hat ein unbekanntes Schema.")
    return data


def stand(root: Path = ROOT, map_path: Path | None = None) -> dict:
    """Kompakte, read-only Selbstbeschreibung mit expliziten Autonomiegrenzen."""
    data = load_map(map_path or root / "docs" / "generated" / "GENUS_KARTOGRAFIE.json")
    finding_counts = Counter(str(item.get("severity", "info")) for item in data["findings"])
    return {
        "schema": "genus-developer-status-v1",
        "commit": git_commit(root),
        "map_sha256": data["content_sha256"],
        "map_schema": data["schema_version"],
        "summary": data["summary"],
        "findings": dict(sorted(finding_counts.items())),
        "capabilities": {
            "self_map": True,
            "evidence_diagnosis": True,
            "hash_bound_change_spec": True,
            "gated_external_draft": True,
            "isolated_worktree": True,
            "independent_tests": True,
            "automatic_commit": False,
            "automatic_merge": False,
            "automatic_deploy": False,
        },
        "trust_boundary": "propose -> draft in isolation -> test -> human review",
    }


def _stem(word: str) -> str:
    value = word.casefold().replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss")
    value = value.replace("_", "-").strip("-")
    for suffix in _SUFFIXES:
        if len(value) - len(suffix) >= 4 and value.endswith(suffix):
            value = value[:-len(suffix)]
            break
    return value


def _terms(text: str) -> tuple[str, ...]:
    return tuple(sorted({
        stem for token in _WORD.findall(text)
        if token.casefold() not in _STOP and len(stem := _stem(token)) >= 3
    }))


def _related(left: str, right: str) -> bool:
    return left == right or (min(len(left), len(right)) >= 5
                             and (left.startswith(right) or right.startswith(left)))


def _source_files(root: Path) -> Iterable[Path]:
    for directory, suffixes in (
        ("genus", {".py"}), ("deploy", {".py", ".sh", ".ps1"}),
        ("tests", {".py"}), ("docs", {".md"}),
    ):
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            rel = path.relative_to(root).as_posix()
            if (path.is_file() and path.suffix.casefold() in suffixes
                    and not rel.startswith(("docs/archive/", "docs/generated/", "docs/reports/",
                                            "docs/visual/"))):
                yield path


def _module_for_file(relative: str) -> str | None:
    path = PurePosixPath(relative)
    if path.suffix == ".py" and path.parts and path.parts[0] in {"genus", "deploy"}:
        return "module:" + ".".join(path.with_suffix("").parts)
    return None


def diagnose(symptom: str, *, root: Path = ROOT, map_path: Path | None = None,
             limit: int = 12) -> dict:
    """Rankt Quellbelege allgemein per Wortüberlappung; behauptet keine unbewiesene Ursache."""
    query = _terms(symptom)
    if not query:
        raise ValueError("Die Diagnose braucht mindestens einen inhaltlichen Suchbegriff.")
    evidence: list[dict] = []
    per_file: Counter[str] = Counter()
    for path in _source_files(root):
        rel = path.relative_to(root).as_posix()
        path_terms = _terms(rel.replace("/", " ").replace(".", " "))
        path_matches = {q for q in query for term in path_terms if _related(q, term)}
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        candidates: list[tuple[int, int, tuple[str, ...], str]] = []
        for line_no, line in enumerate(lines, 1):
            if not line.strip():
                continue
            line_terms = _terms(line)
            matched = tuple(sorted({
                q for q in query for term in line_terms if _related(q, term)
            }))
            if not matched and not path_matches:
                continue
            if not matched and path_matches and line_no > 8 and not line.lstrip().startswith(("def ", "class ")):
                continue
            score = len(matched) * 4 + len(path_matches) * 3
            if rel.startswith("genus/"):
                score += 3
            elif rel.startswith("tests/"):
                score += 2
            if line.lstrip().startswith(("def ", "class ", "#", '"""')):
                score += 1
            candidates.append((score, line_no, matched, " ".join(line.strip().split())[:220]))
        for score, line_no, matched, snippet in sorted(candidates, reverse=True)[:2]:
            evidence.append({
                "file": rel, "line": line_no, "score": score,
                "matched_terms": list(matched or sorted(path_matches)), "snippet": snippet,
            })
            per_file[rel] += score
    evidence.sort(key=lambda item: (-item["score"], item["file"], item["line"]))
    evidence = evidence[:max(1, min(limit, 30))]

    data = load_map(map_path or root / "docs" / "generated" / "GENUS_KARTOGRAFIE.json")
    module_ids = []
    for item in evidence:
        module = _module_for_file(item["file"])
        if module and module not in module_ids:
            module_ids.append(module)
    import_types = {"imports_eager", "imports_lazy", "imports"}
    impact = []
    for edge in data["edges"]:
        if edge.get("type") not in import_types:
            continue
        if edge.get("to") in module_ids and str(edge.get("from", "")).startswith("module:"):
            candidate = edge["from"]
        elif edge.get("from") in module_ids and str(edge.get("to", "")).startswith("module:"):
            candidate = edge["to"]
        else:
            continue
        if candidate not in module_ids and candidate not in impact:
            impact.append(candidate)
    tests = []
    for item in evidence:
        if item["file"].startswith("tests/") and item["file"] not in tests:
            tests.append(item["file"])
    for module in module_ids:
        candidate = "tests/test_" + module.split(".")[-1] + ".py"
        if (root / candidate).is_file() and candidate not in tests:
            tests.append(candidate)
    confidence = "supported" if len({e["file"] for e in evidence}) >= 3 and module_ids else "tentative"
    result = {
        "schema": "genus-diagnosis-v1",
        "symptom": symptom.strip(),
        "query_terms": list(query),
        "confidence": confidence,
        "claim": "Quellnähe und Wirkungsraum, keine bewiesene Root Cause",
        "evidence": evidence,
        "suspected_modules": module_ids[:8],
        "adjacent_modules": impact[:10],
        "candidate_tests": tests[:8],
        "map_sha256": data["content_sha256"],
        "base_commit": git_commit(root),
    }
    result["diagnosis_sha256"] = _sha(result, "diagnosis_sha256")
    return result


def validate_diagnosis(diagnosis: dict, *, root: Path = ROOT,
                       map_path: Path | None = None) -> list[str]:
    """Bindet eine Diagnose exakt an ihren Inhalt, die Selbstkarte und den Basis-Commit."""
    required = {
        "schema", "symptom", "query_terms", "confidence", "claim", "evidence",
        "suspected_modules", "adjacent_modules", "candidate_tests", "map_sha256",
        "base_commit", "diagnosis_sha256",
    }
    if not isinstance(diagnosis, dict) or set(diagnosis) != required:
        return ["Diagnose hat nicht exakt den v1-Vertrag"]
    errors = []
    if diagnosis.get("schema") != "genus-diagnosis-v1":
        errors.append("unbekanntes Diagnose-Schema")
    if not isinstance(diagnosis.get("symptom"), str) or not diagnosis["symptom"].strip():
        errors.append("Diagnose-Symptom fehlt")
    if diagnosis.get("confidence") not in {"tentative", "supported"}:
        errors.append("Diagnose-Konfidenz ist ungültig")
    if diagnosis.get("base_commit") != git_commit(root):
        errors.append("Diagnose gehört zu einem anderen Basis-Commit")
    try:
        current_map = load_map(map_path or root / "docs" / "generated" / "GENUS_KARTOGRAFIE.json")
    except (OSError, ValueError, json.JSONDecodeError):
        errors.append("aktuelle Selbstkarte ist nicht lesbar")
    else:
        if diagnosis.get("map_sha256") != current_map["content_sha256"]:
            errors.append("Diagnose gehört zu einer anderen Selbstkarte")
    for key in ("query_terms", "evidence", "suspected_modules", "adjacent_modules", "candidate_tests"):
        if not isinstance(diagnosis.get(key), list):
            errors.append(f"Diagnosefeld {key} ist keine Liste")
    if diagnosis.get("diagnosis_sha256") != _sha(diagnosis, "diagnosis_sha256"):
        errors.append("Diagnose-Hash stimmt nicht")
    return errors


def _safe_relative(path: str) -> str | None:
    value = path.replace("\\", "/").strip()
    pure = PurePosixPath(value)
    if (not value or value.startswith("/") or pure.is_absolute() or ".." in pure.parts
            or value.endswith("/") or any(value.startswith(p) for p in _FORBIDDEN_PREFIXES)
            or pure.name in _ALWAYS_FORBIDDEN or pure.suffix.casefold() not in _ALLOWED_SUFFIXES):
        return None
    return pure.as_posix()


def _risk(paths: Iterable[str]) -> str:
    values = tuple(paths)
    if any(any(path == prefix or path.startswith(prefix) for prefix in _CRITICAL_PATHS)
           for path in values):
        return "critical"
    if any(any(path == prefix or path.startswith(prefix) for prefix in _HIGH_PATHS)
           for path in values):
        return "high"
    if any(path.startswith(("genus/", "deploy/", "schema")) for path in values):
        return "medium"
    return "low"


def _escalate(risk: str) -> str:
    return RISKS[min(RISKS.index(risk) + 1, len(RISKS) - 1)]


def _required_gates(paths: Iterable[str], tests: Iterable[str], risk: str,
                    learned_caution: Iterable[str]) -> list[str]:
    paths, tests, learned_caution = tuple(paths), tuple(tests), tuple(learned_caution)
    gates = ["diff_check"]
    if any(path.endswith(".py") for path in paths):
        gates.append("ruff")
    if tests:
        gates.append("pytest_targeted")
    if any(path.startswith(("genus/", "deploy/")) or path == "schema.sql" for path in paths):
        gates.append("kartografie")
    if any(path in _ANSWER_PATHS for path in paths):
        gates.append("alltagsprobe")
    if any(path in {"genus/cli.py", "genus/companion.py"} for path in paths):
        gates.append("architecture_budget")
    if risk in {"high", "critical"}:
        gates.extend(["pytest_full", "security_review"])
    if learned_caution:
        gates.append("runtime_observation")
    return list(dict.fromkeys(gates))


def outcome_path() -> Path:
    explicit = os.environ.get("GENUS_DEVELOPER_OUTCOMES")
    return Path(explicit).expanduser() if explicit else Path.home() / ".genus" / "entwickler" / "outcomes.jsonl"


def read_outcomes(path: Path | None = None) -> list[dict]:
    target = path or outcome_path()
    try:
        lines = target.read_text(encoding="utf-8").splitlines()[-1000:]
    except OSError:
        return []
    results = []
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("schema") == OUTCOME_SCHEMA:
            results.append(item)
    return results


def outcome_summary(path: Path | None = None) -> dict:
    rows = read_outcomes(path)
    by_outcome = Counter(row.get("outcome") for row in rows)
    by_reason = Counter(row.get("reason") for row in rows)
    caution = defaultdict(int)
    for row in rows:
        if row.get("outcome") in {"rejected", "runtime_regression"}:
            weight = 2 if row.get("outcome") == "runtime_regression" else 1
            for file in row.get("files") or ():
                caution[str(file)] += weight
    return {
        "total": len(rows),
        "by_outcome": dict(sorted(by_outcome.items())),
        "by_reason": dict(sorted(by_reason.items())),
        "caution_files": dict(sorted(caution.items(), key=lambda item: (-item[1], item[0]))[:20]),
        "autonomy_effect": "accepted outcomes never widen permissions; failures only tighten risk",
    }


def make_change_spec(goal: str, *, diagnosis: dict | None = None,
                     allowed_files: Iterable[str] = (), required_tests: Iterable[str] = (),
                     root: Path = ROOT, history_path: Path | None = None) -> dict:
    """Erzeugt einen Vorschlag. Rechte entstehen erst durch eine separate, hashgebundene Freigabe."""
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("Eine Änderungsspezifikation braucht ein Ziel.")
    if diagnosis is not None:
        diagnosis_errors = validate_diagnosis(diagnosis, root=root)
        if diagnosis_errors:
            raise ValueError("Ungültige oder veraltete Diagnose:\n" + "\n".join(diagnosis_errors))
    candidates = list(allowed_files)
    if not candidates and diagnosis:
        candidates = [
            item["file"] for item in diagnosis.get("evidence") or ()
            if str(item.get("file", "")).startswith(("genus/", "deploy/", "tests/"))
        ][:6]
    paths = []
    for candidate in candidates:
        safe = _safe_relative(str(candidate))
        if safe is None:
            raise ValueError(f"Pfad außerhalb des Entwicklervertrags: {candidate!r}")
        if safe not in paths:
            paths.append(safe)
    if not paths:
        raise ValueError("Mindestens eine ausdrücklich begrenzte Datei ist erforderlich.")

    tests = []
    for candidate in (*required_tests, *((diagnosis or {}).get("candidate_tests") or ())):
        safe = _safe_relative(str(candidate))
        if safe and safe.startswith("tests/") and safe.endswith(".py") and safe not in tests:
            tests.append(safe)
    risk = _risk(paths)
    summary = outcome_summary(history_path)
    caution = set(summary["caution_files"])
    learned_caution = sorted(set(paths) & caution)
    if learned_caution:
        risk = _escalate(risk)

    gates = _required_gates(paths, tests, risk, learned_caution)
    commit = git_commit(root)
    if commit is None:
        raise ValueError("Der Basis-Commit ist nicht ohne Prozessstart belegbar.")
    spec = {
        "schema": SPEC_SCHEMA,
        "goal": goal.strip(),
        "diagnosis_sha256": (diagnosis or {}).get("diagnosis_sha256"),
        "base_commit": commit,
        "risk": risk,
        "allowed_files": paths,
        "generated_files": list(_GENERATED_MAP_FILES) if "kartografie" in gates else [],
        "forbidden_paths": [".git/", ".venv/", "secrets", "live database"],
        "required_tests": tests[:8],
        "gates": gates,
        "budget": dict(_BUDGETS[risk]),
        "learned_caution": learned_caution,
        "human_gates": ["draft_approval", "diff_review", "merge", "deploy"],
        "draft_policy": {
            "external_model_may_propose": risk != "critical",
            "may_commit": False,
            "may_merge": False,
            "may_push": False,
            "may_deploy": False,
        },
    }
    spec["spec_sha256"] = _sha(spec, "spec_sha256")
    errors = validate_spec(spec)
    if errors:
        raise ValueError("Ungültige Änderungsspezifikation:\n" + "\n".join(errors))
    return spec


def validate_spec(spec: dict) -> list[str]:
    errors = []
    required = {
        "schema", "goal", "diagnosis_sha256", "base_commit", "risk", "allowed_files",
        "generated_files", "forbidden_paths", "required_tests", "gates", "budget",
        "learned_caution", "human_gates", "draft_policy", "spec_sha256",
    }
    if not isinstance(spec, dict) or set(spec) != required:
        return ["Spezifikation hat nicht exakt den v1-Vertrag."]
    if spec.get("schema") != SPEC_SCHEMA:
        errors.append("unbekanntes Spec-Schema")
    if not isinstance(spec.get("goal"), str) or not spec["goal"].strip():
        errors.append("Ziel fehlt")
    if not re.fullmatch(r"[0-9a-f]{40,64}", str(spec.get("base_commit", ""))):
        errors.append("Basis-Commit ist ungültig")
    if spec.get("risk") not in RISKS:
        errors.append("Risikostufe ist ungültig")
    paths = spec.get("allowed_files")
    if not isinstance(paths, list) or not paths or any(_safe_relative(str(p)) != p for p in paths):
        errors.append("allowed_files enthält unsichere oder fehlende Pfade")
    if isinstance(paths, list) and len(paths) != len(set(paths)):
        errors.append("allowed_files enthält Duplikate")
    generated = spec.get("generated_files")
    if not isinstance(generated, list) or any(p not in _GENERATED_MAP_FILES for p in generated):
        errors.append("generated_files enthält nichtdeterministische Ziele")
    tests = spec.get("required_tests")
    if (not isinstance(tests, list)
            or any(_safe_relative(str(t)) != t or not str(t).startswith("tests/")
                   or not str(t).endswith(".py") for t in tests)):
        errors.append("required_tests darf nur Python-Tests unter tests/ enthalten")
    gates = spec.get("gates")
    if not isinstance(gates, list) or not gates or any(g not in GATES for g in gates):
        errors.append("unbekanntes oder leeres Gate")
    caution = spec.get("learned_caution")
    if (not isinstance(caution, list) or any(path not in (paths or ()) for path in caution)
            or len(caution) != len(set(caution))):
        errors.append("learned_caution ist nicht auf den Dateiscope begrenzt")
    budget = spec.get("budget")
    expected_budget = _BUDGETS.get(spec.get("risk"))
    if budget != expected_budget:
        errors.append("Budget passt nicht zur Risikostufe")
    base_risk = _risk(paths or ())
    learned_risk = _escalate(base_risk) if caution else base_risk
    if spec.get("risk") != learned_risk:
        errors.append("Risikostufe passt nicht zum Dateiscope")
    if isinstance(gates, list) and gates != _required_gates(paths or (), tests or (),
                                                            str(spec.get("risk")), caution or ()):
        errors.append("Gates passen nicht zu Scope, Risiko und Prüffällen")
    expected_generated = list(_GENERATED_MAP_FILES) if isinstance(gates, list) and "kartografie" in gates else []
    if generated != expected_generated:
        errors.append("generated_files passt nicht zum Kartografie-Gate")
    if spec.get("forbidden_paths") != [".git/", ".venv/", "secrets", "live database"]:
        errors.append("forbidden_paths wurde verändert")
    if spec.get("human_gates") != ["draft_approval", "diff_review", "merge", "deploy"]:
        errors.append("menschliche Gates wurden verändert")
    diagnosis_sha = spec.get("diagnosis_sha256")
    if diagnosis_sha is not None and not re.fullmatch(r"[0-9a-f]{64}", str(diagnosis_sha)):
        errors.append("Diagnose-Hash ist ungültig")
    if not isinstance(spec.get("draft_policy"), dict) or any(
        spec["draft_policy"].get(key) is not False for key in ("may_commit", "may_merge", "may_push", "may_deploy")
    ):
        errors.append("Draft-Policy öffnet verbotene Außenwirkung")
    elif spec["draft_policy"].get("external_model_may_propose") is not (spec.get("risk") != "critical"):
        errors.append("Draft-Policy passt nicht zur kritischen Risikogrenze")
    if spec.get("spec_sha256") != _sha(spec, "spec_sha256"):
        errors.append("Spec-Hash stimmt nicht")
    return errors


def approve(spec: dict, reviewer: str, *, scope: str = "draft_only",
            approved_at: str | None = None) -> dict:
    errors = validate_spec(spec)
    if errors:
        raise ValueError("Nicht freigabefähig:\n" + "\n".join(errors))
    if not reviewer.strip():
        raise ValueError("Eine Freigabe braucht einen menschlichen Reviewer.")
    if scope != "draft_only":
        raise ValueError("v1 darf ausschließlich einen isolierten Entwurf freigeben.")
    approval = {
        "schema": APPROVAL_SCHEMA,
        "spec_sha256": spec["spec_sha256"],
        "base_commit": spec["base_commit"],
        "reviewer": reviewer.strip(),
        "scope": scope,
        "approved_at": approved_at or _now(),
        "rights": {"draft": True, "commit": False, "merge": False, "push": False, "deploy": False},
    }
    approval["approval_sha256"] = _sha(approval, "approval_sha256")
    return approval


def validate_approval(spec: dict, approval: dict) -> list[str]:
    errors = validate_spec(spec)
    if not isinstance(approval, dict):
        return errors + ["Freigabe ist kein Objekt"]
    required = {
        "schema", "spec_sha256", "base_commit", "reviewer", "scope", "approved_at",
        "rights", "approval_sha256",
    }
    if set(approval) != required or approval.get("schema") != APPROVAL_SCHEMA:
        errors.append("Freigabe hat nicht exakt den v1-Vertrag")
        return errors
    if approval.get("spec_sha256") != spec.get("spec_sha256"):
        errors.append("Freigabe gehört zu einer anderen Spezifikation")
    if approval.get("base_commit") != spec.get("base_commit"):
        errors.append("Freigabe gehört zu einem anderen Basis-Commit")
    if approval.get("scope") != "draft_only":
        errors.append("Freigabe öffnet mehr als einen isolierten Entwurf")
    if not isinstance(approval.get("reviewer"), str) or not approval["reviewer"].strip():
        errors.append("Freigabe hat keinen menschlichen Reviewer")
    rights = approval.get("rights")
    if not isinstance(rights, dict) or rights != {
        "draft": True, "commit": False, "merge": False, "push": False, "deploy": False,
    }:
        errors.append("Freigaberechte sind unzulässig")
    if approval.get("approval_sha256") != _sha(approval, "approval_sha256"):
        errors.append("Freigabe-Hash stimmt nicht")
    return errors


def inspect_patch(spec: dict, patch: str, *, allow_generated: bool = False) -> dict:
    """Prüft Scope, Budget und Kernreinheit eines Unified-Diffs; wendet ihn niemals an."""
    errors = validate_spec(spec)
    if not isinstance(patch, str) or not patch.strip():
        errors.append("Patch ist leer")
        patch = ""
    raw = patch.encode("utf-8")
    if not allow_generated and len(raw) > int(spec.get("budget", {}).get("max_patch_bytes", 0)):
        errors.append("Patch überschreitet das Byte-Budget")
    if "GIT binary patch" in patch or "Binary files " in patch:
        errors.append("Binärpatches sind verboten")
    if "deleted file mode" in patch:
        errors.append("Dateilöschungen sind in v1 verboten")
    paths = []
    current = None
    additions = deletions = scoped_additions = scoped_deletions = hunks = 0
    model_scope = set(spec.get("allowed_files") or ())
    for line in patch.splitlines():
        match = _DIFF_HEADER.match(line)
        if match:
            left, right = match.groups()
            current = right
            if left != right:
                errors.append(f"Umbenennung ist in v1 verboten: {left} -> {right}")
            if right not in paths:
                paths.append(right)
            continue
        if line.startswith("@@ "):
            hunks += 1
        if line.startswith(("rename from ", "rename to ", "copy from ", "copy to ",
                            "old mode ", "new mode ", "similarity index ")):
            errors.append("Umbenennungen, Kopien und Modusänderungen sind in v1 verboten")
        if line.startswith("new file mode ") and line != "new file mode 100644":
            errors.append("Neue Dateien müssen reguläre 100644-Dateien sein")
        if line.startswith("--- "):
            header = line[4:]
            if header != "/dev/null" and (current is None or header != "a/" + current):
                errors.append("Alter Dateikopf stimmt nicht mit diff --git überein")
        if line.startswith("+++ "):
            header = line[4:]
            if current is None or header != "b/" + current:
                errors.append("Neuer Dateikopf stimmt nicht mit diff --git überein")
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
            if current in model_scope:
                scoped_additions += 1
            if any(pattern.search(line) for pattern in _SECRET_ADDITION):
                errors.append("Patch enthält ein mögliches Secret")
            if current and current.startswith("genus/") and any(pattern.search(line) for pattern in _CORE_ESCAPE):
                errors.append(f"Kernpfad {current} versucht Prozess- oder Netzwirkung einzuführen")
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
            if current in model_scope:
                scoped_deletions += 1
    if patch and not paths:
        errors.append("Patch enthält keinen gültigen diff --git-Kopf")
    if patch and hunks == 0:
        errors.append("Patch enthält keinen Texthunk")
    effective = set(spec.get("allowed_files") or ())
    if allow_generated:
        effective.update(spec.get("generated_files") or ())
    for path in paths:
        if _safe_relative(path) != path:
            errors.append(f"unsicherer Patchpfad: {path}")
        elif path not in effective:
            errors.append(f"Patchpfad außerhalb der Freigabe: {path}")
    changed = additions + deletions
    scoped_changed = scoped_additions + scoped_deletions
    max_files = int(spec.get("budget", {}).get("max_files", 0))
    if len([p for p in paths if p in set(spec.get("allowed_files") or ())]) > max_files:
        errors.append("Patch überschreitet das Dateibudget")
    if scoped_changed > int(spec.get("budget", {}).get("max_changed_lines", 0)):
        errors.append("Patch überschreitet das Zeilenbudget")
    return {
        "ok": not errors,
        "errors": list(dict.fromkeys(errors)),
        "paths": paths,
        "additions": additions,
        "deletions": deletions,
        "changed_lines": changed,
        "scoped_changed_lines": scoped_changed,
        "patch_bytes": len(raw),
        "patch_sha256": hashlib.sha256(raw).hexdigest(),
    }


def record_outcome(spec: dict, approval: dict, *, outcome: str, reason: str,
                   reviewer: str, note: str = "", path: Path | None = None,
                   recorded_at: str | None = None) -> dict:
    errors = validate_approval(spec, approval)
    if errors:
        raise ValueError("Ergebnis gehört nicht zu einem gültig freigegebenen Entwurf:\n" + "\n".join(errors))
    if outcome not in OUTCOMES or reason not in REASONS:
        raise ValueError("Unbekannter Entwicklungs-Ausgang oder Grund.")
    if not reviewer.strip():
        raise ValueError("Ein Ergebnis braucht einen menschlichen Reviewer.")
    item = {
        "schema": OUTCOME_SCHEMA,
        "spec_sha256": spec["spec_sha256"],
        "approval_sha256": approval["approval_sha256"],
        "base_commit": spec["base_commit"],
        "risk": spec["risk"],
        "files": list(spec["allowed_files"]),
        "outcome": outcome,
        "reason": reason,
        "reviewer": reviewer.strip(),
        "note": " ".join(note.split())[:240],
        "recorded_at": recorded_at or _now(),
    }
    item["outcome_sha256"] = _sha(item, "outcome_sha256")
    target = path or outcome_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return item
