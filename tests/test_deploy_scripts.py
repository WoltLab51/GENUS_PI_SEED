from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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
    assert "genus-network-watchdog.service" in installer
    assert "OnUnitActiveSec=5min" in installer
    assert "GENUS_USER" in installer
