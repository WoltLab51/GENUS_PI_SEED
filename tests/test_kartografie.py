import ast
import inspect
import json
from pathlib import Path

from click.testing import CliRunner

from genus import cli, event_router, integrity, kartografie, kartografie_render


ROOT = Path(__file__).resolve().parents[1]


def _reachable_projector_source(projector) -> str:
    """Independent one-module call graph used to verify declared table effects."""
    function = inspect.unwrap(projector)
    module = inspect.getmodule(function)
    assert module is not None
    module_source = inspect.getsource(module)
    tree = ast.parse(module_source)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    pending = [function.__name__]
    seen: set[str] = set()
    fragments: list[str] = []
    while pending:
        name = pending.pop()
        if name in seen or name not in functions:
            continue
        seen.add(name)
        node = functions[name]
        fragments.append(ast.get_source_segment(module_source, node) or "")
        for call in (item for item in ast.walk(node) if isinstance(item, ast.Call)):
            if isinstance(call.func, ast.Name) and call.func.id in functions:
                pending.append(call.func.id)
    return "\n".join(fragments)


def test_map_is_deterministic_complete_and_source_bound():
    first = kartografie.build_map()
    second = kartografie.build_map()
    assert first == second
    assert first["summary"]["event_types"] == 39
    assert first["summary"]["projected_events"] == 23
    assert first["summary"]["raw_events"] == 16
    assert first["summary"]["projection_tables"] == 12
    assert first["summary"]["modules"] == len(
        list((ROOT / "genus").rglob("*.py")) + list((ROOT / "deploy").rglob("*.py"))
    )

    node_ids = {node["id"] for node in first["nodes"]}
    assert len(node_ids) == len(first["nodes"])
    for edge in first["edges"]:
        assert edge["from"] in node_ids
        assert edge["to"] in node_ids
    source_owners = [
        *first["nodes"],
        *first["edges"],
        *first["learning_impact"],
        *first["findings"],
        first["runtime_snapshot"],
    ]
    for owner in source_owners:
        for ref in owner.get("sources", []):
            path = Path(ref["file"])
            assert not path.is_absolute()
            assert ".." not in path.parts
            source_path = ROOT / path
            assert source_path.is_file()
            assert 1 <= ref["line"] <= len(source_path.read_text(encoding="utf-8").splitlines())
    for item in first["analysis_limits"]["dynamic_sql_calls"]:
        ref = item["source"]
        assert (ROOT / ref["file"]).is_file()


def test_projection_target_contract_matches_router_schema_replay_and_integrity(conn):
    assert set(event_router.PROJEKTOREN) == set(event_router.PROJEKTIONSZIELE)
    targets = {
        table for values in event_router.PROJEKTIONSZIELE.values() for table in values
    }
    assert targets == set(event_router.REPLAY_PROJEKTIONSTABELLEN)
    schema_tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'table'"
        ).fetchall()
    }
    assert targets <= schema_tables
    assert targets == set(integrity.SNAPSHOT_PROJEKTIONSTABELLEN.values())
    assert set(integrity.SNAPSHOT_PROJEKTIONSTABELLEN) == set(
        integrity.snapshot_projections(conn)
    )
    assert not (set(event_router.BEWUSST_ROH) & set(event_router.PROJEKTIONSZIELE))
    for event, projector in event_router.PROJEKTOREN.items():
        function_source = _reachable_projector_source(projector)
        for target in event_router.PROJEKTIONSZIELE[event]:
            assert target in function_source, (
                f"{event}: declared target {target} is not visible in "
                f"{projector.__module__}.{projector.__name__}"
            )


def test_event_scanner_resolves_ledger_import_aliases():
    tree = ast.parse(
        '''
from genus import ledger as history
from genus.ledger import append as write_event
EVENT = "alias_event"

def one(conn):
    history.append(conn, EVENT, {})

def two(conn):
    write_event(conn, "direct_alias_event", {})
'''
    )
    owners, appenders = kartografie._ledger_bindings(tree)
    visitor = kartografie._CallVisitor(kartografie._constants(tree), owners, appenders)
    visitor.visit(tree)
    assert {event for _, _, event in visitor.events} == {
        "alias_event",
        "direct_alias_event",
    }


