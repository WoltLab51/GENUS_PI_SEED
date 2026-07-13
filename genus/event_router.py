"""Der Event-Router: EIN Nachschlagen statt einer if/elif-Kette (Phase 1 der Ziel-Architektur).

Jeder Event-Typ im System läuft hier durch -- beim Replay und nirgendwo sonst (der
Live-Schreibpfad wendet seine Projektion direkt an, immer als Paar mit ``ledger.append``).
Vorher war die Zuordnung Event-Typ -> Projektor eine ~20-zweigige if/elif-Kette: ein neuer
Event-Typ hieß, DIESE Datei zu editieren, obwohl das Verhalten ganz im Zielmodul wohnt.
Jetzt ist sie ein Register (``PROJEKTOREN``), das erste Kern-Register nach dem Vorbild von
``werkzeug.REGISTRY``: registrieren -> prüfen -> nachschlagen.

Zwei Mengen, beide ausdrücklich:

- ``PROJEKTOREN``: Event-Typ -> Projektor-Funktion. Neue Typen kommen über
  ``registriere_projektor`` dazu (Tippfehler-Schutz: der Vertragstest in
  ``tests/test_event_vertrag.py`` prüft jeden Schlüssel gegen die tatsächlich
  geschriebenen Event-Typen).
- ``BEWUSST_ROH``: Event-Typen, die MIT ABSICHT keine Projektion haben (rohe Fakten,
  zur Lesezeit frisch berechnet -- z.B. Prognosen; oder reine Protokoll-Marker). Ohne
  diese Menge wäre "vergessen zu registrieren" von "bewusst roh" nicht unterscheidbar --
  genau die Lücke, die der Replay-Determinismus-Test allein NICHT fängt (beide Seiten
  wären sich einig und grün; aktueller Vertrag: docs/EVENT_CONTRACT.md;
  historische Entwurfsherkunft: Naht 3 in
  docs/history/TARGET_ARCHITECTURE_2026-07-04.md §8).

Der Vertragstest erzwingt: jeder je geschriebene Event-Typ steht in GENAU EINER der
beiden Mengen. Ein neuer Event-Typ ohne Entscheidung (projiziert oder roh?) bricht CI.
"""
from __future__ import annotations

import json
from functools import wraps
from typing import Callable

from genus import (
    experience,
    governance,
    inquiries,
    maturation,
    operation,
    projection,
    proposals,
    state,
)


def _mit_source_event(fn: Callable) -> Callable:
    """Adapter für die operation-Projektoren, die historisch ``_source_event`` erwarten
    (der Live-Schreibpfad setzt es auf die echte Event-Id; beim Replay ist das
    ``_event_id``). Verhalten-erhaltend aus der alten Kette übernommen."""
    @wraps(fn)
    def wrapped(conn, payload: dict) -> None:
        payload["_source_event"] = payload["_event_id"]
        fn(conn, payload)
    return wrapped


# Das Kern-Register (aktueller Vertrag: docs/ARCHITECTURE.md §3; historische
# Entwurfsherkunft: docs/history/TARGET_ARCHITECTURE_2026-07-04.md §4) -- diese
# Projektoren müssen stehen, BEVOR ein Replay laufen kann; alles Weitere registriert sich
# über registriere_projektor.
PROJEKTOREN: dict[str, Callable] = {
    "evidence_recorded": projection.apply_evidence_recorded,
    "assertion_recorded": projection.apply_assertion_recorded,
    "belief_created": projection.apply_belief_created,
    "belief_confirmed": projection.apply_belief_confirmed,
    "belief_weakened": projection.apply_belief_weakened,
    "belief_superseded": projection.apply_belief_superseded,
    "relation_asserted": projection.apply_relation_asserted,
    "relation_retracted": projection.apply_relation_retracted,
    "proposal_created": proposals.apply_proposal_created,
    "proposal_reviewed": proposals.apply_proposal_reviewed,
    "experience_recorded": experience.apply_experience_recorded,
    "experience_recharacterized": experience.apply_experience_recharacterized,
    "state_changed": state.apply_state_changed,
    "governance_decision": governance.apply_governance_decision,
    "operation_check_recorded": _mit_source_event(operation.apply_operation_check_recorded),
    "operation_recovery_attempted": _mit_source_event(operation.apply_operation_recovery_attempted),
    "operation_recovery_result": operation.apply_operation_recovery_result,
    "rule_activated": maturation.apply_rule_activated,
    "inquiry_created": inquiries.apply_inquiry_created,
    "inquiry_resolved": inquiries.apply_inquiry_resolved,
    "inquiries_reconciled": inquiries.apply_inquiries_reconciled,
}

