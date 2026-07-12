# GENUS_PI_SEED_v0.6 — Codex Prompt: Habitat Sensors

> **Status:** archived · **Build authority:** none
> Historical build prompt. This file records the requested v0.6 state, including
> forecasts that were later implemented. Current behavior is authoritative in code
> and tests; the subsequent chronology lives in the
> [Build Journal](../history/BUILD_JOURNAL.md).

Read the existing codebase in this repository carefully before writing
anything. Understand the patterns in sensor.py, rules.py, reactors.py,
cli.py and tests/ — then extend them.

---

## Was in v0.6 gebaut wird

Drei neue Sensoren, die jeder eine andere Erkenntnisform üben:

```
system.disk_percent     Trend (steigt/fällt/stabil — neuer Belief-Typ)
system.activity         binär aktiv/idle (Rhythmus — passt NICHT ins high/normal Schema)
system.temperature      Korrelation mit CPU (übt State + Widerspruch)
```

Plus: erste UNIX-cron-Anleitung für automatische Sammlung auf dem Pi.

---

## Hard rules — wie immer

- event_log: no UPDATE, no DELETE, ever
- belief_projection: fully rebuildable from replay
- confidence: calculated, never stored
- no LLM, no HTTP calls
- derivation: never null
- grep -r "anthropic|openai|requests|httpx" genus/ → empty

---

## 1. sensor.py — neue Funktionen hinzufügen

```python
import psutil

def read_disk(path: str = "/") -> dict:
    """
    Disk usage for given path.
    Returns raw observation dict — no interpretation.
    """
    usage = psutil.disk_usage(path)
    return {
        "source": "psutil.disk_usage",
        "raw_value": usage.percent,
        "unit": "percent",
        "interval": 0.0,
        "path": path,
    }

def mock_disk(value: float) -> dict:
    return {
        "source": "mock",
        "raw_value": value,
        "unit": "percent",
        "interval": 0.0,
        "path": "/",
    }

def read_activity() -> dict:
    """
    System activity: active if users are logged in AND cpu > idle threshold.
    Returns binary: raw_value = 1.0 (active) or 0.0 (idle).
    No interpretation — 1/0 is the observation, belief is formed by rules.
    """
    users = psutil.users()
    cpu = psutil.cpu_percent(interval=0.5)
    active = 1.0 if (len(users) > 0 and cpu > 2.0) else 0.0
    return {
        "source": "psutil.activity",
        "raw_value": active,
        "unit": "binary",
        "interval": 0.5,
        "user_count": len(users),
        "cpu_sample": cpu,
    }

def mock_activity(value: float) -> dict:
    """value: 1.0 = active, 0.0 = idle"""
    return {
        "source": "mock",
        "raw_value": value,
        "unit": "binary",
        "interval": 0.0,
        "user_count": 1 if value > 0 else 0,
        "cpu_sample": 50.0 if value > 0 else 0.5,
    }

def read_temperature() -> dict | None:
    """
    CPU temperature via psutil.sensors_temperatures().
    Returns None gracefully if not available (e.g. on some laptops/VMs).
    Uses first available coretemp or acpitz reading.
    """
    try:
        temps = psutil.sensors_temperatures()
    except (AttributeError, NotImplementedError):
        return None
    if not temps:
        return None
    for key in ("coretemp", "acpitz", "cpu_thermal", "k10temp"):
        if key in temps and temps[key]:
            return {
                "source": f"psutil.sensors_temperatures.{key}",
                "raw_value": temps[key][0].current,
                "unit": "celsius",
                "interval": 0.0,
            }
    # fallback: first available sensor
    first_key = next(iter(temps))
    if temps[first_key]:
        return {
            "source": f"psutil.sensors_temperatures.{first_key}",
            "raw_value": temps[first_key][0].current,
            "unit": "celsius",
            "interval": 0.0,
        }
    return None

def mock_temperature(value: float) -> dict:
    return {
        "source": "mock",
        "raw_value": value,
        "unit": "celsius",
        "interval": 0.0,
    }
```

---

## 2. rules.py — neue Einträge in RULES und neue Regel-Art

### Neue Konstanten hinzufügen