def test_map_distinguishes_replay_raw_learning_and_missing_answer_contracts():
    data = kartografie.build_map()
    edge_types = {edge["type"] for edge in data["edges"]}
    assert {"produces_event", "routes_on_replay", "writes_projection"} <= edge_types
    assert {"raw_fold", "audit_only"} <= edge_types
    assert {"imports_eager", "imports_lazy"} <= edge_types

    impact = {item["signal"]: item["impact"] for item in data["learning_impact"]}
    assert impact["Fakten und Relationen"] == "direct"
    assert impact["Intent-Lesungen"] == "none"
    assert impact["Explizites Antwortfeedback (👍/👎)"] == "none"
    assert impact["Modellgedeutetes Lob oder Kritik"] == "none"
    assert impact["Modellgewichte"] == "none"

    semantic = {node["id"]: node for node in data["nodes"]}
    assert semantic["h1:answer_draft"]["status"] == "active_pilot"
    assert semantic["h1:dialogue_frame"]["status"] == "active_pilot"
    assert semantic["h1:outcome"]["status"] == "active_delivered_only"
    assert semantic["h1:feedback"]["status"] == "active_explicit_gated"

    missing = {
        node["id"]
        for node in data["nodes"]
        if node.get("status") == "missing_h1"
    }
    assert {
        "h1:memory_vault",
        "h1:discourse",
        "h1:evaluation",
    } == missing

    edge_keys = {
        (edge["from"], edge["to"], edge["type"]) for edge in data["edges"]
    }
    assert ("module:genus.motor", "table:event_log", "reads_table") in edge_keys
    assert (
        "module:genus.betriebsprofil",
        "table:belief_projection",
        "reads_table",
    ) in edge_keys
    assert ("module:genus.db", "table:event_log", "initializes_schema") in edge_keys
    assert (
        "flow:telegram_send",
        "h1:outcome",
        "records_after_receipt",
    ) in edge_keys
    assert (
        "h1:answer_draft",
        "flow:composer",
        "renders_pilot",
    ) in edge_keys
    assert (
        "h1:dialogue_frame",
        "flow:composer",
        "frames_pilot",
    ) in edge_keys
    assert (
        "h1:outcome",
        "h1:feedback",
        "links_explicit_feedback",
    ) in edge_keys
    assert data["analysis_limits"]["dynamic_sql_calls"]


def test_pi_overlay_is_sanitized_and_dated():
    data = kartografie.build_map()
    runtime = [node for node in data["nodes"] if node["id"].startswith("runtime:")]
    assert runtime
    assert {node["observed_at"] for node in runtime} == {"2026-07-13"}
    serialized = json.dumps(data, ensure_ascii=False)
    for forbidden in (
        "C:\\Users\\ronny",
        "/home/ronny",
        "TELEGRAM_BOT_TOKEN",
        "allowed_user_id",
        "chat_id\":",
    ):
        assert forbidden not in serialized


def test_generated_artifacts_are_current_and_self_contained():
    data = kartografie.build_map()
    assert kartografie_render.stale_artifacts(data) == []
    html_text = kartografie_render.HTML_PATH.read_text(encoding="utf-8")
    assert data["content_sha256"] in html_text
    assert "GENUS-Kartografie" in html_text
    assert "Wirkungskette" in html_text
    assert "Pi-Betrieb" in html_text
    for forbidden in ("fetch(", "XMLHttpRequest", "WebSocket("):
        assert forbidden not in html_text
    assert "innerHTML" not in html_text
    assert 'id="canvas" class="canvas" aria-live' not in html_text
    assert all(item["sources"] for item in data["learning_impact"])
    assert kartografie_render.HTML_PATH.stat().st_size < 2_000_000


def test_kartografie_check_command_runs():
    result = CliRunner().invoke(cli.main, ["kartografie", "check"])
    assert result.exit_code == 0, result.output
    assert "[KARTE] current" in result.output
