CREATE TABLE IF NOT EXISTS event_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT    NOT NULL,
    payload     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    prev_seal   TEXT,
    seal        TEXT
);

CREATE INDEX IF NOT EXISTS idx_event_log_type ON event_log(event_type);
CREATE INDEX IF NOT EXISTS idx_event_log_created ON event_log(created_at);
-- Evidence/metric lookups filter on event_type + the JSON metric_key; a partial
-- expression index keeps the rule and experience scans off a full table scan.
-- Partial on evidence_recorded (which always carries valid JSON), so the
-- json_extract is never evaluated for other event types.
CREATE INDEX IF NOT EXISTS idx_event_log_metric
    ON event_log(json_extract(payload, '$.metric_key'))
    WHERE event_type = 'evidence_recorded';

CREATE TRIGGER IF NOT EXISTS prevent_event_log_update
BEFORE UPDATE ON event_log
BEGIN
    SELECT RAISE(ABORT, 'event_log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS prevent_event_log_delete
BEFORE DELETE ON event_log
BEGIN
    SELECT RAISE(ABORT, 'event_log is append-only');
END;

CREATE TABLE IF NOT EXISTS belief_projection (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_key            TEXT    NOT NULL,
    claim_value          TEXT    NOT NULL,
    state                TEXT    NOT NULL,
    derivation           TEXT    NOT NULL,
    supporting_events    TEXT    NOT NULL DEFAULT '[]',
    contradicting_events TEXT    NOT NULL DEFAULT '[]',
    created_at           TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_updated_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    superseded_by        INTEGER REFERENCES belief_projection(id)
);

CREATE INDEX IF NOT EXISTS idx_belief_projection_claim
ON belief_projection(claim_key, claim_value, state);

CREATE TABLE IF NOT EXISTS proposal_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_type  TEXT    NOT NULL,
    claim_key      TEXT    NOT NULL,
    claim_value    TEXT    NOT NULL,
    source_belief  INTEGER REFERENCES belief_projection(id),
    source_event   INTEGER REFERENCES event_log(id),
    payload        TEXT    NOT NULL,
    state          TEXT    NOT NULL DEFAULT 'pending',
    decision       TEXT,
    reviewed_at    TEXT,
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_proposal_log_state ON proposal_log(state);

CREATE TABLE IF NOT EXISTS inquiry_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    inquiry_type   TEXT    NOT NULL,
    claim_key      TEXT    NOT NULL,
    source_belief  INTEGER REFERENCES belief_projection(id),
    source_event   INTEGER REFERENCES event_log(id),
    question_key   TEXT    NOT NULL,
    payload        TEXT    NOT NULL,
    state          TEXT    NOT NULL DEFAULT 'open',
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    answer         TEXT,
    resolved_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_inquiry_log_state ON inquiry_log(state);

CREATE TABLE IF NOT EXISTS experience_log (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    experience_key     TEXT    NOT NULL UNIQUE,
    experience_type    TEXT    NOT NULL,
    subject_key        TEXT    NOT NULL,
    pattern            TEXT    NOT NULL,
    supporting_events  TEXT    NOT NULL DEFAULT '[]',
    derivation         TEXT    NOT NULL,
    summary            TEXT    NOT NULL,
    created_at         TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_experience_log_subject
ON experience_log(subject_key, experience_type);

CREATE TABLE IF NOT EXISTS state_projection (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    state_key           TEXT    NOT NULL,
    state_value         TEXT    NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'active',
    derivation          TEXT    NOT NULL,
    supporting_beliefs  TEXT    NOT NULL DEFAULT '[]',
    components          TEXT    NOT NULL DEFAULT '{}',
    reason              TEXT    NOT NULL,
    created_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_updated_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    superseded_by       INTEGER REFERENCES state_projection(id)
);

CREATE INDEX IF NOT EXISTS idx_state_projection_key_status
ON state_projection(state_key, status);

CREATE TABLE IF NOT EXISTS rule_projection (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_key         TEXT    NOT NULL UNIQUE,
    rule_type        TEXT    NOT NULL,
    subject_key      TEXT    NOT NULL,
    spec             TEXT    NOT NULL,
    status           TEXT    NOT NULL DEFAULT 'active',
    source_proposal  INTEGER REFERENCES proposal_log(id),
    derivation       TEXT    NOT NULL,
    created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_rule_projection_type_status
ON rule_projection(rule_type, status);

CREATE TABLE IF NOT EXISTS operation_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_type  TEXT    NOT NULL,
    check_key       TEXT    NOT NULL,
    status          TEXT    NOT NULL,
    target          TEXT    NOT NULL,
    payload         TEXT    NOT NULL,
    derivation      TEXT    NOT NULL,
    source_event    INTEGER REFERENCES event_log(id),
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_updated_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_operation_log_check
ON operation_log(check_key, status);

CREATE TABLE IF NOT EXISTS governance_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action          TEXT    NOT NULL,
    target_type     TEXT    NOT NULL,
    target_id       INTEGER NOT NULL,
    decision        TEXT    NOT NULL,
    override        INTEGER NOT NULL DEFAULT 0,
    policy_results  TEXT    NOT NULL DEFAULT '[]',
    reason          TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_governance_log_target
ON governance_log(target_type, target_id);