```python
DISK_METRIC_KEY        = "system.disk_percent"
ACTIVITY_METRIC_KEY    = "system.activity"
TEMPERATURE_METRIC_KEY = "system.temperature"

DISK_HIGH_THRESHOLD    = 85.0
DISK_LOW_THRESHOLD     = 60.0
TEMP_HIGH_THRESHOLD    = 75.0   # Celsius — Pi throttles at 80°
TEMP_LOW_THRESHOLD     = 55.0
DISK_DERIVATION        = "rule:disk_threshold_v1"
TEMPERATURE_DERIVATION = "rule:temperature_threshold_v1"
ACTIVITY_DERIVATION    = "rule:activity_binary_v1"
```

### RULES dict erweitern

```python
RULES = {
    CPU_METRIC_KEY: { ... },      # unverändert
    MEMORY_METRIC_KEY: { ... },   # unverändert
    DISK_METRIC_KEY: {
        "type": "threshold",
        "high_threshold": DISK_HIGH_THRESHOLD,
        "low_threshold": DISK_LOW_THRESHOLD,
        "claim_key": "system.disk",
        "derivation": DISK_DERIVATION,
        "contradiction_reason": "system.disk high contradicted by sustained normal readings",
    },
    TEMPERATURE_METRIC_KEY: {
        "type": "threshold",
        "high_threshold": TEMP_HIGH_THRESHOLD,
        "low_threshold": TEMP_LOW_THRESHOLD,
        "claim_key": "system.temperature",
        "derivation": TEMPERATURE_DERIVATION,
        "contradiction_reason": "system.temperature high contradicted by sustained normal readings",
    },
    ACTIVITY_METRIC_KEY: {
        "type": "binary",          # NEU — eigene Regel-Art
        "active_value": "active",
        "idle_value": "idle",
        "claim_key": "system.activity",
        "derivation": ACTIVITY_DERIVATION,
    },
}
```

### apply_threshold erweitern — Binary-Zweig

In `apply_threshold(conn, metric_key)` nach dem Lesen von `rule = RULES[metric_key]`:

```python
if rule.get("type") == "binary":
    return apply_binary_rule(conn, metric_key, rule)
# ... bestehende threshold-Logik unverändert
```

### apply_binary_rule — neue Funktion

```python
def apply_binary_rule(conn, metric_key: str, rule: dict) -> list[str]:
    """
    Binary rule: raw_value == 1.0 → active_value belief,
                 raw_value == 0.0 → idle_value belief.

    Activity is different from threshold:
    - We only need ONE reading, not WINDOW_SIZE
    - A belief is created or superseded immediately on change
    - No "weakened" state — it's binary, either or
    """
    window = _latest_evidence_window(conn, metric_key, n=1)
    if not window:
        return []

    latest = window[0]
    value = float(latest["metric_value"])
    event_id = int(latest["id"])
    claim_key = rule["claim_key"]
    derivation = rule["derivation"]
    written: list[str] = []

    new_value = rule["active_value"] if value >= 1.0 else rule["idle_value"]
    current = projection.active_belief(conn, claim_key)

    if current is None:
        # Erster Belief
        belief_id = projection.next_belief_id(conn)
        belief_event_id = ledger.append(conn, "belief_created", {
            "belief_id": belief_id,
            "claim_key": claim_key,
            "claim_value": new_value,
            "derivation": derivation,
            "supporting_events": [event_id],
        })
        projection.apply_belief_created(conn, {
            "belief_id": belief_id,
            "claim_key": claim_key,
            "claim_value": new_value,
            "derivation": derivation,
            "supporting_events": [event_id],
            "_event_created_at": ledger.event_created_at(conn, belief_event_id),
        })
        written.append("belief_created")

    elif current["claim_value"] == new_value:
        # Bestätigung — gleicher Zustand
        conf_event_id = ledger.append(conn, "belief_confirmed", {
            "belief_id": int(current["id"]),
            "new_supporting_event": event_id,
        })
        projection.apply_belief_confirmed(conn, {
            "belief_id": int(current["id"]),
            "new_supporting_event": event_id,
            "_event_created_at": ledger.event_created_at(conn, conf_event_id),
        })
        written.append("belief_confirmed")

    else:
        # Zustand wechselt — sofortige Supersession, kein "weakened"
        new_belief_id = projection.next_belief_id(conn)
        sup_payload = {
            "old_belief_id": int(current["id"]),
            "new_belief_id": new_belief_id,
            "claim_key": claim_key,
            "claim_value": new_value,
            "derivation": derivation,
            "supporting_events": [event_id],
            "reason": f"activity changed to {new_value}",
        }
        sup_event_id = ledger.append(conn, "belief_superseded", sup_payload)
        sup_payload["_event_created_at"] = ledger.event_created_at(conn, sup_event_id)
        projection.apply_belief_superseded(conn, sup_payload)
        written.append("belief_superseded")

    return written
```