# Maschinenlesbarer Wirkungsvertrag: Ein Event ist erst dann vollständig kartiert,
# wenn neben seinem Replay-Projektor auch die persistierte Zielsicht benannt ist.
# Die Reihenfolge der Ziele ist absichtlich irrelevant; die Replay-Reihenfolge unten
# bleibt separat und explizit, weil Löschreihenfolgen ein Betriebsdetail sind.
PROJEKTIONSZIELE: dict[str, frozenset[str]] = {
    "evidence_recorded": frozenset({"value_projection"}),
    "assertion_recorded": frozenset({"value_projection"}),
    "belief_created": frozenset({"belief_projection"}),
    "belief_confirmed": frozenset({"belief_projection"}),
    "belief_weakened": frozenset({"belief_projection"}),
    "belief_superseded": frozenset({"belief_projection"}),
    "relation_asserted": frozenset({"relation_projection"}),
    "relation_retracted": frozenset({"relation_projection"}),
    "proposal_created": frozenset({"proposal_log"}),
    "proposal_reviewed": frozenset({"proposal_log"}),
    "experience_recorded": frozenset({"experience_log"}),
    "experience_recharacterized": frozenset({"experience_log"}),
    "state_changed": frozenset({"state_projection"}),
    "governance_decision": frozenset({"governance_log"}),
    "operation_check_recorded": frozenset({"operation_log"}),
    "operation_recovery_attempted": frozenset({"operation_log"}),
    "operation_recovery_result": frozenset({"operation_log"}),
    "rule_activated": frozenset({"rule_projection"}),
    "inquiry_created": frozenset({"inquiry_log"}),
    "inquiry_resolved": frozenset({"inquiry_log"}),
    "inquiries_reconciled": frozenset({"inquiry_log"}),
}

REPLAY_PROJEKTIONSTABELLEN: tuple[str, ...] = (
    "rule_projection",
    "governance_log",
    "operation_log",
    "inquiry_log",
    "proposal_log",
    "experience_log",
    "state_projection",
    "belief_projection",
    "relation_projection",
    "value_projection",
)

# Bewusst OHNE Projektion -- jede Zeile mit ihrem Grund:
BEWUSST_ROH: frozenset[str] = frozenset({
    "observation_created",     # roher Beobachtungs-Marker; Werte leben in value_projection
    "contradiction_detected",  # Protokoll-Marker; die Folge (Inquiry) hat ihre eigene Projektion
    "constraint_checked",      # Governance-Spur; die Entscheidung selbst wird projiziert
    "policy_evaluated",        # dito
    "forecast_made",           # Prognosen werden zur Lesezeit frisch berechnet (learning.py)
    "forecast_scored",         # dito
    "rule_proposed",           # der Vorschlag läuft als proposal_created; dies ist die Reifungs-Spur
    "ledger_epoch_opened",     # der Siegel-Epochen-Marker (sealing.py) -- Kette, kein Zustand
    "werkzeug_registriert",    # die Registrierungs-ENTSCHEIDUNG (Phase 3 Scheibe 2); die
                               # Laufzeit-Registry wird aus Code neu gebaut, nicht projiziert
    "proposal_umgesetzt",      # Ausführungs-Spur von Stufe 1 (genus/umsetzung.py); die
                               # WIRKUNG sind normale, projizierte relation_asserted-Events
    "code_entwurf_erstellt",   # Werkstatt-Spur (Stufe 2): der Code selbst ist Randmaterial,
    "code_entwurf_geprueft",   # nur die Entscheidung/Prüfung wird Geschichte
    "hand_vorgeschlagen",      # die HÄNDE (genus/hand.py): der Zustand einer Außenhandlung lebt
    "hand_bestaetigt",         # rein als Ereignis-Projektion (read-time, kein Nebentisch) --
    "hand_ausgefuehrt",        # Vorschlag -> menschliches OK -> genau-einmal-Ausführung, jede
    "hand_abgelehnt",          # Stufe ein Ledger-Ereignis (harter §8-Gate + volle Prüf-Spur)
})


