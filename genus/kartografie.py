"""Deterministische, quellengebundene Kartografie des GENUS-Systems.

Die Karte verbindet drei Wahrheiten, die vorher getrennt gepflegt wurden:

* aus dem Quellbaum abgeleitete Modul-, Import-, SQL- und Event-Abhängigkeiten,
* den expliziten Event -> Projektor -> Projektion-Vertrag,
* wenige kuratierte Wirkungskanten für Antwort, Lernen und Betrieb.

Kuratierte Kanten bleiben überprüfbar: jede trägt eine Fundstelle im Repository. Es
werden weder Live-Daten noch absolute Pfade, Benutzerkennungen oder Secrets exportiert.
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import re
import sys
import tokenize
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from genus import event_router


SCHEMA_VERSION = 1
ROOT = Path(__file__).resolve().parents[1]
SOURCE_AREAS = ("genus", "deploy")


RINGS: dict[str, frozenset[str]] = {
    "fundament": frozenset(
        {"constants", "proposal_types", "relation_semantics", "db", "sealing"}
    ),
    "wahrheitsmechanik": frozenset({"ledger", "confidence", "projection"}),
    "projektionen": frozenset(
        {
            "sources",
            "proposals",
            "inquiries",
            "experience",
            "state",
            "maturation",
            "governance",
            "operation",
        }
    ),
    "lernen": frozenset(
        {
            "rules",
            "learning",
            "inference",
            "self_calibration",
            "reactors",
            "abstraktion",
            "deduktion",
            "hypothese",
        }
    ),
    "antwort": frozenset(
        {
            "wortgraph",
            "auskunft",
            "werkzeuge_auskunft",
            "companion",
            "antwort",
            "persoenlichkeit",
            "formwahl",
            "erinnerung",
            "verstehen",
        }
    ),
    "schnittstellen": frozenset(
        {"query", "cli", "doctor", "thermometer", "control", "sensor"}
    ),
    "querschnitt": frozenset({"event_router", "integrity"}),
}


RAW_EVENT_USE: dict[str, tuple[tuple[str, str], ...]] = {
    "observation_created": (("genus.reactors", "raw_fold"),),
    "contradiction_detected": (("genus.inquiries", "audit_trigger"),),
    "constraint_checked": (("genus.query", "raw_fold"),),
    "policy_evaluated": (("genus.query", "raw_fold"),),
    "forecast_made": (("genus.learning", "raw_fold"),),
    "forecast_scored": (("genus.learning", "raw_fold"),),
    "rule_proposed": (("genus.maturation", "raw_fold"), ("genus.query", "raw_fold")),
    "ledger_epoch_opened": (("genus.sealing", "raw_fold"),),
    "werkzeug_registriert": (("genus.werkzeug", "audit_trace"),),
    "proposal_umgesetzt": (("genus.umsetzung", "raw_fold"),),
    "code_entwurf_erstellt": (("genus.werkstatt", "raw_fold"),),
    "code_entwurf_geprueft": (("genus.werkstatt", "audit_only"),),
    "hand_vorgeschlagen": (("genus.hand", "raw_fold"),),
    "hand_bestaetigt": (("genus.hand", "raw_fold"),),
    "hand_ausgefuehrt": (("genus.hand", "raw_fold"),),
    "hand_abgelehnt": (("genus.hand", "raw_fold"),),
}


SEMANTIC_NODES: tuple[dict[str, Any], ...] = (
    {
        "id": "flow:telegram",
        "type": "membrane",
        "label": "Telegram-Nachricht",
        "status": "active",
        "stage": 0,
        "source": ("deploy/telegram_bot.py", "handle_update"),
    },
    {
        "id": "flow:owner_gate",
        "type": "gate",
        "label": "Owner- und Privatchat-Gate",
        "status": "active",
        "stage": 1,
        "source": ("deploy/telegram_bot.py", "_allowed_ids"),
    },
    {
        "id": "flow:session6",
        "type": "memory",
        "label": "6-Zug-Session (RAM)",
        "status": "active_temporary",
        "stage": 2,
        "source": ("deploy/telegram_bot.py", "handle_update"),
    },
    {
        "id": "flow:intent_offer",
        "type": "contract",
        "label": "Verstehens-Raster",
        "status": "active",
        "stage": 2,
        "source": ("genus/verstehen.py", "gbnf_grammatik"),
    },
    {
        "id": "flow:deuter",
        "type": "model_membrane",
        "label": "Deuter: Absicht + Segmente",
        "status": "active_classifier",
        "stage": 3,
        "source": ("deploy/deuter.py", "interpret"),
    },
    {
        "id": "flow:response_cube",
        "type": "orchestrator",
        "label": "Antwort-Würfel",
        "status": "active",
        "stage": 4,
        "source": ("genus/companion.py", "respond_with_deuter"),
    },
    {
        "id": "flow:dispatch",
        "type": "registry",
        "label": "Intent-Dispatch",
        "status": "active",
        "stage": 5,
        "source": ("genus/companion.py", "_deuter_antwort"),
    },
    {
        "id": "flow:handlers",
        "type": "answer_source",
        "label": "Werkzeug-Handler",
        "status": "legacy_strings_with_draft_pilot",
        "stage": 6,
        "source": ("genus/companion.py", "_zelle_definition"),
    },
    {
        "id": "flow:read_model",
        "type": "read_model",
        "label": "Wissens-Read-Model",
        "status": "active",
        "stage": 5,
        "source": ("genus/sources.py", "relations"),
    },
    {
        "id": "flow:narrators",
        "type": "renderer",
        "label": "Fakt-/Relationsnarratoren",
        "status": "deterministic",
        "stage": 6,
        "source": ("genus/auskunft.py", "answer"),
    },
    {
        "id": "flow:personality",
        "type": "style",
        "label": "Antwort-Belegung",
        "status": "narrow_controls",
        "stage": 6,
        "source": ("genus/antwort.py", "belegung"),
    },
    {
        "id": "flow:composer",
        "type": "composer",
        "label": "Draft-Renderer + String-Komposition",
        "status": "draft_composition_pilot",
        "stage": 7,
        "source": ("genus/antwort.py", "rendere"),
    },
    {
        "id": "flow:voice",
        "type": "model_membrane",
        "label": "Stimme: optionale Paraphrase",
        "status": "optional_default_off",
        "stage": 8,
        "source": ("deploy/stimme.py", "formuliere"),
    },
    {
        "id": "flow:telegram_send",
        "type": "membrane",
        "label": "Telegram-Ausgabe",
        "status": "active",
        "stage": 9,
        "source": ("deploy/telegram_bot.py", "_send_message"),
    },
    {
        "id": "flow:cli_ask",
        "type": "diagnostic_channel",
        "label": "CLI ask (Diagnosepfad)",
        "status": "separate_read_only",
        "stage": 4,
        "source": ("genus/query.py", "ask"),
    },
    {
        "id": "learn:intent_correction",
        "type": "learning_signal",
        "label": "Enge Intent-Korrektur",
        "status": "active_narrow",
        "stage": 2,
        "source": ("deploy/deuter.py", "_korrektur_abschnitt"),
    },
    {
        "id": "learn:episodes",
        "type": "learning_store",
        "label": "Persönliche Episoden im Ledger",
        "status": "active_append_only",
        "stage": 2,
        "source": ("genus/erinnerung.py", "merke"),
    },
    {
        "id": "learn:day_buffer",
        "type": "learning_store",
        "label": "Tagespuffer",
        "status": "active_ephemeral",
        "stage": 2,
        "source": ("deploy/telegram_bot.py", "_schreibe_tagespuffer"),
    },
    {
        "id": "learn:word_queue",
        "type": "learning_store",
        "label": "Wort-Lernqueue",
        "status": "opt_in_default_off",
        "stage": 2,
        "source": ("deploy/telegram_bot.py", "_schreibe_lernwunsch"),
    },
    {
        "id": "learn:static_models",
        "type": "model_boundary",
        "label": "Statische GGUF-Gewichte",
        "status": "no_weight_learning",
        "stage": 3,
        "source": ("deploy/deuter.py", "interpret"),
    },
    {
        "id": "h1:dialogue_frame",
        "type": "contract",
        "label": "DialogueFrame",
        "status": "active_pilot",
        "stage": 7,
        "source": ("genus/antwort.py", "DialogueFrame"),
    },
    {
        "id": "h1:answer_draft",
        "type": "contract",
        "label": "AnswerDraft + Provenienz",
        "status": "active_pilot",
        "stage": 6,
        "source": ("genus/antwort.py", "AnswerDraft"),
    },
    {
        "id": "h1:outcome",
        "type": "outcome_contract",
        "label": "Zugestelltes ResponseOutcome",
        "status": "active_delivered_only",
        "stage": 10,
        "source": ("deploy/telegram_bot.py", "_bestaetige_zustellung"),
    },
    {
        "id": "h1:memory_vault",
        "type": "missing_privacy_boundary",
        "label": "Löschbarer Memory-Vault",
        "status": "missing_h1",
        "stage": 2,
        "source": ("docs/ROADMAP.md", "Vault"),
    },
    {
        "id": "h1:feedback",
        "type": "feedback_contract",
        "label": "Explizites Feedback mit Response-ID",
        "status": "active_explicit_gated",
        "stage": 11,
        "source": ("deploy/telegram_bot.py", "_explizites_feedback"),
    },
    {
        "id": "h1:alltagsprobe",
        "type": "evaluation_gate",
        "label": "Alltagsprobe: 17 synthetische Fälle",
        "status": "hard_gate_active_human_review_open",
        "stage": 12,
        "synthetic_cases": 17,
        "hard_gate": "active",
        "human_review": "open_hash_bound",
        "review_binding": "case_fingerprint+response_sha256",
        "source": ("genus/alltagsprobe.py", "run_suite"),
    },
    {
        "id": "h1:discourse",
        "type": "missing_composer",
        "label": "Diskursplan + treuer Renderer",
        "status": "missing_h1",
        "stage": 7,
        "source": ("docs/ROADMAP.md", "Antwortbogen"),
    },
    {
        "id": "h1:evaluation",
        "type": "missing_feedback",
        "label": "Gegatete Wirkungsbewertung",
        "status": "missing_h1",
        "stage": 12,
        "source": ("docs/QUALITY.md", "Abnahme"),
    },
    {
        "id": "h1:model_bakeoff",
        "type": "evaluation_membrane",
        "label": "Providerneutraler Stimmen-Bake-off",
        "status": "synthetic_only_dormant",
        "stage": 12,
        "privacy": "synthetic",
        "live_chat": False,
        "source": ("deploy/model_bakeoff.py", "_synthetic_answers"),
    },
)


SEMANTIC_EDGES: tuple[dict[str, Any], ...] = (
    {"from": "flow:telegram", "to": "flow:owner_gate", "type": "enters"},
    {"from": "flow:owner_gate", "to": "flow:session6", "type": "admits"},
    {"from": "flow:session6", "to": "flow:deuter", "type": "supplies_context"},
    {"from": "flow:intent_offer", "to": "flow:deuter", "type": "constrains"},
    {"from": "learn:intent_correction", "to": "flow:deuter", "type": "improves_intent"},
    {"from": "learn:static_models", "to": "flow:deuter", "type": "runs_model"},
    {"from": "flow:deuter", "to": "flow:response_cube", "type": "classifies_only"},
    {"from": "flow:response_cube", "to": "flow:dispatch", "type": "dispatches"},
    {"from": "flow:dispatch", "to": "flow:handlers", "type": "calls"},
    {"from": "flow:read_model", "to": "flow:handlers", "type": "supplies_knowledge"},
    {"from": "flow:read_model", "to": "flow:narrators", "type": "supplies_claims"},
    {"from": "flow:narrators", "to": "flow:handlers", "type": "renders"},
    {"from": "learn:episodes", "to": "flow:handlers", "type": "recalls"},
    {"from": "flow:personality", "to": "flow:handlers", "type": "controls_style"},
    {"from": "flow:handlers", "to": "flow:composer", "type": "returns_strings_or_drafts"},
    {"from": "flow:composer", "to": "flow:voice", "type": "optional_paraphrase"},
    {"from": "flow:voice", "to": "flow:telegram_send", "type": "sends"},
    {"from": "flow:composer", "to": "flow:telegram_send", "type": "default_sends"},
    {"from": "flow:telegram_send", "to": "learn:day_buffer", "type": "distils"},
    {"from": "flow:cli_ask", "to": "flow:read_model", "type": "reads_separately"},
    {"from": "flow:session6", "to": "h1:dialogue_frame", "type": "h1_input"},
    {"from": "h1:memory_vault", "to": "h1:dialogue_frame", "type": "h1_relevance"},
    {"from": "flow:handlers", "to": "h1:answer_draft", "type": "emits_draft_pilot"},
    {"from": "h1:answer_draft", "to": "flow:composer", "type": "renders_pilot"},
    {"from": "h1:dialogue_frame", "to": "flow:composer", "type": "frames_pilot"},
    {"from": "h1:answer_draft", "to": "h1:discourse", "type": "h1_compose"},
    {"from": "h1:dialogue_frame", "to": "h1:discourse", "type": "h1_guides"},
    {"from": "h1:discourse", "to": "flow:voice", "type": "h1_render"},
    {"from": "flow:telegram_send", "to": "h1:outcome", "type": "records_after_receipt"},
    {"from": "h1:outcome", "to": "flow:session6", "type": "confirms_turn"},
    {"from": "h1:outcome", "to": "h1:feedback", "type": "links_explicit_feedback"},
    {"from": "h1:feedback", "to": "h1:evaluation", "type": "h1_evidence"},
    {"from": "flow:composer", "to": "h1:alltagsprobe", "type": "exercises_contract_suite"},
    {"from": "h1:alltagsprobe", "to": "h1:evaluation", "type": "supplies_hard_gate"},
    {"from": "h1:alltagsprobe", "to": "h1:evaluation", "type": "awaits_hash_bound_human_review"},
    {"from": "h1:alltagsprobe", "to": "h1:model_bakeoff", "type": "supplies_synthetic_answers"},
    {"from": "h1:model_bakeoff", "to": "flow:voice", "type": "evaluates_remote_voice"},
)


LEARNING_IMPACT: tuple[dict[str, Any], ...] = (
    {
        "signal": "Fakten und Relationen",
        "store": "event_log + relation/value_projection",
        "consumer": "sources, auskunft, Wortgraph",
        "impact": "direct",
        "effect": "Mehr erkannte Begriffe, Definitionen, Relationen und Quellenbelege.",
        "sources": (("genus/sources.py", "relations"),),
    },
    {
        "signal": "Quellenvertrauen und Übereinstimmung",
        "store": "Read-time Confidence",
        "consumer": "Narratoren",
        "impact": "indirect",
        "effect": "Auswahl, Unsicherheits- und Mehrfachbelegsätze ändern sich.",
        "sources": (("genus/sources.py", "relation_confidence"),),
    },
    {
        "signal": "Intent-Lesungen",
        "store": "relation_projection",
        "consumer": "Thermometer und Lückendetektor",
        "impact": "none",
        "effect": "Zählt Verständnis, verbessert aber keine Formulierung und keinen Inhalt.",
        "sources": (("genus/verstehen.py", "record_reading"),),
    },
    {
        "signal": "Enge Intent-Korrektur",
        "store": "response_feedback_log + korrekturen.jsonl",
        "consumer": "lokaler/entfernter Deuter-Prompt + Qualitätsmessung",
        "impact": "indirect",
        "effect": "Ist mit der Response-ID replaybar belegt; Beispieltext bleibt lokal, begrenzte Intent-Verwechslungen schärfen die spätere Intentwahl.",
        "sources": (
            ("genus/response_outcomes.py", "record_feedback"),
            ("deploy/deuter.py", "_korrektur_abschnitt"),
        ),
    },
    {
        "signal": "Persönliche Episode",
        "store": "append-only Ledger",
        "consumer": "Erinnerungsabruf",
        "impact": "direct_limited",
        "effect": "Wird auf Abruf und über einen engen Konzeptbezug eingebunden.",
        "sources": (("genus/erinnerung.py", "merke"),),
    },
    {
        "signal": "Persönlichkeitseinstellung",
        "store": "art:* Relationen",
        "consumer": "Antwort-Belegung",
        "impact": "direct_limited",
        "effect": "Ändert wenige Floskeln, Länge, Beiwerk und optionale Stimme.",
        "sources": (("genus/antwort.py", "belegung"),),
    },
    {
        "signal": "Forecasts und Fehler",
        "store": "rohe Ledger-Events",
        "consumer": "learning CLI und Kurven",
        "impact": "none",
        "effect": "Kalibrierung sichtbar, aber kein normaler Dialogverbraucher.",
        "sources": (("genus/learning.py", "run_forecast_cycle"),),
    },
    {
        "signal": "Explizites Antwortfeedback (👍/👎)",
        "store": "response_feedback_log",
        "consumer": "replaybare Qualitätsmessung",
        "impact": "none",
        "effect": "Reine Daumen und enge eindeutige Textkritik werden sicher mit einer zugestellten Response-ID verknüpft; automatische Strategiegewichtung bleibt bewusst aus.",
        "sources": (("genus/response_outcomes.py", "record_feedback"),),
    },
    {
        "signal": "Modellgedeutetes Lob oder Kritik",
        "store": "nur Lesarten-Zählung",
        "consumer": "fester Handler",
        "impact": "none",
        "effect": "Wird ohne eindeutige Gebärde oder Korrektur nicht als Qualitätsfeedback gespeichert.",
        "sources": (("genus/companion.py", "_zelle_kritik"),),
    },
    {
        "signal": "Unbekanntes Chatwort",
        "store": "Opt-in Lernqueue",
        "consumer": "externer Lerner",
        "impact": "potential",
        "effect": "Nur ein ausdrücklich als Definition erfragter unbekannter Einzelbegriff kann später Graphwissen erzeugen; die Queue ist standardmäßig aus.",
        "sources": (("deploy/telegram_bot.py", "_schreibe_lernwunsch"),),
    },
    {
        "signal": "Modellgewichte",
        "store": "statische GGUF-Dateien",
        "consumer": "Deuter, Stimme, Waage",
        "impact": "none",
        "effect": "GENUS aktualisiert oder trainiert diese Gewichte nicht.",
        "sources": (("deploy/deuter.py", "_get_model"),),
    },
)


RUNTIME_OBSERVED_AT = "2026-07-13"
RUNTIME_REPORT = f"docs/reports/{RUNTIME_OBSERVED_AT}-cartography-runtime-audit.md"
RUNTIME_NODES: tuple[dict[str, Any], ...] = (
    {"id": "runtime:repo", "type": "runtime", "label": "Pi-Codecheckout", "status": "clean_main", "source": ("deploy/pi_deploy.sh", "git fetch")},
    {"id": "runtime:venv", "type": "runtime", "label": "Kern-Venv", "status": "healthy", "source": ("deploy/pi_deploy.sh", "pip install -e")},
    {"id": "runtime:ledger", "type": "private_store", "label": "Produktives SQLite-Ledger", "status": "healthy_single", "source": ("deploy/pi_deploy.sh", "GENUS_DB_PATH")},
    {"id": "runtime:cron", "type": "scheduler", "label": "Cron-Vertrag (17 Jobs)", "status": "active", "source": ("deploy/pi_install_cron.sh", "observe-all")},
    {"id": "runtime:watchdog_timer", "type": "root_boundary", "label": "Netzwerk-Watchdog-Timer", "status": "active", "source": ("deploy/pi_install_network_watchdog.sh", "Persistent=true")},
    {"id": "runtime:watchdog", "type": "root_boundary", "label": "Root-Watchdog", "status": "healthy", "source": ("deploy/pi_install_network_watchdog.sh", "ExecStart=")},
    {"id": "runtime:root_helpers", "type": "root_boundary", "label": "Root-eigene Helper-Kopien", "status": "repo_equal", "source": ("deploy/pi_network_watchdog.sh", "PRIVILEGED")},
    {"id": "runtime:learner", "type": "membrane_service", "label": "Permanenter Learner", "status": "active_broad_user_zone", "source": ("deploy/pi_install_learner.sh", "ExecStart=/bin/bash")},
    {"id": "runtime:telegram_bot", "type": "membrane_service", "label": "Telegram-Bot", "status": "active_voice_off", "source": ("deploy/pi_install_telegram_bot.sh", "GENUS_TELEGRAM_STIMME=0")},
    {"id": "runtime:deuter", "type": "model_membrane", "label": "Qwen-Deuter", "status": "installed_lazy", "source": ("deploy/deuter.py", "_get_model")},
    {"id": "runtime:embedder", "type": "model_membrane", "label": "FastEmbed Sense-Bridge", "status": "active_tmp_cache_drift", "source": ("deploy/pi_install_embedder.sh", "TextEmbedding")},
    {"id": "runtime:model_store", "type": "private_store", "label": "Lokale Modellablage", "status": "present_inventory_debt", "source": ("deploy/pi_install_deuter.sh", None)},
    {"id": "runtime:h0_profile", "type": "measurement", "label": "H0.1-Betriebsprofil", "status": "baseline_series_running", "source": ("deploy/pi_betriebsprofil_capture.sh", "betriebsprofil capture")},
    {"id": "runtime:backup", "type": "backup", "label": "Physisches Backupziel", "status": "healthy_permission_drift", "source": ("deploy/backup_ledger_to_sd.sh", "q.backup(z)")},
    {"id": "runtime:status", "type": "membrane_service", "label": "Status-Publisher", "status": "active_sanitized", "source": ("deploy/pi_publish_status.sh", "export_pi_status.py")},
    {"id": "runtime:logs", "type": "private_store", "label": "Cron-/Doctor-/Statuslogs", "status": "unbounded_rotation_gap", "source": ("deploy/pi_install_cron.sh", "cron.log")},
    {"id": "service:telegram", "type": "external_service", "label": "Telegram API", "status": "untrusted_network", "source": ("deploy/telegram_bot.py", "_api")},
    {"id": "service:wikidata", "type": "external_service", "label": "Wikidata", "status": "untrusted_network", "source": ("deploy/pi_learn.sh", "observe_konzept.sh")},
    {"id": "service:dbnary", "type": "external_service", "label": "DBnary", "status": "untrusted_network", "source": ("deploy/pi_learn.sh", "observe_dbnary.sh")},
    {"id": "service:weather_news", "type": "external_service", "label": "Wetter- und Nachrichtenquellen", "status": "untrusted_network", "source": ("deploy/pi_install_cron.sh", "weather")},
    {"id": "service:github", "type": "external_service", "label": "GitHub", "status": "external_code_and_status", "source": ("deploy/pi_deploy.sh", "git fetch")},
)


RUNTIME_EDGES: tuple[dict[str, Any], ...] = (
    {"from": "service:github", "to": "runtime:repo", "type": "fast_forward_deploy", "source": ("deploy/pi_deploy.sh", "git fetch")},
    {"from": "runtime:repo", "to": "runtime:venv", "type": "installs", "source": ("deploy/pi_deploy.sh", "pip install -e")},
    {"from": "runtime:venv", "to": "runtime:ledger", "type": "runs_core_against", "source": ("deploy/pi_deploy.sh", "GENUS_DB_PATH")},
    {"from": "runtime:cron", "to": "runtime:ledger", "type": "schedules_observations", "source": ("deploy/pi_install_cron.sh", "observe-all")},
    {"from": "runtime:cron", "to": "service:weather_news", "type": "polls", "source": ("deploy/pi_install_cron.sh", "weather")},
    {"from": "runtime:cron", "to": "runtime:backup", "type": "schedules", "source": ("deploy/pi_install_cron.sh", "ledger-backup")},
    {"from": "runtime:cron", "to": "runtime:h0_profile", "type": "schedules_read_only", "source": ("deploy/pi_install_cron.sh", "pi_betriebsprofil_capture.sh")},
    {"from": "runtime:cron", "to": "runtime:status", "type": "schedules_sanitized_publish", "source": ("deploy/pi_install_cron.sh", "status-publish")},
    {"from": "runtime:cron", "to": "runtime:logs", "type": "appends_unbounded", "source": ("deploy/pi_install_cron.sh", "cron.log")},
    {"from": "runtime:watchdog_timer", "to": "runtime:watchdog", "type": "triggers", "source": ("deploy/pi_install_network_watchdog.sh", "Persistent=true")},
    {"from": "runtime:root_helpers", "to": "runtime:watchdog", "type": "executes_root_owned", "source": ("deploy/pi_install_network_watchdog.sh", "ExecStart=")},
    {"from": "runtime:watchdog", "to": "runtime:learner", "type": "verifies_and_recovers", "source": ("deploy/pi_network_watchdog.sh", "learner")},
    {"from": "runtime:watchdog", "to": "runtime:telegram_bot", "type": "verifies_and_recovers", "source": ("deploy/pi_network_watchdog.sh", "GENUS_TELEGRAM_STIMME=0")},
    {"from": "runtime:learner", "to": "service:wikidata", "type": "polls", "source": ("deploy/pi_learn.sh", "observe_konzept.sh")},
    {"from": "runtime:learner", "to": "service:dbnary", "type": "polls", "source": ("deploy/pi_learn.sh", "observe_dbnary.sh")},
    {"from": "runtime:learner", "to": "runtime:embedder", "type": "bridges_senses", "source": ("deploy/pi_learn.sh", "bridge_senses.py")},
    {"from": "runtime:learner", "to": "runtime:ledger", "type": "writes_validated_events", "source": ("deploy/pi_learn.sh", "GENUS_DB_PATH")},
    {"from": "service:telegram", "to": "runtime:telegram_bot", "type": "long_polls_private_chat", "source": ("deploy/telegram_bot.py", "_get_updates")},
    {"from": "runtime:telegram_bot", "to": "runtime:deuter", "type": "classifies_message", "source": ("deploy/telegram_bot.py", "respond_with_deuter")},
    {"from": "runtime:model_store", "to": "runtime:deuter", "type": "loads_lazy", "source": ("deploy/deuter.py", "_get_model")},
    {"from": "runtime:deuter", "to": "flow:response_cube", "type": "supplies_intent_slots", "source": ("deploy/deuter.py", "interpret")},
    {"from": "flow:telegram_send", "to": "service:telegram", "type": "sends_response", "source": ("deploy/telegram_bot.py", "_send_message")},
    {"from": "runtime:ledger", "to": "runtime:h0_profile", "type": "read_only_prefix_snapshot", "source": ("deploy/pi_betriebsprofil_capture.sh", "betriebsprofil capture")},
    {"from": "runtime:ledger", "to": "runtime:backup", "type": "sqlite_backup", "source": ("deploy/backup_ledger_to_sd.sh", "q.backup(z)")},
    {"from": "runtime:status", "to": "service:github", "type": "publishes_aggregates_only", "source": ("deploy/pi_publish_status.sh", "export_pi_status.py")},
)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _module_name(path: Path) -> str:
    rel = path.relative_to(ROOT)
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _ring(module: str) -> str:
    if module.startswith("deploy."):
        return "membranen"
    base = module.rsplit(".", 1)[-1]
    if base.startswith("cli"):
        return "schnittstellen"
    for ring, names in RINGS.items():
        if base in names:
            return ring
    return "domaene"


def _line_for_symbol(tree: ast.AST, symbol: str) -> int | None:
    leaf = symbol.rsplit(".", 1)[-1]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == leaf:
                return node.lineno
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == leaf for target in targets):
                return node.lineno
    return None


def source(
    relative: str,
    marker: str | None = None,
    *,
    kind: str = "curated",
) -> dict[str, Any]:
    """Return a verified, repository-relative source reference.

    For Python files ``marker`` is first treated as a symbol and then as a literal.
    For text/shell files it is a literal. A missing marker is a build error: curated
    knowledge must never silently outlive its evidence.
    """
    path = ROOT / relative
    if not path.is_file():
        raise ValueError(f"Kartografie-Quelle fehlt: {relative}")
    text = path.read_text(encoding="utf-8")
    line = 1
    symbol: str | None = None
    if marker:
        found: int | None = None
        if path.suffix == ".py":
            found = _line_for_symbol(ast.parse(text, filename=relative), marker)
            if found is not None:
                symbol = marker
        if found is None:
            for index, value in enumerate(text.splitlines(), 1):
                if marker in value:
                    found = index
                    break
        if found is None:
            raise ValueError(f"Kartografie-Marker fehlt: {relative}::{marker}")
        line = found
    result: dict[str, Any] = {"file": relative, "line": line, "kind": kind}
    if symbol:
        result["symbol"] = symbol
    return result


def _node(
    node_id: str,
    node_type: str,
    label: str,
    *,
    sources: Iterable[dict[str, Any]] = (),
    **fields: Any,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": node_type,
        "label": label,
        **fields,
        "sources": list(sources),
    }


def _source_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (item["file"], item["line"], item.get("symbol"), item.get("kind"))


class _Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.dynamic_sql_calls: list[dict[str, Any]] = []

    def add_node(self, value: dict[str, Any]) -> None:
        existing = self.nodes.get(value["id"])
        if existing is not None and existing != value:
            raise ValueError(f"Knoten doppelt mit anderem Inhalt: {value['id']}")
        self.nodes[value["id"]] = value

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        edge_type: str,
        *,
        sources: Iterable[dict[str, Any]] = (),
        **fields: Any,
    ) -> None:
        key = (from_id, to_id, edge_type)
        existing = self.edges.get(key)
        if existing is None:
            self.edges[key] = {
                "from": from_id,
                "to": to_id,
                "type": edge_type,
                **fields,
                "sources": list(sources),
            }
            return
        merged = {_source_key(item): item for item in existing["sources"]}
        merged.update({_source_key(item): item for item in sources})
        existing["sources"] = [merged[key] for key in sorted(merged)]


class _ImportVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.depth = 0
        self.imports: list[tuple[ast.Import | ast.ImportFrom, bool]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    def visit_Import(self, node: ast.Import) -> None:
        self.imports.append((node, self.depth > 0))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.imports.append((node, self.depth > 0))


class _CallVisitor(ast.NodeVisitor):
    def __init__(
        self,
        constants: dict[str, str],
        ledger_owners: set[str],
        ledger_appenders: set[str],
    ) -> None:
        self.constants = constants
        self.ledger_owners = ledger_owners
        self.ledger_appenders = ledger_appenders
        self.stack: list[str] = []
        self.events: list[tuple[str, int, str]] = []
        self.sql: list[tuple[str, str, int]] = []
        self.unresolved_sql: list[tuple[str, int, str]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    @classmethod
    def _call_path(cls, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            owner = cls._call_path(node.value)
            return f"{owner}.{node.attr}" if owner else node.attr
        return None

    def _event_value(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return self.constants.get(node.id)
        return None

    @staticmethod
    def _string_value(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for value in node.values:
                if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                    return None
                parts.append(value.value)
            return "".join(parts)
        return None

    def visit_Call(self, node: ast.Call) -> None:
        call_path = self._call_path(node.func)
        parts = call_path.rsplit(".", 1) if call_path else []
        owner = parts[0] if len(parts) == 2 else None
        name = parts[-1] if parts else None
        is_ledger_append = (
            name == "append" and owner in self.ledger_owners
        ) or call_path in self.ledger_appenders
        if is_ledger_append:
            arg = node.args[1] if len(node.args) > 1 else None
            if arg is None:
                arg = next(
                    (kw.value for kw in node.keywords if kw.arg == "event_type"),
                    None,
                )
            event = self._event_value(arg) if arg is not None else None
            if event:
                self.events.append((self.stack[-1] if self.stack else "<module>", node.lineno, event))
        if name in {"execute", "executemany", "executescript"} and node.args:
            sql = self._string_value(node.args[0])
            if sql:
                self.sql.append((name, sql, node.lineno))
            else:
                self.unresolved_sql.append(
                    (self.stack[-1] if self.stack else "<module>", node.lineno, name)
                )
        self.generic_visit(node)


def _constants(tree: ast.AST) -> dict[str, str]:
    values: dict[str, str] = {}
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        values[target.id] = node.value.value
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                values[node.target.id] = node.value.value
    return values


def _ledger_bindings(tree: ast.AST) -> tuple[set[str], set[str]]:
    owners: set[str] = set()
    appenders: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "genus.ledger":
                    owners.add(alias.asname or "genus.ledger")
        elif isinstance(node, ast.ImportFrom):
            if node.module == "genus":
                for alias in node.names:
                    if alias.name == "ledger":
                        owners.add(alias.asname or "ledger")
            elif node.module == "genus.ledger":
                for alias in node.names:
                    if alias.name == "append":
                        appenders.add(alias.asname or "append")
    return owners, appenders


def _sql_literals(tree: ast.AST, text: str) -> list[tuple[str, int]]:
    """Collect SQL-bearing literals even when they flow through a local helper.

    Direct ``conn.execute(<literal>)`` calls are only one form used in GENUS. Helpers
    such as ``motor._count`` and ``betriebsprofil.count`` receive their SELECT as a
    normal argument. Module/function/class docstrings are excluded to avoid turning
    prose examples into dependency evidence.
    """
    docstring_lines: list[tuple[int, int]] = []
    for owner in ast.walk(tree):
        body = getattr(owner, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
            value = body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                docstring_lines.append((value.lineno, value.end_lineno or value.lineno))
    found: list[tuple[str, int]] = []
    # CPython 3.11 and 3.12 assign different ``lineno`` values to the single AST Constant
    # produced from adjacent string tokens.  Token start positions are source facts and stay
    # stable across supported interpreters, so generated cartography must use those instead.
    fstring_start_type = getattr(tokenize, "FSTRING_START", -1)
    fstring_middle_type = getattr(tokenize, "FSTRING_MIDDLE", -1)
    fstring_end_type = getattr(tokenize, "FSTRING_END", -1)
    fstring_start_line: int | None = None
    fstring_parts: list[str] = []
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == fstring_start_type:
            fstring_start_line = token.start[0]
            fstring_parts = []
            continue
        if fstring_start_line is not None:
            if token.type == fstring_middle_type:
                fstring_parts.append(token.string)
            elif token.type == fstring_end_type:
                sql = "".join(fstring_parts)
                if _READ_SQL.search(sql) or _WRITE_SQL.search(sql):
                    found.append((sql, fstring_start_line))
                fstring_start_line = None
                fstring_parts = []
            continue
        if token.type != tokenize.STRING:
            continue
        line = token.start[0]
        if any(start <= line <= end for start, end in docstring_lines):
            continue
        if _READ_SQL.search(token.string) or _WRITE_SQL.search(token.string):
            found.append((token.string, line))
    return found


def _resolve_imports(
    current: str,
    node: ast.Import | ast.ImportFrom,
    local_modules: set[str],
) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    if isinstance(node, ast.Import):
        candidates = [alias.name for alias in node.names]
    else:
        module = node.module or ""
        if node.level:
            package = current.split(".")[:-1]
            keep = max(0, len(package) - node.level + 1)
            module = ".".join(package[:keep] + ([module] if module else []))
        if module == "genus":
            candidates = [f"genus.{alias.name}" for alias in node.names]
        elif module:
            candidates = [module]
        else:
            candidates = []
    for candidate in candidates:
        if candidate in local_modules:
            targets.append(("module", candidate))
            continue
        if f"deploy.{candidate}" in local_modules:
            targets.append(("module", f"deploy.{candidate}"))
            continue
        root = candidate.split(".", 1)[0]
        if root and root not in sys.stdlib_module_names and root != "__future__":
            targets.append(("external", root))
    return targets


_READ_SQL = re.compile(r"\b(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)", re.IGNORECASE)
_WRITE_SQL = re.compile(
    r"\b(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|REPLACE\s+INTO|UPDATE|DELETE\s+FROM)\s+"
    r"([a-z_][a-z0-9_]*)",
    re.IGNORECASE,
)


def _schema(graph: _Graph) -> set[str]:
    path = ROOT / "schema.sql"
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+([a-z_][a-z0-9_]*)\s*"
        r"\((.*?)\);",
        re.IGNORECASE | re.DOTALL,
    )
    tables: set[str] = set()
    for match in pattern.finditer(text):
        table = match.group(1)
        tables.add(table)
        line = text.count("\n", 0, match.start()) + 1
        graph.add_node(
            _node(
                f"table:{table}",
                "table",
                table,
                sources=({"file": "schema.sql", "line": line, "kind": "schema"},),
                replayable=table in event_router.REPLAY_PROJEKTIONSTABELLEN,
            )
        )
        for target in re.findall(r"\bREFERENCES\s+([a-z_][a-z0-9_]*)", match.group(2), re.I):
            graph.add_edge(
                f"table:{table}",
                f"table:{target}",
                "foreign_key_to",
                sources=({"file": "schema.sql", "line": line, "kind": "schema"},),
            )
    return tables


def _modules(graph: _Graph, tables: set[str]) -> tuple[set[str], set[str]]:
    paths = sorted(
        path
        for area in SOURCE_AREAS
        for path in (ROOT / area).rglob("*.py")
        if "__pycache__" not in path.parts
    )
    modules = {_module_name(path) for path in paths}
    produced: set[str] = set()
    for path in paths:
        module = _module_name(path)
        relative = _rel(path)
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=relative)
        graph.add_node(
            _node(
                f"module:{module}",
                "module",
                module,
                sources=({"file": relative, "line": 1, "kind": "ast"},),
                ring=_ring(module),
                roles=["module"],
            )
        )

        imports = _ImportVisitor()
        imports.visit(tree)
        for import_node, lazy in imports.imports:
            for target_type, target in _resolve_imports(module, import_node, modules):
                target_id = f"{target_type}:{target}"
                if target_type == "external":
                    graph.add_node(
                        _node(
                            target_id,
                            "external",
                            target,
                            sources=(),
                            boundary="dependency",
                        )
                    )
                graph.add_edge(
                    f"module:{module}",
                    target_id,
                    "imports_lazy" if lazy else "imports_eager",
                    sources=(
                        {"file": relative, "line": import_node.lineno, "kind": "ast"},
                    ),
                )

        ledger_owners, ledger_appenders = _ledger_bindings(tree)
        calls = _CallVisitor(_constants(tree), ledger_owners, ledger_appenders)
        calls.visit(tree)
        roles = graph.nodes[f"module:{module}"]["roles"]
        if module.startswith("deploy."):
            roles.append("membrane")
        if calls.events:
            roles.append("event_producer")
        if calls.sql:
            roles.append("sql_consumer")
        if calls.unresolved_sql:
            if "dynamic_sql" not in roles:
                roles.append("dynamic_sql")
            for function, line, method in calls.unresolved_sql:
                graph.dynamic_sql_calls.append(
                    {
                        "module": module,
                        "function": function,
                        "method": method,
                        "source": {"file": relative, "line": line, "kind": "ast"},
                    }
                )
        for function, line, event in calls.events:
            produced.add(event)
            symbol_id = f"producer:{module}.{function}"
            if symbol_id not in graph.nodes:
                graph.add_node(
                    _node(
                        symbol_id,
                        "event_producer",
                        f"{module.rsplit('.', 1)[-1]}.{function}",
                        sources=({"file": relative, "line": line, "kind": "ast"},),
                        module=module,
                    )
                )
                graph.add_edge(
                    f"module:{module}",
                    symbol_id,
                    "contains",
                    sources=({"file": relative, "line": line, "kind": "ast"},),
                )
            graph.add_edge(
                symbol_id,
                f"event:{event}",
                "produces_event",
                sources=({"file": relative, "line": line, "kind": "ast"},),
            )

        sql_evidence = [(sql, line, "sql_call") for _, sql, line in calls.sql]
        sql_evidence.extend(
            (sql, line, "sql_literal") for sql, line in _sql_literals(tree, text)
        )
        for sql, line, evidence_kind in sql_evidence:
            src = ({"file": relative, "line": line, "kind": evidence_kind},)
            for table in sorted(set(_READ_SQL.findall(sql)) & tables):
                graph.add_edge(f"module:{module}", f"table:{table}", "reads_table", sources=src)
            for table in sorted(set(_WRITE_SQL.findall(sql)) & tables):
                graph.add_edge(f"module:{module}", f"table:{table}", "writes_table", sources=src)
        if module == "genus.db":
            schema_ref = (
                {
                    "file": relative,
                    "line": _line_for_symbol(tree, "SCHEMA_PATH") or 1,
                    "kind": "schema_loader",
                },
            )
            for table in sorted(tables):
                graph.add_edge(
                    f"module:{module}",
                    f"table:{table}",
                    "initializes_schema",
                    sources=schema_ref,
                )
    return modules, produced


def _events(graph: _Graph, modules: set[str], produced: set[str]) -> None:
    projected = set(event_router.PROJEKTOREN)
    raw = set(event_router.BEWUSST_ROH)
    all_events = sorted(produced | projected | raw)
    router_source = "genus/event_router.py"
    for event in all_events:
        status = "projected" if event in projected else "raw" if event in raw else "undecided"
        graph.add_node(
            _node(
                f"event:{event}",
                "event",
                event,
                sources=(source(router_source, f'"{event}"', kind="registry"),),
                status=status,
                produced=event in produced,
            )
        )
    # sealing.open_epoch deliberately writes below ledger.append.
    if "ledger_epoch_opened" not in produced:
        produced.add("ledger_epoch_opened")
        graph.add_edge(
            "module:genus.sealing",
            "event:ledger_epoch_opened",
            "produces_event_direct",
            sources=(source("genus/sealing.py", "ledger_epoch_opened", kind="declared_exception"),),
        )

    for event, projector in sorted(event_router.PROJEKTOREN.items()):
        symbol = f"{projector.__module__}.{projector.__name__}"
        projector_id = f"projector:{symbol}"
        relative = projector.__module__.replace(".", "/") + ".py"
        graph.add_node(
            _node(
                projector_id,
                "projector",
                symbol,
                sources=(source(relative, projector.__name__, kind="registry"),),
                module=projector.__module__,
            )
        )
        module_id = f"module:{projector.__module__}"
        if module_id in graph.nodes:
            roles = graph.nodes[module_id]["roles"]
            if "projector" not in roles:
                roles.append("projector")
        graph.add_edge(
            f"event:{event}",
            projector_id,
            "routes_on_replay",
            sources=(source(router_source, f'"{event}"', kind="registry"),),
        )
        for table in sorted(event_router.PROJEKTIONSZIELE.get(event, ())):
            graph.add_edge(
                projector_id,
                f"table:{table}",
                "writes_projection",
                sources=(source(router_source, f'"{event}"', kind="projection_contract"),),
            )

    for event, consumers in RAW_EVENT_USE.items():
        for module, use_type in consumers:
            if module not in modules:
                raise ValueError(f"Raw-Event-Verbraucher fehlt: {module}")
            graph.add_edge(
                f"event:{event}",
                f"module:{module}",
                use_type,
                sources=(source(module.replace(".", "/") + ".py", kind="curated"),),
            )


def _semantics(graph: _Graph) -> None:
    for item in SEMANTIC_NODES:
        value = dict(item)
        relative, marker = value.pop("source")
        graph.add_node(
            _node(
                value.pop("id"),
                value.pop("type"),
                value.pop("label"),
                sources=(source(relative, marker),),
                **value,
            )
        )
    evidence_by_node = {item["id"]: item["source"] for item in SEMANTIC_NODES}
    for item in SEMANTIC_EDGES:
        value = dict(item)
        from_id = value.pop("from")
        to_id = value.pop("to")
        edge_type = value.pop("type")
        relative, marker = evidence_by_node[from_id]
        graph.add_edge(
            from_id,
            to_id,
            edge_type,
            sources=(source(relative, marker),),
            **value,
        )

    # Die semantische Antwortsicht bindet die echten Projektionstabellen ein.
    answer_table_sources = {
        "relation_projection": ("genus/sources.py", "relation_projection", "direct"),
        "value_projection": ("genus/sources.py", "value_projection", "direct"),
        "belief_projection": ("genus/query.py", "belief_projection", "limited"),
        "state_projection": ("genus/query.py", "state_projection", "limited"),
    }
    for table, (relative, marker, impact) in answer_table_sources.items():
        graph.add_edge(
            f"table:{table}",
            "flow:read_model",
            "influences_answer",
            sources=(source(relative, marker, kind="curated"),),
            impact=impact,
        )


def _runtime(graph: _Graph) -> None:
    stages = {
        "service:github": 0,
        "service:telegram": 0,
        "service:wikidata": 0,
        "service:dbnary": 0,
        "service:weather_news": 0,
        "runtime:repo": 1,
        "runtime:root_helpers": 1,
        "runtime:venv": 2,
        "runtime:cron": 2,
        "runtime:watchdog_timer": 2,
        "runtime:watchdog": 3,
        "runtime:learner": 3,
        "runtime:telegram_bot": 3,
        "runtime:model_store": 3,
        "runtime:embedder": 4,
        "runtime:deuter": 4,
        "runtime:ledger": 5,
        "runtime:logs": 5,
        "runtime:h0_profile": 6,
        "runtime:backup": 6,
        "runtime:status": 6,
    }
    for item in RUNTIME_NODES:
        value = dict(item)
        relative, marker = value.pop("source")
        node_id = value.pop("id")
        refs = [source(relative, marker, kind="runtime_contract")]
        if node_id.startswith("runtime:"):
            refs.append(
                source(
                    RUNTIME_REPORT,
                    value["label"],
                    kind="dated_pi_audit",
                )
            )
        graph.add_node(
            _node(
                node_id,
                value.pop("type"),
                value.pop("label"),
                sources=refs,
                observed_at=RUNTIME_OBSERVED_AT,
                stage=stages[node_id],
                **value,
            )
        )
    for item in RUNTIME_EDGES:
        value = dict(item)
        relative, marker = value.pop("source")
        graph.add_edge(
            value.pop("from"),
            value.pop("to"),
            value.pop("type"),
            sources=(source(relative, marker, kind="runtime_contract"),),
            observed_at=RUNTIME_OBSERVED_AT,
            **value,
        )


def _views(graph: _Graph) -> list[dict[str, Any]]:
    semantic = [node_id for node_id in graph.nodes if node_id.startswith(("flow:", "learn:", "h1:"))]
    raw_edge_types = {"raw_fold", "audit_trigger", "audit_trace", "audit_only"}
    raw_consumers = {
        edge["to"] for edge in graph.edges.values() if edge["type"] in raw_edge_types
    }
    return [
        {
            "id": "wirkung",
            "label": "Wirkungskette",
            "description": "Vom Eingang bis zur zugestellten Antwort und ihrem expliziten Feedback; offene H1-Kanten gestrichelt.",
            "nodes": sorted(semantic),
            "edge_types": sorted({edge["type"] for edge in graph.edges.values() if edge["from"] in semantic and edge["to"] in semantic}),
        },
        {
            "id": "ereignisse",
            "label": "Events & Projektionen",
            "description": "Produzent, Event, Replay-Projektor und persistierte Zielsicht.",
            "nodes": sorted(
                {
                    node_id
                    for node_id in graph.nodes
                    if node_id.startswith(("producer:", "event:", "projector:", "table:"))
                }
                | raw_consumers
            ),
            "edge_types": [
                "produces_event",
                "produces_event_direct",
                "routes_on_replay",
                "writes_projection",
                "raw_fold",
                "audit_trigger",
                "audit_trace",
                "audit_only",
            ],
        },
        {
            "id": "lernen",
            "label": "Lernen → Antwort",
            "description": "Welche gespeicherten Signale Antworten direkt, indirekt oder gar nicht verändern.",
            "nodes": sorted(
                node_id
                for node_id in graph.nodes
                if node_id.startswith(("learn:", "flow:", "h1:", "table:"))
            ),
            "edge_types": ["influences_answer", "improves_intent", "recalls", "controls_style"],
        },
        {
            "id": "module",
            "label": "Module & Imports",
            "description": "Vollständiger Python-Quellbaum mit eager/lazy Imports und externen Abhängigkeiten.",
            "nodes": sorted(
                node_id for node_id, node in graph.nodes.items() if node["type"] in {"module", "external"}
            ),
            "edge_types": ["imports_eager", "imports_lazy"],
        },
        {
            "id": "betrieb",
            "label": "Pi-Betrieb",
            "description": f"Sanitisierter Sollpfad mit datiertem read-only Pi-Audit vom {RUNTIME_OBSERVED_AT}; kein Live-Monitor.",
            "nodes": sorted(
                node_id
                for node_id in graph.nodes
                if node_id.startswith(("runtime:", "service:"))
                or node_id in {"flow:response_cube", "flow:telegram_send"}
            ),
            "edge_types": sorted(
                {
                    edge["type"]
                    for edge in graph.edges.values()
                    if edge.get("observed_at") == RUNTIME_OBSERVED_AT
                }
            ),
        },
    ]


def _validate(graph: _Graph, produced: set[str]) -> list[str]:
    errors: list[str] = []
    node_ids = set(graph.nodes)
    for edge in graph.edges.values():
        if edge["from"] not in node_ids or edge["to"] not in node_ids:
            errors.append(f"hängende Kante: {edge['from']} -> {edge['to']}")
    projected = set(event_router.PROJEKTOREN)
    raw = set(event_router.BEWUSST_ROH)
    if projected != set(event_router.PROJEKTIONSZIELE):
        errors.append("PROJEKTOREN und PROJEKTIONSZIELE haben unterschiedliche Eventtypen")
    if projected & raw:
        errors.append("Eventtyp ist zugleich projiziert und bewusst roh")
    undecided = produced - projected - raw
    if undecided:
        errors.append(f"produzierte Eventtypen ohne Routerentscheidung: {sorted(undecided)}")
    missing_produced = (projected | raw) - produced
    if missing_produced:
        errors.append(f"registrierte Eventtypen ohne Produzent: {sorted(missing_produced)}")
    targets = {table for values in event_router.PROJEKTIONSZIELE.values() for table in values}
    if targets != set(event_router.REPLAY_PROJEKTIONSTABELLEN):
        errors.append("Projektionsziele und Replay-Leerliste unterscheiden sich")
    for node in graph.nodes.values():
        for ref in node.get("sources", []):
            if Path(ref["file"]).is_absolute() or ".." in Path(ref["file"]).parts:
                errors.append(f"unsichere Quellenreferenz: {ref['file']}")
    for edge in graph.edges.values():
        for ref in edge.get("sources", []):
            if Path(ref["file"]).is_absolute() or ".." in Path(ref["file"]).parts:
                errors.append(f"unsichere Quellenreferenz: {ref['file']}")
    return errors


def _learning_impact() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in LEARNING_IMPACT:
        value = dict(item)
        refs = value.pop("sources")
        value["sources"] = [source(relative, marker) for relative, marker in refs]
        result.append(value)
    return result


def _import_cycles(graph: _Graph) -> list[dict[str, Any]]:
    modules = {node_id for node_id, node in graph.nodes.items() if node["type"] == "module"}
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in modules}
    import_edges: dict[tuple[str, str], set[str]] = defaultdict(set)
    for edge in graph.edges.values():
        if edge["type"] not in {"imports_eager", "imports_lazy"}:
            continue
        if edge["from"] in modules and edge["to"] in modules:
            adjacency[edge["from"]].add(edge["to"])
            import_edges[(edge["from"], edge["to"])].add(edge["type"])

    index = 0
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(node_id: str) -> None:
        nonlocal index
        indices[node_id] = index
        low[node_id] = index
        index += 1
        stack.append(node_id)
        on_stack.add(node_id)
        for target in sorted(adjacency[node_id]):
            if target not in indices:
                visit(target)
                low[node_id] = min(low[node_id], low[target])
            elif target in on_stack:
                low[node_id] = min(low[node_id], indices[target])
        if low[node_id] == indices[node_id]:
            component: list[str] = []
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == node_id:
                    break
            if len(component) > 1 or node_id in adjacency[node_id]:
                components.append(sorted(component))

    for module in sorted(modules):
        if module not in indices:
            visit(module)

    result: list[dict[str, Any]] = []
    for number, component in enumerate(sorted(components), 1):
        member_set = set(component)
        types = sorted(
            {
                edge_type
                for (from_id, to_id), edge_types in import_edges.items()
                if from_id in member_set and to_id in member_set
                for edge_type in edge_types
            }
        )
        result.append(
            {
                "id": f"import-cycle-{number}",
                "members": [member.removeprefix("module:") for member in component],
                "edge_types": types,
                "contains_lazy_edge": "imports_lazy" in types,
                "assessment": "visible_runtime_cycle" if "imports_lazy" in types else "eager_cycle",
            }
        )
    return result


def build_map() -> dict[str, Any]:
    graph = _Graph()
    tables = _schema(graph)
    modules, produced = _modules(graph, tables)
    _events(graph, modules, produced)
    _semantics(graph)
    _runtime(graph)
    errors = _validate(graph, produced)
    if errors:
        raise ValueError("Kartografie-Vertrag verletzt:\n- " + "\n- ".join(errors))

    nodes = [graph.nodes[key] for key in sorted(graph.nodes)]
    edges = [graph.edges[key] for key in sorted(graph.edges)]
    import_cycles = _import_cycles(graph)
    status_counts: dict[str, int] = defaultdict(int)
    for node in nodes:
        status_counts[node["type"]] += 1
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "authority": "repository source + explicit projection and effect contracts",
        "scope": ["genus/**/*.py", "deploy/**/*.py", "schema.sql", "curated causal contracts"],
        "summary": {
            "nodes": len(nodes),
            "edges": len(edges),
            "modules": status_counts["module"],
            "external_dependencies": status_counts["external"],
            "event_types": status_counts["event"],
            "projected_events": len(event_router.PROJEKTOREN),
            "raw_events": len(event_router.BEWUSST_ROH),
            "projection_tables": len(event_router.REPLAY_PROJEKTIONSTABELLEN),
            "missing_h1_contracts": sum(node.get("status") == "missing_h1" for node in nodes),
            "runtime_nodes": sum(node["id"].startswith("runtime:") for node in nodes),
            "import_cycles": len(import_cycles),
            "dynamic_sql_calls": len(graph.dynamic_sql_calls),
        },
        "nodes": nodes,
        "edges": edges,
        "views": _views(graph),
        "learning_impact": _learning_impact(),
        "import_cycles": import_cycles,
        "runtime_snapshot": {
            "captured_at": RUNTIME_OBSERVED_AT,
            "kind": "dated_read_only_pi_audit",
            "live_monitor": False,
            "check_scope": "kartografie check validates repository contracts and snapshot currency; it does not connect to the Pi",
            "sources": [
                source(
                    RUNTIME_REPORT,
                    "Snapshot:",
                    kind="dated_pi_audit",
                )
            ],
        },
        "analysis_limits": {
            "dynamic_sql_calls": sorted(
                graph.dynamic_sql_calls,
                key=lambda item: (item["module"], item["source"]["line"]),
            ),
            "dynamic_sql_statement": "Table edges include direct and helper-passed SQL literals; unresolved dynamic execute calls are listed instead of guessed.",
            "shell_runtime_statement": "Shell, systemd and cron topology is an explicit source-bound runtime contract, not a general shell-language dependency extraction.",
        },
        "findings": [
            {
                "id": "answer-quality-bottleneck",
                "severity": "medium",
                "statement": "Die Alltagsprobe hält 17 synthetische Fälle als hartes, reproduzierbares Vertragsgate fest. Ton und Nutzen brauchen weiterhin fall- und antwort-hashgebundene Humanreviews; die Wirkungsbewertung ist deshalb offen. AnswerDraft deckt nur Definitionen und Beziehungen ab, die übrigen Handler liefern Strings, und aus Feedback folgt keine Strategiewahl.",
                "sources": [
                    source("genus/alltagsprobe.py", "ALLTAGSFAELLE"),
                    source("genus/alltagsprobe.py", "_human_status"),
                    source("genus/antwort.py", "AnswerDraft"),
                    source("genus/response_outcomes.py", "record_feedback"),
                ],
            },
            {
                "id": "feedback-restart-boundary",
                "severity": "medium",
                "statement": "Die Telegram-Session hält Response-IDs nur im Prozess. Nach einem Neustart fehlt noch ein löschbarer, transportnaher Index, der neues Feedback wieder einer früher zugestellten Antwort zuordnet.",
                "sources": [
                    source("deploy/telegram_bot.py", "_letztes_feedbackziel"),
                    source("docs/design/MEMORY.md", "Prozessneustart"),
                ],
            },
            {
                "id": "delivery-outcome-outbox-gap",
                "severity": "medium",
                "statement": "Scheitert die Outcome-Persistenz erst nach belegter Telegram-Zustellung, wird der Update-Offset dennoch fortgeschrieben. Ohne löschbare Edge-Outbox bleibt diese zugestellte Antwort dauerhaft ungemessen.",
                "sources": [
                    source("deploy/telegram_bot.py", "response outcome could not be persisted"),
                    source("docs/reports/2026-07-13-h1-response-loop.md", "Edge-Outbox"),
                ],
            },
            {
                "id": "live-vs-replay",
                "severity": "contract",
                "statement": "Live-Produzenten wenden Projektoren direkt an; der Event-Router ist der Replay-Pfad.",
                "sources": [source("genus/event_router.py", "beim Replay und nirgendwo sonst")],
            },
            {
                "id": "privacy-boundary-gap",
                "severity": "high",
                "statement": "Persönliche Episoden liegen append-only; der löschbare persönliche Vault ist noch ein H1-Vertrag.",
                "sources": [
                    source("genus/erinnerung.py", "merke"),
                    source("docs/ROADMAP.md", "Vault"),
                ],
            },
            {
                "id": "pi-fastembed-cache",
                "severity": "high",
                "statement": "Das Embedder-Venv ist persistent, der Modellcache liegt live jedoch flüchtig unter /tmp; Offline- und Neustartverhalten sind dadurch nicht reproduzierbar.",
                "sources": [
                    source(RUNTIME_REPORT, "D1 ·"),
                    source("deploy/pi_install_embedder.sh", "TextEmbedding"),
                ],
            },
            {
                "id": "pi-unit-word-learning-drift",
                "severity": "medium",
                "statement": "Die Installer deklarieren Chat-Wortlernen explizit aus; die live installierten Units verließen sich beim Audit noch auf denselben Code-Default.",
                "sources": [
                    source(RUNTIME_REPORT, "D2 ·"),
                    source("deploy/pi_install_learner.sh", "GENUS_CHAT_WORD_LEARNING"),
                    source("deploy/pi_install_telegram_bot.sh", "GENUS_CHAT_WORD_LEARNING"),
                    source("deploy/pi_network_watchdog.sh", "GENUS_TELEGRAM_STIMME=0"),
                ],
            },
            {
                "id": "pi-backup-permissions",
                "severity": "high",
                "statement": "Backups sind funktional und physisch getrennt, aber Ziel und Dateien benötigen einen eigenen 0700/0600-Vertrag für Defense in Depth.",
                "sources": [
                    source(RUNTIME_REPORT, "D3 ·"),
                    source("deploy/backup_ledger_to_sd.sh", "BACKUP_DIR"),
                    source("docs/SECURITY_MODEL.md", "nicht automatisch verschlüsselt"),
                ],
            },
            {
                "id": "pi-log-rotation",
                "severity": "medium",
                "statement": "Cron-, Doctor- und Statuslogs werden ohne Größen- oder Generationengrenze fortgeschrieben.",
                "sources": [
                    source(RUNTIME_REPORT, "D4 ·"),
                    source("deploy/pi_install_cron.sh", "cron.log"),
                ],
            },
            {
                "id": "pi-private-file-modes",
                "severity": "medium",
                "statement": "Der private Elternpfad ist 0700, einzelne State-, Log- und Ledgerdateien besitzen aber keinen einheitlichen 0600-Eigenvertrag.",
                "sources": [
                    source(RUNTIME_REPORT, "D5 ·"),
                    source("docs/SECURITY_MODEL.md", "0700"),
                ],
            },
            {
                "id": "pi-model-inventory",
                "severity": "low",
                "statement": "Mehrere nicht aktive Werkstattmodelle erschweren Rollen-, Update- und Speicherinventar.",
                "sources": [
                    source(RUNTIME_REPORT, "D6 ·"),
                    source("deploy/pi_install_deuter.sh"),
                ],
            },
            {
                "id": "pi-learner-trust-zone",
                "severity": "architectural",
                "statement": "Der netzaktive Learner teilt den Benutzer und damit einen breiten Ausfallradius mit Ledger und privatem Membranzustand.",
                "sources": [
                    source(RUNTIME_REPORT, "D7 ·"),
                    source("deploy/pi_install_learner.sh", "User="),
                    source("docs/SECURITY_MODEL.md", "Learner"),
                ],
            },
            {
                "id": "pi-cron-timezone",
                "severity": "low",
                "statement": "Cron wird in lokaler Pi-Zeit interpretiert, Tickzeilen sind UTC; der Sommerzeitvertrag ist nicht explizit.",
                "sources": [
                    source(RUNTIME_REPORT, "D8 ·"),
                    source("deploy/pi_install_cron.sh", "date -u"),
                ],
            },
        ],
    }
    digest_input = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    result["content_sha256"] = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
    return result


def render_json(data: dict[str, Any] | None = None) -> str:
    return json.dumps(data or build_map(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def written_event_types() -> frozenset[str]:
    """Return recursively AST-derived ledger event types, including the seal exception."""
    graph = _Graph()
    tables = _schema(graph)
    _, produced = _modules(graph, tables)
    produced.add("ledger_epoch_opened")
    return frozenset(produced)