### _latest_evidence_window — n-Parameter hinzufügen

```python
def _latest_evidence_window(conn, metric_key: str, n: int = WINDOW_SIZE):
    rows = conn.execute(
        """
        SELECT id, json_extract(payload, '$.metric_value') AS metric_value
        FROM event_log
        WHERE event_type = 'evidence_recorded'
          AND json_extract(payload, '$.metric_key') = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (metric_key, n),
    ).fetchall()
    ...
```

---

## 3. reactors.py — neue observe-Funktionen

```python
def observe_disk_reading(conn, reading: dict) -> dict:
    return observe_system_reading(conn, reading, rules.DISK_METRIC_KEY)

def observe_activity_reading(conn, reading: dict) -> dict:
    return observe_system_reading(conn, reading, rules.ACTIVITY_METRIC_KEY)

def observe_temperature_reading(conn, reading: dict) -> dict:
    return observe_system_reading(conn, reading, rules.TEMPERATURE_METRIC_KEY)
```

---

## 4. cli.py — neue Kommandos

```python
@main.command("observe-disk")
def observe_disk() -> None:
    reading = sensor.read_disk()
    conn = get_conn()
    try:
        result = reactors.observe_disk_reading(conn, reading)
        _print_observation_result("DSK", reading, result)
        _print_active_belief_summary(conn)
    finally:
        conn.close()

@main.command("observe-activity")
def observe_activity() -> None:
    reading = sensor.read_activity()
    conn = get_conn()
    try:
        result = reactors.observe_activity_reading(conn, reading)
        _print_observation_result("ACT", reading, result)
        _print_active_belief_summary(conn)
    finally:
        conn.close()

@main.command("observe-temperature")
def observe_temperature() -> None:
    reading = sensor.read_temperature()
    if reading is None:
        click.echo("[OBS] TEMP: not available on this system")
        return
    conn = get_conn()
    try:
        result = reactors.observe_temperature_reading(conn, reading)
        _print_observation_result("TMP", reading, result)
        _print_active_belief_summary(conn)
    finally:
        conn.close()

@main.command("observe-all")
def observe_all() -> None:
    """Run all available sensors in one call."""
    conn = get_conn()
    try:
        for label, reading_fn, observe_fn in [
            ("CPU", sensor.read_cpu,      reactors.observe_cpu_reading),
            ("MEM", sensor.read_memory,   reactors.observe_memory_reading),
            ("DSK", sensor.read_disk,     reactors.observe_disk_reading),
            ("ACT", sensor.read_activity, reactors.observe_activity_reading),
        ]:
            reading = reading_fn()
            result = observe_fn(conn, reading)
            _print_observation_result(label, reading, result)

        temp = sensor.read_temperature()
        if temp is not None:
            result = reactors.observe_temperature_reading(conn, temp)
            _print_observation_result("TMP", temp, result)
        else:
            click.echo("[OBS] TMP: not available on this system")

        _print_active_belief_summary(conn)
    finally:
        conn.close()
```

---

## 5. Tests

### tests/test_disk.py

```
test_high_disk_creates_belief
    3x mock_disk(90.0) → belief system.disk=high is active

test_low_after_high_disk_supersedes
    3x mock_disk(90.0) then 3x mock_disk(40.0)
    → old belief superseded, new belief active, old row still exists

test_disk_derivation_is_always_set
    derivation == rules.DISK_DERIVATION

test_disk_thresholds_are_binding
    DISK_HIGH_THRESHOLD == 85.0, DISK_LOW_THRESHOLD == 60.0
```

