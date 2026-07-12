"""Das Selbstbild ist eine lesbare Projektion -- keine festgeschriebene Persona."""
from genus import ledger, projection, reactors, state, verstehen, ziele


def _belief(conn, key: str, value: str, derivation: str = "rule:test") -> None:
    event_id = ledger.append(conn, "evidence_recorded", {
        "observation_id": 1,
        "metric_key": key,
        "metric_value": 1.0,
    })
    projection.create_belief(conn, key, value, derivation, [event_id])


def test_stand_liest_identitaet_ziele_und_habitat_aus_den_wahrheitsflaechen(conn):
    from genus import selbstbild

    ziele.seed_ziele(conn)
    _belief(conn, "system.network", "healthy", "operation_check:v1")
    _belief(conn, "private.user.secret", "sichtbar")  # nie für die Oberfläche freigegeben
    state.record_state_changed_event(conn, {
        "state_key": state.STATE_KEY,
        "state_value": state.NOMINAL,
        "derivation": state.DERIVATION,
        "supporting_beliefs": [],
        "components": {},
        "reason": "test",
    })

    s = selbstbild.stand(conn)

    assert s["name"] == "GENUS" and s["version"]
    assert s["mission"] == "Menschen unterstützen. digital. GENUS."
    assert s["selbstbild_status"] == "teilweise"
    assert [(h["claim_key"], h["wert"], h["epistemisch"]) for h in s["habitat"]] == [
        ("system.network", "healthy", projection.SUPPORTED),
    ]
    assert s["systemzustand"]["wert"] == state.NOMINAL


def test_habitat_bericht_bleibt_ohne_sensorwissen_ehrlich(conn):
    from genus import selbstbild

    text = selbstbild.bericht(conn, aspekt="Habitat")

    assert "noch nicht ausreichend beobachtet" in text
    assert "rate ich nicht" in text


def test_widerspruechlicher_selbststatus_wird_nicht_lexikografisch_entschieden(conn):
    from genus import selbstbild

    ziele.seed_ziele(conn)
    reactors.observe_relation(conn, selbstbild.SELBST_FAEHIGKEIT, ziele.STATUS,
                              "live", "model:test")

    s = selbstbild.stand(conn)
    text = selbstbild.bericht(conn, aspekt="Identität")

    assert s["selbstbild_status"] is None
    assert s["selbstbild_status_konflikt"] is True
    assert "widersprüchlich" in text and "live" in text and "teilweise" in text


def test_die_beiden_live_fragen_landen_im_allgemeinen_selbstbild_blatt(conn):
    from genus import companion

    verstehen.seed_raster(conn)
    ziele.seed_ziele(conn)
    _belief(conn, "system.clock", "synchronized", "operation_check:v1")

    selbst = companion.respond_with_deuter(
        conn,
        "Was weißt du über dich selbst?",
        deuter=lambda q: {"absicht": "selbstbild", "subject": "Selbstbild", "object": None},
    )
    habitat = companion.respond_with_deuter(
        conn,
        "Kennt GENUS sein Habitat?",
        deuter=lambda q: {"absicht": "selbstbild", "subject": "Habitat", "object": None},
    )

    assert selbst["gelesen"] == ["selbstbild"]
    assert "Ich bin GENUS" in selbst["text"] and "Mission" in selbst["text"]
    assert habitat["gelesen"] == ["selbstbild"]
    assert "Uhr: synchronisiert" in habitat["text"]
    assert "physischer Standort" in habitat["text"]