def registriere_projektor(
    event_type: str,
    fn: Callable,
    *,
    targets: frozenset[str],
) -> None:
    """Trägt Projektor UND persistierte Ziele atomar in den Wirkungsvertrag ein.

    Idempotent für dieselbe Funktion und dieselben Ziele; ein abweichender Eintrag ist
    ein Konstruktionsfehler. Neue Zieltabellen müssen zuerst Teil der expliziten
    Replay-Leerliste werden -- sonst wäre der neue Projektor nicht replaybar.
    """
    if not targets:
        raise ValueError(f"Projektor für '{event_type}' braucht mindestens ein Projektionsziel")
    unbekannte_ziele = targets - set(REPLAY_PROJEKTIONSTABELLEN)
    if unbekannte_ziele:
        raise ValueError(
            f"Projektionsziele für '{event_type}' fehlen in der Replay-Leerliste: "
            f"{sorted(unbekannte_ziele)}"
        )
    bestehend = PROJEKTOREN.get(event_type)
    if bestehend is not None and bestehend is not fn:
        raise ValueError(
            f"Projektor für '{event_type}' ist schon registriert ({bestehend.__name__}); "
            f"stilles Überschreiben wäre ein verstecktes Verhalten"
        )
    if event_type in BEWUSST_ROH:
        raise ValueError(
            f"'{event_type}' ist als bewusst-roh deklariert -- erst dort austragen, "
            f"dann registrieren (eine Entscheidung, nicht zwei halbe)"
        )
    bestehende_ziele = PROJEKTIONSZIELE.get(event_type)
    if bestehende_ziele is not None and bestehende_ziele != targets:
        raise ValueError(
            f"Projektionsziele für '{event_type}' sind schon registriert: "
            f"{sorted(bestehende_ziele)}"
        )
    PROJEKTOREN[event_type] = fn
    PROJEKTIONSZIELE[event_type] = targets


def replay(conn, *, commit: bool = True) -> dict:
    """Rebuild every projection from the append-only event log.

    ``commit=False`` lets a caller keep the rebuild inside a wider transaction.  The CLI uses
    that mode so its before/replay/after idempotence check holds one SQLite writer gate from the
    first snapshot through the comparison; otherwise a Telegram or autonomous write can slip
    into the tiny gaps and create a false ``state changed after replay`` failure.
    """
    events = conn.execute("SELECT * FROM event_log ORDER BY id").fetchall()
    for table in REPLAY_PROJEKTIONSTABELLEN:
        conn.execute(f"DELETE FROM {table}")
    conn.execute(
        """
        DELETE FROM sqlite_sequence
        WHERE name IN (
            'rule_projection',
            'governance_log',
            'operation_log',
            'inquiry_log',
            'proposal_log',
            'experience_log',
            'state_projection',
            'belief_projection',
            'relation_projection'
        )
        """
    )

    for event in events:
        apply_event(conn, event)

    active_count = conn.execute(
        "SELECT COUNT(*) AS count FROM belief_projection WHERE state = 'active'"
    ).fetchone()["count"]
    proposal_count = conn.execute("SELECT COUNT(*) AS count FROM proposal_log").fetchone()[
        "count"
    ]
    inquiry_count = conn.execute("SELECT COUNT(*) AS count FROM inquiry_log").fetchone()[
        "count"
    ]
    experience_count = conn.execute(
        "SELECT COUNT(*) AS count FROM experience_log"
    ).fetchone()["count"]
    state_count = conn.execute(
        "SELECT COUNT(*) AS count FROM state_projection WHERE status = 'active'"
    ).fetchone()["count"]
    governance_count = conn.execute(
        "SELECT COUNT(*) AS count FROM governance_log"
    ).fetchone()["count"]
    operation_count = conn.execute(
        "SELECT COUNT(*) AS count FROM operation_log"
    ).fetchone()["count"]
    active_rule_count = conn.execute(
        "SELECT COUNT(*) AS count FROM rule_projection WHERE status = 'active'"
    ).fetchone()["count"]
    if commit:
        conn.commit()
    return {
        "events": len(events),
        "active_beliefs": int(active_count),
        "proposals": int(proposal_count),
        "inquiries": int(inquiry_count),
        "experiences": int(experience_count),
        "active_states": int(state_count),
        "governance_decisions": int(governance_count),
        "operations": int(operation_count),
        "active_rules": int(active_rule_count),
    }


def apply_event(conn, event) -> None:
    payload = json.loads(event["payload"])
    payload["_event_created_at"] = event["created_at"]
    payload["_event_id"] = event["id"]
    projektor = PROJEKTOREN.get(event["event_type"])
    if projektor is not None:
        projektor(conn, payload)
