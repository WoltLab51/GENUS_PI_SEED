import json

import pytest
from click.testing import CliRunner

from genus import anchor, cli, ledger, sealing


def _obs(i: int) -> dict:
    return {"source": "mock", "raw_value": i, "unit": "n"}


def _fill_sealed(conn, n: int = 3) -> None:
    sealing.open_epoch(conn)
    for i in range(n):
        ledger.append(conn, "observation_created", _obs(i))


def _drop_protection(conn) -> None:
    conn.execute("DROP TRIGGER prevent_event_log_update")
    conn.execute("DROP TRIGGER prevent_event_log_delete")


def _event_snapshot(conn) -> list[tuple]:
    return [
        tuple(row)
        for row in conn.execute(
            """
            SELECT id, event_type, payload, created_at, prev_seal, seal
            FROM event_log
            ORDER BY id
            """
        ).fetchall()
    ]


def _recompute_all_seals(conn) -> None:
    meta = json.loads(sealing.epoch_event(conn)["payload"])
    prev = meta["genesis_digest"]
    rows = conn.execute(
        """
        SELECT id, event_type, payload
        FROM event_log
        WHERE id > ?
        ORDER BY id
        """,
        (meta["prefix_max_id"],),
    ).fetchall()
    for row in rows:
        new_seal = sealing.compute_seal(prev, row["event_type"], row["payload"])
        conn.execute(
            "UPDATE event_log SET prev_seal = ?, seal = ? WHERE id = ?",
            (prev, new_seal, row["id"]),
        )
        prev = new_seal


def _recompute_after_anchor(conn, artifact: dict) -> None:
    prev = artifact["head"]
    rows = conn.execute(
        """
        SELECT id, event_type, payload
        FROM event_log
        WHERE id > ?
        ORDER BY id
        """,
        (artifact["head_event_id"],),
    ).fetchall()
    for row in rows:
        new_seal = sealing.compute_seal(prev, row["event_type"], row["payload"])
        conn.execute(
            "UPDATE event_log SET prev_seal = ?, seal = ? WHERE id = ?",
            (prev, new_seal, row["id"]),
        )
        prev = new_seal


def test_create_anchor_requires_sealing(conn):
    with pytest.raises(anchor.AnchorError, match="sealing is not initialized"):
        anchor.create_anchor(conn, "core-a")


def test_create_anchor_returns_canonical_json_and_does_not_mutate(conn):
    _fill_sealed(conn, 2)
    before = _event_snapshot(conn)

    artifact = anchor.create_anchor(
        conn,
        " core-a ",
        created_at="2026-06-12T10:00:00.000Z",
    )
    text = anchor.canonical_json(artifact)

    assert json.loads(text) == artifact
    assert artifact == {
        "schema": anchor.SCHEMA,
        "core_id": "core-a",
        "created_at": "2026-06-12T10:00:00.000Z",
        "algo": sealing.ALGO,
        "epoch_event_id": 1,
        "event_count": 3,
        "head_event_id": 3,
        "head_event_type": "observation_created",
        "head_created_at": artifact["head_created_at"],
        "head": artifact["head"],
        "derivation": anchor.DERIVATION,
        "signature": None,
    }
    assert _event_snapshot(conn) == before


def test_verify_anchor_accepts_growth_after_anchor(conn):
    _fill_sealed(conn, 2)
    artifact = anchor.create_anchor(conn, "core-a")

    ledger.append(conn, "observation_created", _obs(99))

    assert sealing.verify_chain(conn) == []
    assert anchor.verify_anchor(conn, artifact, core_id="core-a") == []


def test_verify_anchor_rejects_invalid_or_wrong_core_id(conn):
    _fill_sealed(conn, 1)
    artifact = anchor.create_anchor(conn, "core-a")

    invalid = dict(artifact)
    invalid.pop("head")

    assert any("missing required" in issue for issue in anchor.verify_anchor(conn, invalid))
    assert any(
        "core_id mismatch" in issue
        for issue in anchor.verify_anchor(conn, artifact, core_id="core-b")
    )


def test_lazy_tampering_before_anchor_is_detected(conn):
    _fill_sealed(conn, 3)
    artifact = anchor.create_anchor(conn, "core-a")
    target = artifact["head_event_id"] - 1
    _drop_protection(conn)
    conn.execute(
        "UPDATE event_log SET payload = ? WHERE id = ?",
        (sealing.canonical_payload(_obs(999)), target),
    )

    issues = anchor.verify_anchor(conn, artifact, core_id="core-a")

    assert any("seal mismatch" in issue for issue in issues)


