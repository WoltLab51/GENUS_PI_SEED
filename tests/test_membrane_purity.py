"""Membrane purity — the structural guarantee that the deterministic core never
imports the outside world.

GENUS's core (`genus/`) knows by *record*, not by reaching out: HTTP, sockets,
process spawning, and model/LLM SDKs belong to the membrane (the shell scripts in
`deploy/`), never to `genus/`. That rule used to be a hand-run grep — a convention
that depends on someone remembering. This test makes it a *gate*: the moment any
core module imports across the membrane, CI goes red.

It parses the AST of every file under `genus/` (recursively, so new subpackages are
covered automatically) and checks the top-level module of each import.
"""
import ast
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent / "genus"

# Top-level modules the pure core must never import, grouped by the membrane they
# would cross. Explicit on purpose: if some outside dependency is ever genuinely
# needed, it goes *through* the membrane (a deploy/ script feeding events in), not
# by adding it here.
FORBIDDEN = {
    # HTTP / network egress
    "http", "urllib", "urllib3", "requests", "httpx", "aiohttp", "socket",
    "ssl", "websocket", "websockets", "ftplib", "smtplib", "telnetlib",
    "poplib", "imaplib", "grpc",
    # process / outward concurrency — the deterministic core spawns nothing
    "subprocess", "multiprocessing", "asyncio", "pty",
    # model / LLM SDKs — the core knows by record, never by asking a model
    "openai", "anthropic", "cohere", "transformers", "torch", "tensorflow",
    "llama_cpp", "huggingface_hub", "sentence_transformers",
}


def _core_modules():
    return sorted(CORE.rglob("*.py"))


def _imported_roots(tree):
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # relative imports (level > 0) stay inside genus/ — ignore them
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_core_package_is_found():
    # Guard the guard: a wrong path would make the purity test pass vacuously.
    assert _core_modules(), f"no core modules found under {CORE}"


def test_core_never_imports_across_the_membrane():
    violations = []
    for path in _core_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for root in sorted(_imported_roots(tree) & FORBIDDEN):
            violations.append(f"{path.relative_to(CORE.parent)} imports '{root}'")
    assert not violations, (
        "the deterministic core must stay membrane-pure — these imports cross it:\n  "
        + "\n  ".join(violations)
        + "\n(such work belongs in deploy/ shell scripts, never in genus/)"
    )
