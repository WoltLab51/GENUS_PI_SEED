import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_grundwortschatz_seed_file_is_a_wellformed_word_list():
    lines = (ROOT / "deploy" / "grundwortschatz_de.tsv").read_text(encoding="utf-8").splitlines()
    words = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        # the list is the VOCABULARY -- one word per line, no hand-typed Q-ids
        assert " " not in s and "\t" not in s, f"one word per line: {line!r}"
        assert not re.fullmatch(r"Q[0-9]+", s), "the list holds words, not guessed Q-ids"
        assert "@" not in s
        words.append(s)
    assert len(words) >= 20                # a real starting foundation
    assert len(words) == len(set(words))   # no duplicate words


def test_grundwortschatz_seed_script_resolves_each_word_from_the_source():
    script = (ROOT / "deploy" / "seed_grundwortschatz.sh").read_text(encoding="utf-8")
    assert "grundwortschatz_de.tsv" in script
    assert "observe_konzept.sh" in script        # GENUS resolves the word from Wikidata itself
    assert "--source curated" not in script      # no hand-typed Q-id mappings anymore
    assert "expresses" in script                 # the review report shows the resolved concept


def test_cron_installation_writes_timestamped_ticks():
    script = (ROOT / "deploy" / "pi_install_cron.sh").read_text(encoding="utf-8")

    assert "[TICK] observe-all" in script
    assert "[TICK] state-refresh" in script
    assert "[TICK] clock-check" in script
    assert "[TICK] weather" in script
    assert "[TICK] weather-2" in script
    assert "[TICK] experience-scan" in script
    assert "[TICK] doctor" in script
    assert "[TICK] repo-observe" in script
    assert "[TICK] status-publish" in script
    # status-publish is STICKY: a persisted marker survives cron reinstalls that don't
    # carry the env flag (the regression that silently dropped the daily status tick)
    assert "status_publish.enabled" in script
    assert "STATUS_PUBLISH" in script
    assert r"date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ" in script


def test_weather_membrane_fetches_number_only_and_keeps_location_at_edge():
    script = (ROOT / "deploy" / "observe_weather.sh").read_text(encoding="utf-8")

    # HTTP lives at the edge; only the number is fed to the core.
    assert "observe-weather" in script
    assert "--temp-outside" in script
    assert "--source" in script
    assert "open-meteo" in script
    assert "temperature_2m" in script
    # location is configured here and never handed to the core
    assert "GENUS_WEATHER_LAT" in script
    assert "GENUS_WEATHER_LON" in script
    # a failed fetch records nothing — absence is not a reading
    assert "no observation recorded" in script
    assert 'if [ -z "$temp" ]' in script
    assert "paused" in script  # honors the global pause switch
    # rich fields (P4 Schnitt 2): everything the source gives, each its own claim (number only)
    assert "apparent_temperature" in script and "precipitation_probability_max" in script
    assert "observe-assertion" in script and "weather.rain_prob" in script


def test_second_weather_membrane_feeds_observe_assertion_number_only():
    script = (ROOT / "deploy" / "observe_weather_second.sh").read_text(encoding="utf-8")

    # an independent second source for the SAME claim, fed via the assertion entry point
    assert "observe-assertion" in script
    assert "--claim-key" in script
    assert "weather.temp_outside" in script
    assert "--source" in script
    assert "wttr.in" in script
    assert "temp_C" in script
    # location lives at the edge; only the number crosses
    assert "GENUS_WEATHER_LAT" in script
    assert "GENUS_WEATHER_LON" in script
    # a failed fetch records nothing — absence is not a reading
    assert "no observation recorded" in script
    assert 'if [ -z "$temp" ]' in script


