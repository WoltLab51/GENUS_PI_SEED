import datetime as dt
import contextlib
import json
import os
import stat

import pytest
from click.testing import CliRunner

from genus import betriebsprofil, cli, db, ledger, sealing


UTC = dt.timezone.utc
T0 = dt.datetime(2026, 7, 13, 8, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _deterministic_thermometer(monkeypatch):
    monkeypatch.setattr(
        betriebsprofil.thermometer,
        "betriebsstand",
        lambda conn: {
            "generalisierung": {
                "absichten_auf_planer": ["a", "b"],
                "verkehr_ueber_planer": 0.5,
                "blaetter_gesaet": 4,
                "blaetter_handelbar": 3,
            },
            "luecken": {
                "blaetter_ohne_handler": ["tun"],
                "faehigkeiten_nicht_live": [],
            },
        },
    )


def _database(tmp_path):
    path = tmp_path / "genus.sqlite3"
    conn = db.connect(path)
    return path, conn


def _insert(conn, event_type, payload, created_at):
    conn.execute(
        "INSERT INTO event_log (event_type, payload, created_at) VALUES (?, ?, ?)",
        (event_type, json.dumps(payload), betriebsprofil.iso_utc(created_at)),
    )
    conn.commit()


def _snapshot(profile_dir, label):
    return json.loads((profile_dir / f"{label}.json").read_text(encoding="utf-8"))


def test_not_started_is_a_true_noop(tmp_path):
    db_path = tmp_path / "missing.sqlite3"
    profile_dir = tmp_path / "profile"

    result = betriebsprofil.capture_due(db_path, output_dir=profile_dir, now=T0)

    assert result == {"action": "not_started", "status": "not_started"}
    assert not profile_dir.exists()
    assert not db_path.exists()


def test_baseline_is_private_payload_free_and_does_not_write_the_ledger(tmp_path):
    db_path, conn = _database(tmp_path)
    profile_dir = tmp_path / "profile"
    _insert(
        conn,
        "observation_created",
        {
            "raw_value": "PRIVATE-MEMORY-CANARY",
            "source": "untrusted-source-CANARY",
            "unit": "text",
        },
        T0 - dt.timedelta(minutes=5),
    )
    before = conn.execute(
        "SELECT id, event_type, payload, created_at FROM event_log ORDER BY id"
    ).fetchall()

    result = betriebsprofil.capture_due(
        db_path, output_dir=profile_dir, start=True, now=T0
    )

    after = conn.execute(
        "SELECT id, event_type, payload, created_at FROM event_log ORDER BY id"
    ).fetchall()
    assert result["action"] == "captured" and result["label"] == "baseline"
    assert [tuple(row) for row in after] == [tuple(row) for row in before]
    text = (profile_dir / "baseline.json").read_text(encoding="utf-8")
    assert "PRIVATE-MEMORY-CANARY" not in text
    assert "untrusted-source-CANARY" not in text
    assert str(db_path) not in text
    snap = json.loads(text)
    assert snap["interval"]["source_families"]["other"] == 1
    assert sum(snap["interval"]["classification"].values()) == 1
    assert snap["privacy"]["payload_content_persisted"] is False
    assert betriebsprofil.profile_status(
        db_path, output_dir=profile_dir
    )["files_verified"] is True
    if os.name != "nt":
        assert stat.S_IMODE(profile_dir.stat().st_mode) == 0o700
        for name in ("baseline.json", "manifest.json", "run.lock"):
            assert stat.S_IMODE((profile_dir / name).stat().st_mode) == 0o600
    conn.close()


def test_schedule_captures_three_disjoint_head_id_intervals_once(tmp_path):
    db_path, conn = _database(tmp_path)
    profile_dir = tmp_path / "profile"
    baseline = betriebsprofil.capture_due(
        db_path, output_dir=profile_dir, start=True, now=T0
    )
    assert baseline["head_event_id"] == 0

    # Equal timestamps are deliberately retained: IDs, not timestamps, form the delta.
    _insert(
        conn,
        "observation_created",
        {"raw_value": 1, "source": "psutil.cpu_percent", "unit": "%"},
        T0 + dt.timedelta(hours=1),
    )
    _insert(
        conn,
        "evidence_recorded",
        {"metric_key": "system.load", "metric_value": 1, "observation_id": 1},
        T0 + dt.timedelta(hours=1),
    )
    assert betriebsprofil.capture_due(
        db_path, output_dir=profile_dir, now=T0 + dt.timedelta(hours=23)
    )["action"] == "not_due"

    h24 = betriebsprofil.capture_due(
        db_path, output_dir=profile_dir, now=T0 + dt.timedelta(hours=24)
    )
    assert h24["label"] == "h24" and h24["events_in_interval"] == 2
    assert betriebsprofil.capture_due(
        db_path, output_dir=profile_dir, now=T0 + dt.timedelta(hours=24)
    )["action"] == "not_due"

    _insert(
        conn,
        "assertion_recorded",
        {"claim_key": "x", "claim_value": 2, "derivation": "test", "source": "test"},
        T0 + dt.timedelta(hours=25),
    )
    h48 = betriebsprofil.capture_due(
        db_path, output_dir=profile_dir, now=T0 + dt.timedelta(hours=48)
    )
    h72 = betriebsprofil.capture_due(
        db_path, output_dir=profile_dir, now=T0 + dt.timedelta(hours=72)
    )
    assert h48["events_in_interval"] == 1
    assert h72["events_in_interval"] == 0
    assert betriebsprofil.capture_due(
        db_path, output_dir=profile_dir, now=T0 + dt.timedelta(hours=73)
    )["action"] == "complete"

    assert _snapshot(profile_dir, "h24")["interval"]["start_head_exclusive"] == 0
    assert _snapshot(profile_dir, "h48")["interval"]["start_head_exclusive"] == 2
    assert _snapshot(profile_dir, "h72")["interval"]["start_head_exclusive"] == 3
    manifest = json.loads((profile_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert [item["label"] for item in manifest["captures"]] == [
        "baseline",
        "h24",
        "h48",
        "h72",
    ]
    conn.close()


def test_late_capture_is_marked_and_normalized_by_actual_elapsed_time(tmp_path):
    db_path, conn = _database(tmp_path)
    profile_dir = tmp_path / "profile"
    betriebsprofil.capture_due(db_path, output_dir=profile_dir, start=True, now=T0)
    _insert(
        conn,
        "assertion_recorded",
        {"claim_key": "x", "claim_value": 1, "derivation": "test", "source": "test"},
        T0 + dt.timedelta(hours=24, minutes=30),
    )

    result = betriebsprofil.capture_due(
        db_path, output_dir=profile_dir, now=T0 + dt.timedelta(hours=26)
    )
    snap = _snapshot(profile_dir, "h24")

    assert result["late_by_seconds"] == 2 * 3600
    assert snap["interval"]["elapsed_seconds"] == 26 * 3600
    assert snap["interval"]["events_per_24h_normalized"] == 0.9
    conn.close()


def test_missed_schedule_point_aborts_instead_of_compressing_windows(tmp_path):
    db_path, conn = _database(tmp_path)
    profile_dir = tmp_path / "profile"
    betriebsprofil.capture_due(db_path, output_dir=profile_dir, start=True, now=T0)

    missed = betriebsprofil.capture_due(
        db_path, output_dir=profile_dir, now=T0 + dt.timedelta(hours=100)
    )

    assert missed["action"] == "aborted_missed"
    assert missed["missed_label"] == "h24"
    assert not (profile_dir / "h24.json").exists()
    assert betriebsprofil.capture_due(
        db_path, output_dir=profile_dir, now=T0 + dt.timedelta(hours=101)
    ) == {"action": "aborted", "status": "aborted"}
    status = betriebsprofil.profile_status(db_path, output_dir=profile_dir)
    assert status["status"] == "aborted"
    assert status["next_label"] is None
    conn.close()


def test_similarity_repetition_is_canonical_but_changed_weight_is_new(tmp_path):
    db_path, conn = _database(tmp_path)
    profile_dir = tmp_path / "profile"
    for subject, object_, derivation in (
        ("A", "B", "cos=0.7000"),
        ("B", "A", "cos=0.7000"),
        ("A", "B", "cos=0.8000"),
    ):
        _insert(
            conn,
            "relation_asserted",
            {
                "subject": subject,
                "predicate": "verwandt",
                "object": object_,
                "source": "model:embedder",
                "derivation": derivation,
            },
            T0 - dt.timedelta(minutes=1),
        )

    betriebsprofil.capture_due(db_path, output_dir=profile_dir, start=True, now=T0)
    interval = _snapshot(profile_dir, "baseline")["interval"]

    assert interval["classification"] == {
        "betriebsspur": 0,
        "erkenntnis": 2,
        "unklar": 0,
        "vermeidbare_wiederholung": 1,
    }
    assert interval["source_families"] == {"model": 3}
    conn.close()


def test_similarity_repetition_crosses_capture_boundaries(tmp_path):
    db_path, conn = _database(tmp_path)
    profile_dir = tmp_path / "profile"
    relation = {
        "subject": "A",
        "predicate": "verwandt",
        "object": "B",
        "source": "model:embedder",
        "derivation": "cos=0.7000",
    }
    _insert(conn, "relation_asserted", relation, T0 - dt.timedelta(minutes=1))
    betriebsprofil.capture_due(db_path, output_dir=profile_dir, start=True, now=T0)
    _insert(conn, "relation_asserted", relation, T0 + dt.timedelta(hours=1))

    betriebsprofil.capture_due(
        db_path, output_dir=profile_dir, now=T0 + dt.timedelta(hours=24)
    )
    classification = _snapshot(profile_dir, "h24")["interval"]["classification"]

    assert classification == {
        "betriebsspur": 0,
        "erkenntnis": 0,
        "unklar": 0,
        "vermeidbare_wiederholung": 1,
    }
    conn.close()


def test_invalid_relations_cannot_inflate_classification_sum(tmp_path):
    db_path, conn = _database(tmp_path)
    profile_dir = tmp_path / "profile"
    invalid = {
        "subject": "A",
        "predicate": "verwandt",
        "object": "B",
        "source": "model:embedder",
        # required derivation deliberately missing
    }
    _insert(conn, "relation_asserted", invalid, T0 - dt.timedelta(minutes=1))
    _insert(conn, "relation_asserted", invalid, T0 - dt.timedelta(minutes=1))

    betriebsprofil.capture_due(db_path, output_dir=profile_dir, start=True, now=T0)
    interval = _snapshot(profile_dir, "baseline")["interval"]

    assert interval["event_count"] == 2
    assert interval["classification"]["unklar"] == 2
    assert interval["classification"]["vermeidbare_wiederholung"] == 0
    assert sum(interval["classification"].values()) == interval["event_count"]
    conn.close()


def test_untrusted_and_future_timestamps_never_enter_baseline_or_output(tmp_path):
    db_path, conn = _database(tmp_path)
    profile_dir = tmp_path / "profile"
    payload = json.dumps({"raw_value": 1, "source": "sensor", "unit": "%"})
    conn.execute(
        "INSERT INTO event_log (event_type, payload, created_at) VALUES (?, ?, ?)",
        ("observation_created", payload, "PRIVATE-TIMESTAMP-CANARY"),
    )
    conn.execute(
        "INSERT INTO event_log (event_type, payload, created_at) VALUES (?, ?, ?)",
        ("observation_created", payload, "2026-07-13 07:00:00"),
    )
    conn.execute(
        "INSERT INTO event_log (event_type, payload, created_at) VALUES (?, ?, ?)",
        ("observation_created", payload, "2026-02-30T00:00:00.000Z"),
    )
    conn.execute(
        "INSERT INTO event_log (event_type, payload, created_at) VALUES (?, ?, ?)",
        ("observation_created", payload, "2026-07-13T24:00:00.000Z"),
    )
    conn.execute(
        "INSERT INTO event_log (event_type, payload, created_at) VALUES (?, ?, ?)",
        (
            "observation_created",
            payload,
            betriebsprofil.iso_utc(T0 + dt.timedelta(days=365)),
        ),
    )
    conn.commit()

    betriebsprofil.capture_due(db_path, output_dir=profile_dir, start=True, now=T0)
    text = (profile_dir / "baseline.json").read_text(encoding="utf-8")
    snap = json.loads(text)

    assert "PRIVATE-TIMESTAMP-CANARY" not in text
    assert snap["interval"]["event_count"] == 0
    assert snap["ledger"]["head_created_at"] is not None
    assert snap["ledger"]["first_created_at"] is None
    assert snap["data_quality"]["invalid_timestamp_events"] == 4
    assert snap["data_quality"]["future_timestamp_events"] == 1
    assert snap["data_quality"]["scope"] == "full_ledger_at_capture"
    conn.close()


def test_future_timestamp_in_id_delta_is_unklar_and_bounded(tmp_path):
    db_path, conn = _database(tmp_path)
    profile_dir = tmp_path / "profile"
    betriebsprofil.capture_due(db_path, output_dir=profile_dir, start=True, now=T0)
    _insert(
        conn,
        "assertion_recorded",
        {"claim_key": "x", "claim_value": 1, "derivation": "test", "source": "test"},
        T0 + dt.timedelta(days=365),
    )

    betriebsprofil.capture_due(
        db_path, output_dir=profile_dir, now=T0 + dt.timedelta(hours=24)
    )
    snap = _snapshot(profile_dir, "h24")

    assert snap["interval"]["event_count"] == 1
    assert snap["interval"]["classification"]["unklar"] == 1
    assert snap["interval"]["hourly_utc"] == [
        {"events": 1, "hour_utc": "after_window"}
    ]
    conn.close()


def test_unknown_invalid_event_never_leaks_its_type_or_payload(tmp_path):
    db_path, conn = _database(tmp_path)
    profile_dir = tmp_path / "profile"
    conn.execute(
        "INSERT INTO event_log (event_type, payload, created_at) VALUES (?, ?, ?)",
        ("PRIVATE-EVENT-CANARY", "PRIVATE-PAYLOAD-CANARY", betriebsprofil.iso_utc(T0)),
    )
    conn.commit()

    betriebsprofil.capture_due(db_path, output_dir=profile_dir, start=True, now=T0)
    text = (profile_dir / "baseline.json").read_text(encoding="utf-8")
    snap = json.loads(text)

    assert "PRIVATE-EVENT-CANARY" not in text
    assert "PRIVATE-PAYLOAD-CANARY" not in text
    assert snap["ledger"]["head_event_type"] == "unknown"
    assert snap["interval"]["event_types"] == {"unknown": 1}
    assert snap["interval"]["classification"]["unklar"] == 1
    assert snap["data_quality"]["invalid_json_events"] == 1
    conn.close()


def test_snapshot_hash_mismatch_stops_status_and_future_capture(tmp_path):
    db_path, conn = _database(tmp_path)
    profile_dir = tmp_path / "profile"
    betriebsprofil.capture_due(db_path, output_dir=profile_dir, start=True, now=T0)
    (profile_dir / "baseline.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(betriebsprofil.ProfileError, match="hash mismatch"):
        betriebsprofil.profile_status(db_path, output_dir=profile_dir)
    with pytest.raises(betriebsprofil.ProfileError, match="hash mismatch"):
        betriebsprofil.capture_due(
            db_path, output_dir=profile_dir, now=T0 + dt.timedelta(hours=24)
        )
    conn.close()


def test_missing_snapshot_and_malformed_manifest_fail_closed(tmp_path):
    db_path, conn = _database(tmp_path)
    profile_dir = tmp_path / "profile"
    betriebsprofil.capture_due(db_path, output_dir=profile_dir, start=True, now=T0)
    (profile_dir / "baseline.json").unlink()
    with pytest.raises(betriebsprofil.ProfileError, match="inspect profile evidence"):
        betriebsprofil.profile_status(db_path, output_dir=profile_dir)

    manifest = profile_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": betriebsprofil.SCHEMA_VERSION,
                "run_id": "h0-1-20260713T080000Z",
                "status": "running",
                "started_at": "2026-07-13T08:00:00.000Z",
                "schedule_hours": [0, 24, 48, 72],
                "captures": [{}],
                "methodology": betriebsprofil._methodology(),
            }
        ),
        encoding="utf-8",
    )
    if os.name != "nt":
        manifest.chmod(0o600)
    with pytest.raises(betriebsprofil.ProfileError, match="capture fields"):
        betriebsprofil.profile_status(db_path, output_dir=profile_dir)
    conn.close()


def test_replacing_the_database_aborts_continuity(tmp_path):
    db_path, conn = _database(tmp_path)
    profile_dir = tmp_path / "profile"
    _insert(
        conn,
        "observation_created",
        {"raw_value": 1, "source": "sensor", "unit": "%"},
        T0 - dt.timedelta(minutes=1),
    )
    betriebsprofil.capture_due(db_path, output_dir=profile_dir, start=True, now=T0)
    conn.close()

    replacement = tmp_path / "replacement.sqlite3"
    replacement_conn = db.connect(replacement)
    _insert(
        replacement_conn,
        "observation_created",
        {"raw_value": 2, "source": "sensor", "unit": "%"},
        T0 + dt.timedelta(hours=1),
    )
    replacement_conn.close()
    os.replace(replacement, db_path)

    with pytest.raises(betriebsprofil.ProfileError, match="replaced"):
        betriebsprofil.capture_due(
            db_path, output_dir=profile_dir, now=T0 + dt.timedelta(hours=24)
        )


def test_changed_unsealed_prefix_aborts_continuity(tmp_path):
    db_path, conn = _database(tmp_path)
    profile_dir = tmp_path / "profile"
    _insert(
        conn,
        "observation_created",
        {"raw_value": 1, "source": "sensor", "unit": "%"},
        T0 - dt.timedelta(minutes=1),
    )
    betriebsprofil.capture_due(db_path, output_dir=profile_dir, start=True, now=T0)
    conn.execute("DROP TRIGGER prevent_event_log_update")
    conn.execute("UPDATE event_log SET payload = ? WHERE id = 1", (json.dumps({"x": 1}),))
    conn.commit()

    with pytest.raises(betriebsprofil.ProfileError, match="prefix changed"):
        betriebsprofil.capture_due(
            db_path, output_dir=profile_dir, now=T0 + dt.timedelta(hours=24)
        )
    conn.close()


@pytest.mark.parametrize("tamper", ["payload", "created_at"])
def test_changed_sealed_prefix_aborts_continuity(tmp_path, tamper):
    db_path, conn = _database(tmp_path)
    profile_dir = tmp_path / "profile"
    sealing.open_epoch(conn)
    event_id = ledger.append(
        conn,
        "observation_created",
        {"raw_value": 1, "source": "sensor", "unit": "%"},
    )
    conn.commit()
    betriebsprofil.capture_due(db_path, output_dir=profile_dir, start=True, now=T0)
    conn.execute("DROP TRIGGER prevent_event_log_update")
    if tamper == "payload":
        conn.execute(
            "UPDATE event_log SET payload = ? WHERE id = ?",
            (json.dumps({"raw_value": 999}), event_id),
        )
    else:
        conn.execute(
            "UPDATE event_log SET created_at = ? WHERE id = ?",
            (betriebsprofil.iso_utc(T0 - dt.timedelta(days=1)), event_id),
        )
    conn.commit()

    with pytest.raises(betriebsprofil.ProfileError, match="prefix changed"):
        betriebsprofil.capture_due(
            db_path, output_dir=profile_dir, now=T0 + dt.timedelta(hours=24)
        )
    conn.close()


def test_snapshot_without_manifest_is_never_silently_overwritten(tmp_path):
    db_path, conn = _database(tmp_path)
    profile_dir = tmp_path / "profile"
    betriebsprofil.capture_due(db_path, output_dir=profile_dir, start=True, now=T0)
    baseline_before = (profile_dir / "baseline.json").read_bytes()
    (profile_dir / "manifest.json").unlink()

    with pytest.raises(betriebsprofil.ProfileError, match="without its manifest"):
        betriebsprofil.capture_due(db_path, output_dir=profile_dir, now=T0)
    with pytest.raises(betriebsprofil.ProfileError, match="without its manifest"):
        betriebsprofil.capture_due(
            db_path, output_dir=profile_dir, start=True, now=T0
        )
    assert (profile_dir / "baseline.json").read_bytes() == baseline_before
    conn.close()


def test_manifest_disappearing_before_lock_never_starts_a_cron_baseline(
    monkeypatch, tmp_path
):
    db_path, conn = _database(tmp_path)
    profile_dir = tmp_path / "profile"
    betriebsprofil.capture_due(db_path, output_dir=profile_dir, start=True, now=T0)
    real_lock = betriebsprofil._profile_lock

    @contextlib.contextmanager
    def deleting_lock(root):
        with real_lock(root):
            (profile_dir / "manifest.json").unlink()
            yield

    monkeypatch.setattr(betriebsprofil, "_profile_lock", deleting_lock)
    with pytest.raises(betriebsprofil.ProfileError, match="disappeared"):
        betriebsprofil.capture_due(
            db_path, output_dir=profile_dir, now=T0 + dt.timedelta(hours=24)
        )
    conn.close()


def test_naive_capture_time_is_rejected(tmp_path):
    db_path, conn = _database(tmp_path)
    with pytest.raises(betriebsprofil.ProfileError, match="timezone-aware"):
        betriebsprofil.capture_due(
            db_path,
            output_dir=tmp_path / "profile",
            start=True,
            now=dt.datetime(2026, 7, 13, 8, 0),
        )
    conn.close()


def test_profile_root_and_lock_symlinks_are_rejected(tmp_path):
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks unavailable")
    db_path, conn = _database(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    target.chmod(0o700)
    root_link = tmp_path / "profile-link"
    try:
        root_link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not permitted")
    with pytest.raises(betriebsprofil.ProfileError, match="real directory"):
        betriebsprofil.capture_due(
            db_path, output_dir=root_link, start=True, now=T0
        )

    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(mode=0o700)
    lock_target = tmp_path / "lock-target"
    lock_target.write_bytes(b"x")
    (profile_dir / "run.lock").symlink_to(lock_target)
    with pytest.raises(betriebsprofil.ProfileError, match="lock must not be a symlink"):
        betriebsprofil.capture_due(
            db_path, output_dir=profile_dir, start=True, now=T0
        )
    conn.close()


def test_profile_lock_rejects_a_concurrent_holder(tmp_path):
    profile_dir = tmp_path / "profile"
    betriebsprofil._ensure_private_dir(profile_dir)

    with betriebsprofil._profile_lock(profile_dir):
        with pytest.raises(betriebsprofil.ProfileError, match="already running"):
            with betriebsprofil._profile_lock(profile_dir):
                pass


def test_explicit_output_directory_expands_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    if os.name == "nt":
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

    root = betriebsprofil._profile_root(tmp_path / "genus.sqlite3", "~/private")

    assert root == tmp_path / "private"


@pytest.mark.parametrize(
    ("raw", "family"),
    [
        ("ronny", "owner_or_curated"),
        ("model:secret", "model"),
        ("psutil.cpu_percent", "local_sensor"),
        ("wikidata", "external_reference"),
        ("open-meteo", "external_weather"),
        ("muster", "deterministic_internal"),
        ("unknown-private-source", "other"),
        (None, "missing"),
    ],
)
def test_source_normalization_is_allowlisted(raw, family):
    assert betriebsprofil.normalize_source(raw) == family


def test_cli_start_fails_without_creating_a_database_or_profile(monkeypatch, tmp_path):
    db_path = tmp_path / "missing.sqlite3"
    profile_dir = tmp_path / "profile"
    monkeypatch.setenv("GENUS_DB_PATH", str(db_path))

    result = CliRunner().invoke(
        cli.main,
        ["betriebsprofil", "capture", "--start", "--output-dir", str(profile_dir)],
    )

    assert result.exit_code != 0
    assert "database does not exist" in result.output
    assert not db_path.exists()
    assert not profile_dir.exists()


def test_cli_missed_schedule_point_exits_nonzero(monkeypatch, tmp_path):
    db_path, conn = _database(tmp_path)
    profile_dir = tmp_path / "profile"
    betriebsprofil.capture_due(db_path, output_dir=profile_dir, start=True, now=T0)
    monkeypatch.setenv("GENUS_DB_PATH", str(db_path))

    monkeypatch.setattr(
        betriebsprofil,
        "utc_now",
        lambda: T0 + dt.timedelta(hours=100),
    )
    result = CliRunner().invoke(
        cli.main,
        ["betriebsprofil", "capture", "--quiet", "--output-dir", str(profile_dir)],
    )

    assert result.exit_code == 2
    assert "aborted: missed h24" in result.output
    conn.close()
