import json

from click.testing import CliRunner

from genus import cli, event_router, integrity, ledger, sealing


def _obs(i: int) -> dict:
    return {"source": "mock", "raw_value": i, "unit": "n"}


def _fill_sealed(conn, n: int = 3) -> None:
    sealing.open_epoch(conn)
    for i in range(n):
        ledger.append(conn, "observation_created", _obs(i))


def _first_real_sealed_id(conn) -> int:
    row = conn.execute(
        """
        SELECT id FROM event_log
        WHERE seal IS NOT NULL AND event_type != ?
        ORDER BY id
        LIMIT 1
        """,
        (sealing.EPOCH_EVENT,),
    ).fetchone()
    return int(row["id"])


def _drop_protection(conn) -> None:
    conn.execute("DROP TRIGGER prevent_event_log_update")
    conn.execute("DROP TRIGGER prevent_event_log_delete")


def test_append_is_unsealed_by_default(conn):
    event_id = ledger.append(conn, "observation_created", _obs(1))

    row = conn.execute(
        "SELECT prev_seal, seal FROM event_log WHERE id = ?",
        (event_id,),
    ).fetchone()

    assert row["prev_seal"] is None
    assert row["seal"] is None
    assert sealing.is_active(conn) is False
    assert sealing.epoch_event(conn) is None


def test_verify_chain_noop_when_inactive(conn):
    ledger.append(conn, "observation_created", _obs(1))

    assert sealing.verify_chain(conn) == []


def test_seal_init_opens_epoch_and_seals_subsequent_appends(conn):
    ledger.append(conn, "observation_created", _obs(0))
    epoch_id = sealing.open_epoch(conn)
    new_id = ledger.append(conn, "observation_created", _obs(1))

    epoch = conn.execute(
        "SELECT prev_seal, seal FROM event_log WHERE id = ?",
        (epoch_id,),
    ).fetchone()
    sealed = conn.execute(
        "SELECT prev_seal, seal FROM event_log WHERE id = ?",
        (new_id,),
    ).fetchone()

    assert epoch_id is not None
    assert epoch["prev_seal"] is not None
    assert epoch["seal"] is not None
    assert sealed["prev_seal"] == epoch["seal"]
    assert sealed["seal"] is not None


def test_open_epoch_is_idempotent(conn):
    _fill_sealed(conn, 2)
    head_before = sealing.head(conn)["seal"]

    assert sealing.open_epoch(conn) is None
    assert sealing.head(conn)["seal"] == head_before
    count = conn.execute(
        "SELECT COUNT(*) AS count FROM event_log WHERE event_type = ?",
        (sealing.EPOCH_EVENT,),
    ).fetchone()["count"]
    assert count == 1


def test_head_advances_with_each_append(conn):
    sealing.open_epoch(conn)
    seals = []

    for i in range(3):
        ledger.append(conn, "observation_created", _obs(i))
        seals.append(sealing.head(conn)["seal"])

    assert len(set(seals)) == 3


def test_clean_chain_verifies_and_integrity_passes(conn):
    _fill_sealed(conn, 4)

    assert sealing.verify_chain(conn) == []
    assert integrity.check(conn)["ok"] is True


def test_lazy_tampering_is_detected(conn):
    _fill_sealed(conn, 3)
    target = _first_real_sealed_id(conn)
    _drop_protection(conn)
    conn.execute(
        "UPDATE event_log SET payload = ? WHERE id = ?",
        (sealing.canonical_payload(_obs(999)), target),
    )

    issues = sealing.verify_chain(conn)

    assert any("seal mismatch" in issue for issue in issues)
    assert integrity.check(conn)["ok"] is False


def test_legacy_prefix_tampering_is_detected_by_genesis(conn):
    ledger.append(conn, "observation_created", _obs(0))
    ledger.append(conn, "observation_created", _obs(1))
    sealing.open_epoch(conn)
    ledger.append(conn, "observation_created", _obs(2))
    _drop_protection(conn)
    conn.execute(
        "UPDATE event_log SET payload = ? WHERE id = 1",
        (sealing.canonical_payload(_obs(777)),),
    )

    issues = sealing.verify_chain(conn)

    assert any("genesis digest mismatch" in issue for issue in issues)