def test_word_membrane_parses_structure_and_feeds_relate():
    script = (ROOT / "deploy" / "observe_word.sh").read_text(encoding="utf-8")

    # structured knowledge acquisition: the membrane parses word-meaning structure
    # (part of speech, synonyms, antonyms -- no model) and hands in relations; HTTP at edge.
    assert "relate" in script
    assert "--source" in script
    assert "dictionaryapi" in script
    assert "synonym" in script
    assert "is_a" in script
    # a failed fetch records nothing
    assert "nothing recorded" in script
    assert 'if [ -z "$facts" ]' in script


def test_acquire_gaps_loop_asks_genus_and_fetches_each():
    script = (ROOT / "deploy" / "acquire_gaps.sh").read_text(encoding="utf-8")

    # the loop asks GENUS what it doesn't know, then the membrane fetches each word
    assert "gaps" in script
    assert "observe_word.sh" in script  # the default membrane
    assert "GENUS_ACQUIRE_SCRIPT" in script  # configurable: e.g. observe_wort.sh (German)
    assert "GENUS_GAP_PREDICATES" in script  # configurable: e.g. is_a to climb a hierarchy
    assert "GENUS_GAP_LIMIT" in script  # bounded per round -- gentle on the API
    assert "no gaps" in script          # the closed-vocabulary case records nothing


def test_german_word_membrane_parses_hierarchy_and_feeds_relate():
    script = (ROOT / "deploy" / "observe_wort.sh").read_text(encoding="utf-8")

    # German word meaning WITH hierarchy: synonyms + Oberbegriffe (is_a), the chains
    # inference needs; HTTP at the edge, primary sense only.
    assert "relate" in script
    assert "openthesaurus" in script
    assert "is_a" in script
    assert "synonym" in script
    assert "supersynsets" in script
    assert "nothing recorded" in script


def test_concept_membrane_feeds_both_layers_from_wikidata():
    script = (ROOT / "deploy" / "observe_konzept.sh").read_text(encoding="utf-8")

    # Wikidata as a language-neutral concept graph: Q-id concepts, P279 = is_a hierarchy,
    # labels+aliases per language = the lexemes. Both layers fed via `relate`.
    assert "relate" in script
    assert "wikidata" in script
    assert "wbgetclaims" in script          # P279 parents -- small, reliable REST call
    assert "wbgetentities" in script        # labels + aliases
    assert "P279" in script
    assert "expresses" in script            # word@lang -> concept (label + aliases, for lookup)
    assert "\\tlabel\\t" in script          # the canonical label, for readable display
    assert "is_a" in script                 # concept -> parent concept
    assert "wbsearchentities" in script     # word -> candidates
    assert "limit=10" in script             # several candidates, not just the top hit
    assert "sitelinks" in script            # pick the most-prominent concept FROM THE SOURCE
    assert "nothing recorded" in script     # a failed/empty fetch records nothing


def test_background_learner_runs_continuously_and_is_pausable():
    script = (ROOT / "deploy" / "pi_learn.sh").read_text(encoding="utf-8")
    assert "observe_konzept.sh" in script   # learns each word by resolving from the source
    assert "wortschatz_de.txt" in script     # the word stream (breadth)
    assert "while true" in script            # continuous, fortlaufend
    assert "paused" in script                # honors the global pause switch every iteration
    assert "CURSOR" in script and "cursor" in script  # resumes where it left off
    assert "DELAY" in script                 # paced between words (politeness to the source)
    assert "loadavg" in script               # yields when the box is busy


