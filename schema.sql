CREATE TABLE IF NOT EXISTS event_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT    NOT NULL,
    payload     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_event_log_type ON event_log(event_type);
CREATE INDEX IF NOT EXISTS idx_event_log_created ON event_log(created_at);

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
