"""Keep the documentation library navigable and explicitly classified."""

from __future__ import annotations

import re
from collections import deque
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\((?P<target>[^)]+)\)")
HTML_LINK = re.compile(r"\bhref=[\"'](?P<target>[^\"']+)[\"']", re.IGNORECASE)
HTML_ID = re.compile(r"\bid=[\"'](?P<anchor>[^\"']+)[\"']", re.IGNORECASE)
MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*#*\s*$", re.MULTILINE)
EXTERNAL_SCHEMES = {"data", "http", "https", "mailto", "tel"}

CANONICAL_DOCS = {
    "ARCHITECTURE.md",
    "CHARTER.md",
    "EVENT_CONTRACT.md",
    "NOW.md",
    "QUALITY.md",
    "README.md",
    "ROADMAP.md",
    "SECURITY_MODEL.md",
}

RETIRED_TOP_LEVEL_NAMES = {
    "GENUS_ABITUR.md",
    "GENUS_ANTIZIPATION.md",
    "GENUS_ARCHITECTURE.md",
    "GENUS_ARCHITEKTUR.md",
    "GENUS_AUDIT_2026_07.md",
    "GENUS_EVENT_CONTRACT.md",
    "GENUS_GEDAECHTNIS.md",
    "GENUS_GESAMTBILD.md",
    "GENUS_GRUNDAUSBILDUNG.md",
    "GENUS_INTELLIGENZ.md",
    "GENUS_LEDGER_AUDIT.md",
    "GENUS_MATERIAL.md",
    "GENUS_PERSOENLICHKEIT.md",
    "GENUS_PHYSIK.md",
    "GENUS_QUALITY.md",
    "GENUS_ROADMAP.md",
    "GENUS_SENSOR_PRINCIPLE.md",
    "GENUS_STUDY.md",
    "GENUS_VISUAL_THINKING.md",
    "genus_atlas_facts.md",
    "genus_core_map.html",
    "genus_visual_atlas.html",
}


def _targets(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    pattern = HTML_LINK if path.suffix == ".html" else MARKDOWN_LINK
    return [match.group("target").strip() for match in pattern.finditer(text)]


def _destination(raw_target: str) -> str:
    target = raw_target
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    elif " " in target:
        # Markdown permits an optional title after the destination.
        target = target.split(maxsplit=1)[0]
    return target


def _local_target(source: Path, raw_target: str) -> Path | None:
    target = _destination(raw_target)

    parsed = urlsplit(target)
    if parsed.scheme.lower() in EXTERNAL_SCHEMES or parsed.netloc:
        return None
    if not parsed.path:
        return source.resolve() if parsed.fragment else None

    decoded = unquote(parsed.path)
    candidate = Path(decoded)
    if candidate.is_absolute():
        return candidate.resolve()
    return (source.parent / candidate).resolve()


def _anchors(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".html":
        return {unquote(match.group("anchor")) for match in HTML_ID.finditer(text)}

    anchors: set[str] = set()
    occurrences: dict[str, int] = {}
    for match in MARKDOWN_HEADING.finditer(text):
        title = match.group("title")
        title = re.sub(r"<[^>]+>", "", title)
        title = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", title)
        title = title.replace("`", "").replace("*", "").replace("_", "")
        base = re.sub(r"[^\w\- ]", "", title.lower(), flags=re.UNICODE)
        base = re.sub(r"\s", "-", base)
        index = occurrences.get(base, 0)
        occurrences[base] = index + 1
        anchors.add(base if index == 0 else f"{base}-{index}")
    return anchors


def _documentation_files() -> set[Path]:
    return {
        path.resolve()
        for path in DOCS.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".html"}
    }


def test_documentation_top_level_is_intentional():
    actual = {path.name for path in DOCS.iterdir() if path.is_file()}
    assert actual == CANONICAL_DOCS
    assert not (ROOT / "GENUS_PI_SEED_v0_CPU_BELIEF_LOOP_SPEC.md").exists(), (
        "the historical v0 spec belongs only in docs/archive"
    )
    assert RETIRED_TOP_LEVEL_NAMES.isdisjoint(actual)


def test_manually_maintained_markdown_declares_its_status_near_the_top():
    missing: list[str] = []
    for path in sorted(DOCS.rglob("*.md")):
        if path.parent == DOCS / "generated":
            continue
        opening = "\n".join(path.read_text(encoding="utf-8").splitlines()[:18]).lower()
        if "status" not in opening:
            missing.append(path.relative_to(ROOT).as_posix())

    assert missing == [], "documentation without an opening status marker:\n" + "\n".join(missing)


def test_all_local_documentation_links_resolve():
    broken: list[str] = []
    bad_anchors: list[str] = []
    public_entrypoints = {
        ROOT / "README.md",
        ROOT / "SECURITY.md",
        ROOT / "deploy" / "README.md",
    }
    sources = sorted(public_entrypoints | _documentation_files())

    for source in sources:
        for raw_target in _targets(source):
            target = _local_target(source, raw_target)
            if target is not None and not target.exists():
                broken.append(
                    f"{source.relative_to(ROOT).as_posix()} -> {raw_target}"
                )
                continue
            fragment = unquote(urlsplit(_destination(raw_target)).fragment)
            if target is not None and fragment and fragment not in _anchors(target):
                bad_anchors.append(
                    f"{source.relative_to(ROOT).as_posix()} -> {raw_target}"
                )

    assert broken == [], "broken local documentation links:\n" + "\n".join(broken)
    assert bad_anchors == [], "broken documentation anchors:\n" + "\n".join(bad_anchors)


def test_every_document_is_reachable_from_the_documentation_index():
    expected = _documentation_files()
    start = (DOCS / "README.md").resolve()
    visited: set[Path] = set()
    queue: deque[Path] = deque([start])

    while queue:
        source = queue.popleft()
        if source in visited or source not in expected:
            continue
        visited.add(source)
        for raw_target in _targets(source):
            target = _local_target(source, raw_target)
            if target is not None and target in expected and target not in visited:
                queue.append(target)

    orphaned = sorted(path.relative_to(ROOT).as_posix() for path in expected - visited)
    assert orphaned == [], "documents not reachable from docs/README.md:\n" + "\n".join(orphaned)