def test_missing_seal_after_epoch_is_detected(conn):
    _fill_sealed(conn, 2)
    conn.execute(
        "INSERT INTO event_log (event_type, payload) VALUES (?, ?)",
        ("observation_created", sealing.canonical_payload(_obs(5))),
    )

    issues = sealing.verify_chain(conn)

    assert any("missing a seal" in issue for issue in issues)


def test_adaptive_tampering_is_not_detected_locally(conn):
    _fill_sealed(conn, 3)
    meta = json.loads(sealing.epoch_event(conn)["payload"])
    genesis = meta["genesis_digest"]
    prefix_max_id = meta["prefix_max_id"]
    target = _first_real_sealed_id(conn)
    _drop_protection(conn)
    conn.execute(
        "UPDATE event_log SET payload = ? WHERE id = ?",
        (sealing.canonical_payload(_obs(424242)), target),
    )

    prev = genesis
    for row in conn.execute(
        """
        SELECT id, event_type, payload
        FROM event_log
        WHERE id > ?
        ORDER BY id
        """,
        (prefix_max_id,),
    ).fetchall():
        new_seal = sealing.compute_seal(prev, row["event_type"], row["payload"])
        conn.execute(
            "UPDATE event_log SET prev_seal = ?, seal = ? WHERE id = ?",
            (prev, new_seal, row["id"]),
        )
        prev = new_seal

    assert sealing.verify_chain(conn) == []


def test_end_truncation_is_not_detected_locally(conn):
    _fill_sealed(conn, 4)
    _drop_protection(conn)
    last = conn.execute("SELECT MAX(id) AS id FROM event_log").fetchone()["id"]
    conn.execute("DELETE FROM event_log WHERE id = ?", (last,))

    assert sealing.verify_chain(conn) == []


def test_replay_is_deterministic_with_sealing(conn):
    _fill_sealed(conn, 3)
    projections_before = integrity.snapshot_projections(conn)
    events_before = [
        tuple(row)
        for row in conn.execute(
            """
            SELECT id, event_type, payload, created_at, prev_seal, seal
            FROM event_log
            ORDER BY id
            """
        ).fetchall()
    ]

    event_router.replay(conn)

    projections_after = integrity.snapshot_projections(conn)
    events_after = [
        tuple(row)
        for row in conn.execute(
            """
            SELECT id, event_type, payload, created_at, prev_seal, seal
            FROM event_log
            ORDER BY id
            """
        ).fetchall()
    ]
    assert projections_after == projections_before
    assert events_after == events_before


def test_reseal_repairs_a_forked_chain(conn):
    _fill_sealed(conn, 4)
    _drop_protection(conn)
    ids = [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM event_log WHERE seal IS NOT NULL ORDER BY id"
        ).fetchall()
    ]
    # simulate a concurrency fork: a later event points at the wrong predecessor seal
    conn.execute("UPDATE event_log SET prev_seal = 'forked' WHERE id = ?", (ids[2],))
    assert any("prev_seal mismatch" in i for i in sealing.verify_chain(conn))

    before = [
        tuple(r)
        for r in conn.execute(
            "SELECT id, event_type, payload, created_at FROM event_log ORDER BY id"
        ).fetchall()
    ]
    n = sealing.reseal(conn)

    assert n >= 4
    assert sealing.verify_chain(conn) == []  # the chain is repaired
    after = [
        tuple(r)
        for r in conn.execute(
            "SELECT id, event_type, payload, created_at FROM event_log ORDER BY id"
        ).fetchall()
    ]
    assert after == before  # only the seals changed -- content and order untouched

    raised = False  # reseal restores the append-only protection it had to lift
    try:
        conn.execute("UPDATE event_log SET payload = 'x' WHERE id = ?", (ids[0],))
    except Exception:
        raised = True
    assert raised


def test_ledger_sealing_cli(monkeypatch, cli_conn, conn):
    monkeypatch.setattr(cli, "get_conn", lambda: cli_conn)
    runner = CliRunner()

    init = runner.invoke(cli.main, ["ledger", "seal-init"])
    head = runner.invoke(cli.main, ["ledger", "head"])
    verify = runner.invoke(cli.main, ["ledger", "verify"])
    second_init = runner.invoke(cli.main, ["ledger", "seal-init"])

    assert init.exit_code == 0
    assert "epoch opened" in init.output
    assert head.exit_code == 0
    assert "head=" in head.output
    assert verify.exit_code == 0
    assert "OK chain intact" in verify.output
    assert second_init.exit_code == 0
    assert "already initialized" in second_init.output