### tests/test_activity.py

```
test_active_creates_active_belief
    mock_activity(1.0) → belief system.activity=active

test_idle_creates_idle_belief
    mock_activity(0.0) → belief system.activity=idle

test_activity_change_supersedes_immediately
    mock_activity(1.0) → mock_activity(0.0)
    → active belief superseded, idle belief active
    → NO belief_weakened event (binary rule, no weakening)

test_activity_does_not_require_window
    single mock_activity(1.0) → belief created immediately
    (binary rule needs only 1 reading, not WINDOW_SIZE)

test_activity_replay_stable
    5x activity readings alternating → replay() → identical state
```

### tests/test_temperature.py

```
test_high_temp_creates_belief
    3x mock_temperature(80.0) → belief system.temperature=high

test_temperature_unavailable_graceful
    if psutil.sensors_temperatures() not available →
    read_temperature() returns None, observe_temperature CLI prints
    "not available" and exits 0

test_temp_correlates_with_cpu (conceptual — no assertion on correlation itself,
    just that both beliefs can exist simultaneously)
    3x mock_cpu(92.0), 3x mock_temperature(80.0)
    → two independent active beliefs, neither interferes with the other
```

### tests/test_observe_all.py

```
test_observe_all_writes_base_events_for_each_sensor
    mock all sensors → observe-all CLI → event_log has
    observation_created + evidence_recorded for each sensor

test_observe_all_exits_zero (mock sensors)
```

---

## 6. README.md — neue Kommandos ergänzen

```bash
genus observe-disk
genus observe-activity
genus observe-temperature
genus observe-all        # alle Sensoren auf einmal
```

---

## 7. UNIX cron — erste automatische Sammlung

Keine cron-Logik im Python-Code. Stattdessen eine Anleitung in README.md:

```markdown
## Automatische Sammlung (cron)

Alle 5 Minuten alle Sensoren beobachten:

    crontab -e

    # GENUS — alle 5 Minuten beobachten
    */5 * * * * cd /path/to/GENUS_PI_SEED && .venv/bin/genus observe-all >> ~/.genus/cron.log 2>&1

Für den Pi (24/7):
    # Mit absolutem Pfad, genus installiert in venv
    */5 * * * * /home/pi/GENUS_PI_SEED/.venv/bin/genus \
        --db /home/pi/.genus/genus.sqlite3 observe-all >> /home/pi/.genus/cron.log 2>&1
```

---

## Definition of Done

```bash
pytest                                            # grün, zero warnings
genus observe-disk                                # schreibt Events, zeigt Belief
genus observe-activity                            # schreibt Events, zeigt Belief
genus observe-temperature                         # läuft oder zeigt "not available"
genus observe-all                                 # alle Sensoren, ein Aufruf
genus replay                                      # exit 0, state matches
genus integrity check                             # exit 0

grep -r "anthropic|openai|ollama" genus/          # leer
grep -r "requests|httpx|aiohttp|urllib.request" genus/  # leer
```

Und manuell prüfen:

- [ ] Nach 3x `observe-disk` mit Wert > 85: `genus beliefs show` zeigt
  `system.disk=high`
- [ ] `genus observe-activity` erzeugt Belief ohne WINDOW_SIZE abwarten
- [ ] Zwei activity-Wechsel hintereinander: keine `belief_weakened` Events,
  nur `belief_superseded`
- [ ] `genus replay` rekonstruiert activity-Beliefs identisch
- [ ] Alter activity-Belief nach Supersession noch in DB auffindbar

---

## Was diese Version beweist

```
Disk       → Trend-Belief-Typ ist möglich
Activity   → binäres Schema funktioniert neben threshold
Temperature → zwei Beliefs korrelieren, stören sich nicht
observe-all → UNIX-Komposition: ein Kommando, alle Augen
cron       → GENUS läuft ohne Daemon, UNIX-first
```

Fünf Sensoren, jeder übt eine andere Erkenntnisform. Die Grundausbildung
ist nach diesem Build vollständig — bereit für v0.7 Query. 🧬
