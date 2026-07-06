"""Der MOTOR-STATUS (Ronny 2026-07-06, P2.1): die Denk-Motor-Zustandskarte als lebendiges,
deterministisches Read-time-Instrument -- je Denkweise gelernt-vs-Saat + Feuer-Rate. Schreibt
nichts, benennt die unvermessenen Denkweisen ehrlich statt eine Zahl zu erfinden."""
import json

from genus import inference, motor, verstehen


def _text(conn):
    return "\n".join(motor.narrate(conn))


def _seed_kalibrierung(conn, key, pattern):
    """Eine Kalibrierungs-Erfahrung direkt säen (wie sie der periodische Scan schriebe), damit
    stored_* sie liest -- ohne die schwere Cross-Prädikat-Rechnung nachzustellen."""
    conn.execute(
        "INSERT INTO experience_log (experience_key, experience_type, subject_key, pattern, "
        "derivation, summary) VALUES (?, 'RuleCalibration', 'motor:test', ?, 'test', 'test')",
        (key, json.dumps(pattern)),
    )
    conn.commit()


def test_leerer_graph_rendert_alle_abschnitte_ohne_absturz(conn):
    t = _text(conn)
    for kopf in ("SCHLIESSEN", "GESCHLECHT", "ERHOLUNG", "VERSTEHEN", "VERMUTEN",
                 "GLAUBEN-STABILITÄT", "MOTOR-AUSSTOSS", "UNVERMESSEN"):
        assert kopf in t, kopf
    assert "noch nicht selbst-kalibriert" in t          # leer -> Kalibrierungen auf Saat
    z = motor.zustand(conn)
    assert z["vermuten"]["stehende_vermutungen"] == 0
    assert z["verstehen"]["belegte_blaetter"] == 0
    assert z["erholung"]["reboot_ausgeloest"] == 0


def test_jede_zeile_traegt_das_praefix(conn):
    for line in motor.narrate(conn):
        assert line.startswith("[MOT]")


def test_report_ist_read_time_und_deterministisch(conn):
    tabellen = ("event_log", "experience_log", "proposal_log", "inquiry_log", "relation_projection")

    def snap():
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tabellen}

    vorher = snap()
    a = motor.narrate(conn)
    b = motor.narrate(conn)
    assert a == b                       # deterministisch, Zeile für Zeile
    assert snap() == vorher             # schreibt NICHTS (Report darf den Ledger nie verändern)


def test_transitivitaet_zeigt_saat_dann_gelernt(conn):
    z0 = motor.zustand(conn)
    assert z0["schliessen"]["transitivitaet"]["lage"] == "saat"   # nichts kalibriert
    _seed_kalibrierung(conn, inference.TRANSITIVITY_CALIBRATION_KEY, {"threshold": 7})
    z1 = motor.zustand(conn)
    assert z1["schliessen"]["transitivitaet"]["lage"] == "gelernt"
    assert z1["schliessen"]["transitivitaet"]["wert"] == 7
    assert "aus der natürlichen Lücke" in _text(conn)


def test_kalibrierung_gleich_der_saat_wird_als_bestaetigt_gelesen(conn):
    _seed_kalibrierung(conn, inference.TRANSITIVITY_CALIBRATION_KEY,
                       {"threshold": inference.MIN_VINDICATIONS})
    z = motor.zustand(conn)
    assert z["schliessen"]["transitivitaet"]["lage"] == "bestaetigt"
    assert "gleich der Saat" in _text(conn)


def test_geschlecht_ruckfall_auf_saat_ist_nicht_bestaetigt(conn):
    # der SEED==LEARNED-Fallstrick: der Geschlechts-Schnitt liefert IMMER einen Wert (0.80 als
    # Rückfall bei leerer Population) -- das darf NICHT als „durch die Daten bestätigt" gelesen
    # werden. Leer -> Lage „saat", nicht „bestaetigt".
    z = motor.zustand(conn)
    assert z["geschlecht"]["lage"] == "saat"
    assert z["geschlecht"]["population"] == 0
    assert "noch nicht selbst-kalibriert" in _text(conn)


def test_belegung_aggregiert_verstehen_je_herkunft_retraktions_bewusst(conn):
    for _ in range(3):
        verstehen.record_reading(conn, "definition", "muster")   # 3x dasselbe Blatt/Herkunft
    verstehen.record_reading(conn, "ursache", "model:deuter")     # ein anderes Blatt
    z = motor.zustand(conn)
    assert z["verstehen"]["belegung_je_quelle"]["muster"] == 3    # zählt JEDES Lesen (kein Dedup)
    assert z["verstehen"]["belegung_je_quelle"]["model:deuter"] == 1
    assert z["verstehen"]["belegte_blaetter"] == 2                # zwei Blätter je gefeuert
    assert "muster: 3" in _text(conn)


def test_stehende_vermutungen_werden_gezaehlt(conn):
    from genus import hypothese, reactors
    reactors.sae_fehlende(conn, [("Q1", "is_a", "Q2")], hypothese.MODEL_QUELLE)
    z = motor.zustand(conn)
    assert z["vermuten"]["stehende_vermutungen"] == 1


def test_recharakterisierungen_werden_nach_typ_getrennt(conn):
    # Review-Fund (MEDIUM): das eine experience_recharacterized-Event trägt Kalibrierungs- UND
    # BeliefStability-Neubewertungen. Ungetrennt läse eine stabil↔volatil-Kippung (der reale
    # v1.13-Fall) als Kalibrierungs-Feuer unter SCHLIESSEN. Sie müssen nach experience_key trennen.
    from genus import ledger
    ledger.append(conn, "experience_recharacterized",
                  {"experience_key": "rule_calibration:transitivity", "reason": "t"})
    ledger.append(conn, "experience_recharacterized",
                  {"experience_key": "belief_stability:system.thermal", "reason": "t"})
    z = motor.zustand(conn)
    assert z["schliessen"]["recharakterisierungen"] == 1          # NUR die Kalibrierung
    assert z["glauben_stabilitaet"]["recharakterisierungen"] == 1  # NUR die Stabilität


def test_unvermessene_denkweisen_werden_benannt_nicht_erfunden(conn):
    # die ehrliche Decke: Denkweisen ohne Spur werden NAMENTLICH genannt, nie mit Zahl geschönt
    t = _text(conn)
    for name in ("Subsumtion", "Modus Ponens", "Schließen im Betrieb", "Quellen-Vertrauen"):
        assert name in t, name
    # Regressions-Wächter (Review-Fund LOW): NICHT behaupten, nur der Deuter-Pfad hinterlasse eine
    # Spur -- der Muster-Dispatch (Quelle »muster«) speist die Belegung genauso.
    assert "nur der Deuter-Pfad" not in t