def test_adaptive_resealing_before_anchor_is_detected(conn):
    _fill_sealed(conn, 3)
    artifact = anchor.create_anchor(conn, "core-a")
    target = artifact["head_event_id"] - 1
    _drop_protection(conn)
    conn.execute(
        "UPDATE event_log SET payload = ? WHERE id = ?",
        (sealing.canonical_payload(_obs(424242)), target),
    )
    _recompute_all_seals(conn)

    assert sealing.verify_chain(conn) == []
    issues = anchor.verify_anchor(conn, artifact, core_id="core-a")
    assert "anchor head seal mismatch" in issues


def test_tail_truncation_at_anchor_is_detected(conn):
    _fill_sealed(conn, 3)
    artifact = anchor.create_anchor(conn, "core-a")
    _drop_protection(conn)
    conn.execute("DELETE FROM event_log WHERE id = ?", (artifact["head_event_id"],))

    assert sealing.verify_chain(conn) == []
    issues = anchor.verify_anchor(conn, artifact, core_id="core-a")
    assert f"anchored head event {artifact['head_event_id']} not found" in issues


def test_adaptive_resealing_after_anchor_remains_valid_for_old_anchor(conn):
    _fill_sealed(conn, 2)
    artifact = anchor.create_anchor(conn, "core-a")
    first_after_anchor = ledger.append(conn, "observation_created", _obs(10))
    ledger.append(conn, "observation_created", _obs(11))
    _drop_protection(conn)
    conn.execute(
        "UPDATE event_log SET payload = ? WHERE id = ?",
        (sealing.canonical_payload(_obs(5150)), first_after_anchor),
    )
    _recompute_after_anchor(conn, artifact)

    assert sealing.verify_chain(conn) == []
    assert anchor.verify_anchor(conn, artifact, core_id="core-a") == []


def test_tail_truncation_after_anchor_remains_valid_for_old_anchor(conn):
    _fill_sealed(conn, 2)
    artifact = anchor.create_anchor(conn, "core-a")
    ledger.append(conn, "observation_created", _obs(10))
    ledger.append(conn, "observation_created", _obs(11))
    _drop_protection(conn)
    conn.execute("DELETE FROM event_log WHERE id > ?", (artifact["head_event_id"],))

    assert sealing.verify_chain(conn) == []
    assert anchor.verify_anchor(conn, artifact, core_id="core-a") == []


def test_ledger_anchor_cli_stdout_env_file_dir_and_verify(
    monkeypatch,
    tmp_path,
    cli_conn,
    conn,
):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    runner = CliRunner()
    _fill_sealed(conn, 1)

    stdout_result = runner.invoke(
        cli.main,
        ["ledger", "anchor", "create", "--core-id", "core-a"],
    )
    assert stdout_result.exit_code == 0
    stdout_artifact = json.loads(stdout_result.output)
    assert stdout_artifact["core_id"] == "core-a"

    monkeypatch.setenv("GENUS_CORE_ID", "env-core")
    env_result = runner.invoke(cli.main, ["ledger", "anchor", "create"])
    assert env_result.exit_code == 0
    assert json.loads(env_result.output)["core_id"] == "env-core"

    file_path = tmp_path / "anchor.json"
    file_result = runner.invoke(
        cli.main,
        ["ledger", "anchor", "create", "--core-id", "core-a", "--out", str(file_path)],
    )
    assert file_result.exit_code == 0
    assert file_path.exists()

    verify_result = runner.invoke(
        cli.main,
        ["ledger", "anchor", "verify", str(file_path), "--core-id", "core-a"],
    )
    assert verify_result.exit_code == 0
    assert "[ANCHOR] OK" in verify_result.output

    anchor_dir = tmp_path / "anchors"
    anchor_dir.mkdir()
    dir_result = runner.invoke(
        cli.main,
        ["ledger", "anchor", "create", "--core-id", "core-a", "--out", str(anchor_dir)],
    )
    assert dir_result.exit_code == 0
    generated = list(anchor_dir.glob("genus-anchor-core-a-*.json"))
    assert len(generated) == 1

    mismatch = runner.invoke(
        cli.main,
        ["ledger", "anchor", "verify", str(file_path), "--core-id", "wrong-core"],
    )
    assert mismatch.exit_code != 0
    assert "core_id mismatch" in mismatch.output


def test_ledger_anchor_cli_requires_core_id(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    monkeypatch.delenv("GENUS_CORE_ID", raising=False)
    _fill_sealed(conn, 1)

    result = CliRunner().invoke(cli.main, ["ledger", "anchor", "create"])

    assert result.exit_code != 0
    assert "core_id is required" in result.output