def test_learner_gap_climb_remembers_attempts_and_has_a_retry_ttl():
    script = (ROOT / "deploy" / "pi_learn.sh").read_text(encoding="utf-8")
    # the fix for the pinned-on-one-gap loop: a bounded attempts memory with a retry TTL
    assert "GAP_ATTEMPTS" in script and "GAP_RETRY_TTL" in script
    assert "grep -vxF" in script          # rotate past gaps already tried within the TTL


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash to run the learner script")
def test_learner_gap_climb_rotates_past_an_unclosable_gap(tmp_path):
    # Regression (found live: 20k+ repeats of one Q-id in 24h). A gap whose source cannot close
    # it (no P279 -> never becomes an is_a subject) must NOT pin the learner; it must rotate on.
    repo = tmp_path
    (repo / ".venv" / "bin").mkdir(parents=True)
    shutil.copy(ROOT / "deploy" / "pi_learn.sh", repo / "pi_learn.sh")
    (repo / "observe_konzept.sh").write_text('#!/usr/bin/env bash\necho "$1" >> "$OBSERVE_LOG"\n')
    (repo / "observe_lexem.sh").write_text("#!/usr/bin/env bash\ntrue\n")
    (repo / "observe_dbnary.sh").write_text("#!/usr/bin/env bash\ntrue\n")
    # gaps returns a STABLE list whose first entry is the unclosable one (stays a gap forever)
    (repo / ".venv" / "bin" / "genus").write_text(
        '#!/usr/bin/env bash\nif [ "$1" = "gaps" ]; then printf "Q_STUCK\\nQ_A\\nQ_B\\n"; fi\n')
    (repo / "empty.txt").write_text("")           # exhausted word list -> straight to gap climbing
    for f in ("pi_learn.sh", "observe_konzept.sh", "observe_lexem.sh", "observe_dbnary.sh"):
        os.chmod(repo / f, 0o755)
    os.chmod(repo / ".venv" / "bin" / "genus", 0o755)
    observed = repo / "observed.txt"
    observed.write_text("")
    env = {
        **os.environ,
        "GENUS_REPO_DIR": str(repo), "GENUS_DB_PATH": str(repo / "db.sqlite3"),
        "GENUS_LOG_DIR": str(repo / "logs"), "GENUS_LEARN_WORDLIST": str(repo / "empty.txt"),
        "GENUS_LEARN_ONCE": "1", "GENUS_EMBED_PYTHON": "/nonexistent", "OBSERVE_LOG": str(observed),
    }
    for _ in range(3):
        subprocess.run(["bash", str(repo / "pi_learn.sh")], env=env, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    climbed = observed.read_text().split()
    assert climbed == ["Q_STUCK", "Q_A", "Q_B"]   # rotated -- NOT ["Q_STUCK", "Q_STUCK", "Q_STUCK"]
    # the unclosable gap is remembered so it won't be retried until the TTL elapses
    attempts = (repo / "learn.gap_attempts").read_text()
    assert "Q_STUCK" in attempts


def test_learner_offers_a_targeted_fachliste_ahead_of_general_breadth():
    # Punkt 3 (Fachwissen gezielt aufbauen): a domain list is a NEW priority tier, tried before
    # the general breadth lists -- not just one more equally-weighted round-robin entry (that
    # would dilute "gezielt" into "genauso schnell wie 5000 andere Wörter")
    script = (ROOT / "deploy" / "pi_learn.sh").read_text(encoding="utf-8")
    assert "FACHLISTEN" in script and "learn_fach" in script
    assert "learn_fach || learn_next || learn_gap" in script


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash to run the learner script")
def test_learner_fachliste_is_learned_before_the_general_wordlist(tmp_path):
    repo = tmp_path
    (repo / ".venv" / "bin").mkdir(parents=True)
    shutil.copy(ROOT / "deploy" / "pi_learn.sh", repo / "pi_learn.sh")
    (repo / "observe_konzept.sh").write_text('#!/usr/bin/env bash\necho "$1" >> "$OBSERVE_LOG"\n')
    (repo / "observe_lexem.sh").write_text("#!/usr/bin/env bash\ntrue\n")
    (repo / "observe_dbnary.sh").write_text("#!/usr/bin/env bash\ntrue\n")
    for f in ("pi_learn.sh", "observe_konzept.sh", "observe_lexem.sh", "observe_dbnary.sh"):
        os.chmod(repo / f, 0o755)
    (repo / "allgemein.txt").write_text("Tisch\nStuhl\n")
    (repo / "fachliste.txt").write_text("Datenbank\nAlgorithmus\n")
    observed = repo / "observed.txt"
    observed.write_text("")
    env = {
        **os.environ,
        "GENUS_REPO_DIR": str(repo), "GENUS_DB_PATH": str(repo / "db.sqlite3"),
        "GENUS_LOG_DIR": str(repo / "logs"), "GENUS_LEARN_WORDLIST": str(repo / "allgemein.txt"),
        "GENUS_LEARN_FACHLISTEN": str(repo / "fachliste.txt"),
        "GENUS_LEARN_ONCE": "1", "GENUS_EMBED_PYTHON": "/nonexistent", "OBSERVE_LOG": str(observed),
    }
    for _ in range(4):
        subprocess.run(["bash", str(repo / "pi_learn.sh")], env=env, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # both Fachliste words learned FIRST, general breadth only once the Fachliste is exhausted
    assert observed.read_text().split() == ["Datenbank", "Algorithmus", "Tisch", "Stuhl"]


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash to run the learner script")
def test_learner_without_a_fachliste_behaves_exactly_as_before(tmp_path):
    repo = tmp_path
    (repo / ".venv" / "bin").mkdir(parents=True)
    shutil.copy(ROOT / "deploy" / "pi_learn.sh", repo / "pi_learn.sh")
    (repo / "observe_konzept.sh").write_text('#!/usr/bin/env bash\necho "$1" >> "$OBSERVE_LOG"\n')
    (repo / "observe_lexem.sh").write_text("#!/usr/bin/env bash\ntrue\n")
    (repo / "observe_dbnary.sh").write_text("#!/usr/bin/env bash\ntrue\n")
    for f in ("pi_learn.sh", "observe_konzept.sh", "observe_lexem.sh", "observe_dbnary.sh"):
        os.chmod(repo / f, 0o755)
    (repo / "allgemein.txt").write_text("Tisch\nStuhl\n")
    observed = repo / "observed.txt"
    observed.write_text("")
    env = {
        **os.environ,
        "GENUS_REPO_DIR": str(repo), "GENUS_DB_PATH": str(repo / "db.sqlite3"),
        "GENUS_LOG_DIR": str(repo / "logs"), "GENUS_LEARN_WORDLIST": str(repo / "allgemein.txt"),
        "GENUS_LEARN_ONCE": "1", "GENUS_EMBED_PYTHON": "/nonexistent", "OBSERVE_LOG": str(observed),
    }
    env.pop("GENUS_LEARN_FACHLISTEN", None)
    for _ in range(2):
        subprocess.run(["bash", str(repo / "pi_learn.sh")], env=env, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert observed.read_text().split() == ["Tisch", "Stuhl"]


def test_learner_installer_is_a_continuous_idle_priority_service():
    script = (ROOT / "deploy" / "pi_install_learner.sh").read_text(encoding="utf-8")
    assert "genus-learner.service" in script
    assert "Type=simple" in script                   # a long-lived daemon, not a timer
    assert "Restart=always" in script                # stays alive across reboots/hiccups
    assert "Nice=19" in script                       # lowest CPU niceness
    assert "CPUSchedulingPolicy=idle" in script      # SCHED_IDLE
    assert "IOSchedulingClass=idle" in script        # idle IO -- yields to everything
    assert "genus pause" in script                   # documents how to stop it


def test_deuter_installer_puts_llama_cpp_in_the_shared_venv_not_a_new_one():
    script = (ROOT / "deploy" / "pi_install_deuter.sh").read_text(encoding="utf-8")
    # unlike the embedder, this model must stay warm inside the bot's own process -- no new venv
    assert "llama-cpp-python" in script
    assert ".venv" in script
    assert "embed-venv" not in script
    assert "qwen2.5-1.5b-instruct-q4_k_m.gguf" in script
    assert "models" in script                        # a permanent home under ~/.genus/


def test_deuter_module_segments_and_never_writes():
    script = (ROOT / "deploy" / "deuter.py").read_text(encoding="utf-8")
    # liest eine Nachricht als LISTE von Segmenten (ISO 24617-2), waehlt aus einer Zwicky-
    # geprueften, erschoepfenden Liste (kein Freitext-Ausweg mehr), erfindet nie Fakten
    assert "DEFAULT_ABSICHTEN" in script
    assert "_JSON_ARRAY" in script             # liest ein Array, nicht ein einzelnes Objekt
    assert "_looks_like_question" in script    # the deterministic statement-veto stays
    assert "except Exception" in script and "return None" in script   # never raises
    for forbidden in ("import governance", "import proposals", "control.pause", "teach_relation"):
        assert forbidden not in script


def test_verstehen_seed_script_is_one_clean_idempotent_apply():
    script = (ROOT / "deploy" / "seed_verstehen.sh").read_text(encoding="utf-8")
    assert "verstehen.seed_raster" in script
    assert "conn.commit()" in script
    assert "idempotent" in script.lower()      # re-running must never duplicate the raster


def test_ziele_seed_script_is_one_clean_idempotent_apply():
    script = (ROOT / "deploy" / "seed_ziele.sh").read_text(encoding="utf-8")
    assert "ziele.seed_ziele" in script
    assert "conn.commit()" in script
    assert "idempotent" in script.lower()      # re-running must never duplicate the goal graph
    assert "fehlende_faehigkeiten" in script   # the apply names the honest gaps out loud


def test_migriere_notizen_script_is_one_clean_idempotent_apply():
    script = (ROOT / "deploy" / "migriere_notizen.sh").read_text(encoding="utf-8")
    assert "erinnerung.migriere_notizen" in script
    assert "conn.commit()" in script
    assert "idempotent" in script.lower()      # re-running must find nothing left to migrate


def test_stimme_module_only_rephrases_never_invents():
    script = (ROOT / "deploy" / "stimme.py").read_text(encoding="utf-8")
    # the faithfulness leash: every quoted word/number must survive, or it fails to None
    assert "_QUOTED" in script and "_NUMBER" in script
    assert "except Exception" in script and "return None" in script   # never raises
    # reuses the SAME model file as the Deuter -- no separate install/download needed
    assert "qwen2.5-1.5b-instruct-q4_k_m.gguf" in script
    for forbidden in ("import governance", "import proposals", "control.pause", "teach_relation"):
        assert forbidden not in script


def test_deuter_and_stimme_each_get_their_own_model_not_shared():
    # live gemessen (2026-07-03): ein geteiltes Modell verwarf bei jedem Stimme-Aufruf den
    # Deuter-Prompt-Cache (26s statt 3s beim naechsten Deuter-Aufruf) -- jede Rolle hat jetzt
    # ihr eigenes warmes Modell
    bot = (ROOT / "deploy" / "telegram_bot.py").read_text(encoding="utf-8")
    assert "deuter.get_model" not in bot
    assert "stimme=stimme.formuliere" in bot
    deuter_script = (ROOT / "deploy" / "deuter.py").read_text(encoding="utf-8")
    assert "def get_model" not in deuter_script


def test_learner_wordlist_is_words_only():
    import re as _re
    lines = (ROOT / "deploy" / "wortschatz_de.txt").read_text(encoding="utf-8").splitlines()
    words = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        assert " " not in s and "\t" not in s, f"one word per line: {line!r}"
        assert not _re.fullmatch(r"Q[0-9]+", s) and "@" not in s  # words, not Q-ids
        words.append(s)
    assert len(words) >= 50                  # real breadth for the learner to chew
    assert len(words) == len(set(words))     # no duplicates


def test_is_a_cycle_resolution_retracts_only_the_clear_reversals():
    script = (ROOT / "deploy" / "resolve_is_a_cycles.sh").read_text(encoding="utf-8")

    # resolves via the existing retraction machinery, source-precisely (each edge is Wikidata-only)
    assert "unrelate" in script
    assert "--source wikidata" in script
    # the three clearly-reversed 2-cycles: retract the wrong edge, keep the reverse subtype
    for qid in ("Q41415", "Q118489612", "Q1137365", "Q854429", "Q1756942", "Q11348"):
        assert qid in script
    # the abstract 3-cycle stays FLAGGED, never blind-retracted ("nichts blind löschen")
    assert "Q104450446" not in script and "Q340169" not in script and "Q17538423" not in script


def test_clock_check_probes_ntp_and_records_operation_event():
    script = (ROOT / "deploy" / "pi_clock_check.sh").read_text(encoding="utf-8")

    assert "operation clock-check" in script
    assert "NTPSynchronized" in script
    assert "--status ok" in script
    assert "--status fail" in script


def test_repo_membrane_counts_only_and_feeds_observe_repo():
    script = (ROOT / "deploy" / "observe_repo_from_x1.sh").read_text(encoding="utf-8")

    assert "observe-repo" in script
    assert "--commits-per-day" in script
    assert "--lines-changed" in script
    assert "--measured-on" in script
    # counts only: git output must be reduced to numbers, never sent as content
    assert "wc -l" in script
    assert "--numstat" in script
    assert "git -C" in script


def test_repo_pi_membrane_fetches_remote_and_counts_only():
    script = (ROOT / "deploy" / "observe_repo_on_pi.sh").read_text(encoding="utf-8")

    # Robust Pi-side variant: fetch the published history and count over the
    # remote-tracking branch, independent of the workstation.
    assert "git -C" in script
    assert "fetch" in script
    assert "origin/" in script
    assert "observe-repo" in script
    assert "--measured-on pi" in script
    # counts only, same as the X1 membrane
    assert "wc -l" in script
    assert "--numstat" in script
    # a failed fetch records nothing — absence is not quiet
    assert "no observation recorded" in script


def test_pi_deploy_rebuilds_projection_before_integrity():
    script = (ROOT / "deploy" / "pi_deploy.sh").read_text(encoding="utf-8")

    # A projection-logic change must be applied to the live projection before the
    # integrity check, otherwise the deploy aborts on the stored-vs-replay mismatch.
    assert "rebuilding projection" in script
    assert "genus replay || true" in script
    # tests run hermetically -- the ambient GENUS_* (incl. the live DB path + pause flag)
    # must be unset so the suite never touches the live ledger or sees the real pause state
    assert "env -u GENUS_DB_PATH" in script and "GENUS_PAUSE_FILE" in script
    # the tolerant rebuild command must precede the integrity-check command
    assert script.index("genus replay || true") < script.index("genus integrity check")


def test_network_watchdog_records_operation_events_and_governed_recovery():
    watchdog = (ROOT / "deploy" / "pi_network_watchdog.sh").read_text(
        encoding="utf-8"
    )
    installer = (ROOT / "deploy" / "pi_install_network_watchdog.sh").read_text(
        encoding="utf-8"
    )

    assert "operation network-check" in watchdog
    assert "operation recovery-result" in watchdog
    assert "--action \"$action\"" in watchdog
    assert "systemctl reboot" in watchdog
    # the reboot threshold is GENUS's own self-calibrated value, asked live each time -- no
    # second, separately-typed copy of the number lives in the script; a manual override and a
    # numeric-safe fallback both still work if the lookup is unavailable
    assert "governance reboot-threshold --value-only" in watchdog
    assert "GENUS_NETWORK_REBOOT_THRESHOLD" in watchdog
    assert "reboot_threshold=3" in watchdog
    # supervisor role: the watchdog also keeps the background learner alive (no extra sudo)
    assert "ensure_learner" in watchdog
    assert "pi_learn.sh" in watchdog
    assert "systemd-run" in watchdog
    assert "paused" in watchdog  # but respects the pause switch
    assert "genus-network-watchdog.service" in installer
    assert "OnUnitActiveSec=5min" in installer
    assert "GENUS_USER" in installer


def test_lexeme_membrane_captures_grammatical_gender_for_nouns():
    script = (ROOT / "deploy" / "observe_lexem.sh").read_text(encoding="utf-8")

    # P5185 (grammatical gender) is a claim on the LEXEME itself, verified live against Wikidata
    # (Hund->masculine, Katze->feminine, Sonne->feminine, Mädchen/Fräulein->neuter (-chen/-lein
    # always neuter, overriding natural gender)) -- the raw material for SYSTEME's 2nd rule-domain
    # (gender-by-suffix induction). Only meaningful for nouns (lexicalCategory Q1084).
    assert "P5185" in script
    assert "grammatical_gender" in script
    assert "Q499327" in script and "maskulin" in script
    assert "Q1775415" in script and "feminin" in script
    assert "Q1775461" in script and "neutrum" in script
    assert 'cat == "Q1084"' in script   # gated to nouns -- gender is meaningless for verbs etc.


def test_gender_backfill_is_resumable_and_skips_already_known():
    script = (ROOT / "deploy" / "backfill_gender.sh").read_text(encoding="utf-8")

    # one-time, resumable (own cursor -- distinct from the main learner's), respects pause/load
    assert "backfill_gender.cursor" in script
    assert "PAUSED" in script
    assert "MAX_LOAD" in script
    # idempotent: skips a noun that already has a recorded gender rather than re-fetching
    assert "has_gender" in script
    assert "grammatical_gender" in script
    assert "already gendered" in script and "skipping" in script
    # reuses the existing membrane -- no new fetch logic duplicated
    assert "observe_lexem.sh" in script
    # unlike pi_learn.sh's infinite loop, this one reports completion and stops
    assert "backfill complete" in script


def test_telegram_bot_installer_keeps_the_token_out_of_the_unit_file():
    script = (ROOT / "deploy" / "pi_install_telegram_bot.sh").read_text(encoding="utf-8")
    # secrets live in their own 0600 files, never inline in the world-readable systemd unit
    assert "chmod 600" in script
    assert "TOKEN_FILE" in script
    assert "GENUS_TELEGRAM_ALLOWED_IDS" in script
    assert "$BOT_TOKEN" not in script.split("ExecStart=")[1].split("\n")[0]  # not in ExecStart line
    # normal priority (responsive), unlike the deliberately idle-priority learner
    assert "CPUSchedulingPolicy=idle" not in script
    assert "Restart=always" in script


def test_telegram_bot_answers_only_never_writes():
    script = (ROOT / "deploy" / "telegram_bot.py").read_text(encoding="utf-8")
    # answer-only membrane: routes through companion.respond (read-only), never touches
    # pause/resume, governance, teach-relation, or any state-changing command
    assert "companion.respond" in script
    assert "allow" in script.lower()
    for forbidden in ("import governance", "import proposals", "control.pause", "control.resume",
                      "teach_relation", "record_proposal"):
        assert forbidden not in script


def test_watchdog_supervises_the_telegram_bot_at_normal_priority():
    script = (ROOT / "deploy" / "pi_network_watchdog.sh").read_text(encoding="utf-8")
    # the watchdog keeps the bridge alive like the learner, but responsive (not idle-scheduled)
    assert "ensure_telegram_bot" in script
    assert "deploy/telegram_bot.py" in script
    # a no-op unless configured: needs both the token file and the allow-list env file
    assert "telegram_bot_token" in script and "telegram_bot.env" in script
    # reads the allow-list by grep, never by sourcing/executing the env file
    assert "GENUS_TELEGRAM_ALLOWED_IDS=" in script
    # the bot's systemd-run must NOT carry the learner's idle scheduling (it should be responsive);
    # the idle properties belong only to ensure_learner, above ensure_telegram_bot
    bot_fn = script.split("ensure_telegram_bot()")[1].split("json_field()")[0]
    assert "CPUSchedulingPolicy=idle" not in bot_fn
    assert "Nice=19" not in bot_fn
