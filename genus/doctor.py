from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from pathlib import Path

from genus import hand, integrity, sealing, sensor


ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN_MODEL_TOKENS = ("anth" + "ropic", "op" + "enai", "ol" + "lama")
FORBIDDEN_NETWORK_TOKENS = (
    "req" + "uests",
    "ht" + "tpx",
    "aio" + "http",
    "urllib" + ".request",
)


@dataclass(frozen=True)
class Check:
    status: str
    name: str
    detail: str


def run(conn, *, db_path: str, core_id: str | None) -> list[Check]:
    checks: list[Check] = []
    checks.append(_db_check(db_path))
    checks.extend(_integrity_checks(conn))
    checks.extend(_sealing_checks(conn, core_id))
    checks.extend(_hand_checks(conn))
    checks.extend(_sensor_checks())
    checks.extend(_forbidden_import_checks())
    return checks


def has_failures(checks: list[Check]) -> bool:
    return any(check.status == "FAIL" for check in checks)


def _db_check(db_path: str) -> Check:
    return Check("OK", "database", f"path={db_path}")


def _integrity_checks(conn) -> list[Check]:
    try:
        result = integrity.check(conn)
    except Exception as exc:  # pragma: no cover - defensive boundary
        return [Check("FAIL", "integrity", str(exc))]
    if result["ok"]:
        return [Check("OK", "integrity", f"events={result['events']}")]
    return [Check("FAIL", "integrity", "; ".join(result["issues"]))]


def _hand_checks(conn) -> list[Check]:
    # Herzschlag-Wächter der ersten Hand: gibt es freigegebene, LÄNGST fällige, aber immer noch
    # ungesendete Erinnerungen, steht der Membran-Sende-Tick (hand_ausfuehren.sh) offenbar still.
    # WARN (kein FAIL): ein liegengebliebener, aber reparabler Zustand — doctor bleibt grün. Rein
    # lesend (keine Ledger-Ereignisse); der Jetzt-Zeitpunkt ist eine reine Anzeige-Entscheidung.
    try:
        jetzt = _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        spaet = hand.ueberfaellige(conn, jetzt)
    except Exception as exc:  # pragma: no cover - defensive boundary
        return [Check("FAIL", "hand-faellig", str(exc))]
    if not spaet:
        return [Check("OK", "hand-faellig", "keine ueberfaellige, ungesendete Hand")]
    ids = ", ".join(str(h["hand_id"]) for h in spaet)
    return [Check("WARN", "hand-faellig",
                  f"{len(spaet)} freigegebene, faellige, ungesendete Hand(e) (hand_id={ids}) "
                  f"— Sende-Tick steht? (deploy/hand_ausfuehren.sh)")]


def _sealing_checks(conn, core_id: str | None) -> list[Check]:
    checks: list[Check] = []
    if not sealing.is_active(conn):
        checks.append(
            Check("WARN", "sealing", "not initialized; run genus ledger seal-init")
        )
    else:
        issues = sealing.verify_chain(conn)
        if issues:
            checks.append(Check("FAIL", "sealing", "; ".join(issues)))
        else:
            head = sealing.head(conn)
            checks.append(
                Check(
                    "OK",
                    "sealing",
                    f"head_event_id={head['id']} head={head['seal']}",
                )
            )

    if core_id and core_id.strip():
        checks.append(Check("OK", "core-id", f"GENUS_CORE_ID={core_id.strip()}"))
    else:
        checks.append(
            Check(
                "WARN",
                "core-id",
                "GENUS_CORE_ID not set; anchor export will be skipped",
            )
        )
    return checks


def _sensor_checks() -> list[Check]:
    checks = []
    for name, reader in (
        ("sensor-cpu", sensor.read_cpu),
        ("sensor-memory", sensor.read_memory),
        ("sensor-disk", sensor.read_disk),
        ("sensor-activity", sensor.read_activity),
    ):
        checks.append(_read_required_sensor(name, reader))

    try:
        temperature = sensor.read_temperature()
    except Exception as exc:  # pragma: no cover - defensive boundary
        checks.append(Check("WARN", "sensor-temperature", str(exc)))
    else:
        if temperature is None:
            checks.append(Check("WARN", "sensor-temperature", "not available"))
        else:
            checks.append(
                Check(
                    "OK",
                    "sensor-temperature",
                    f"{temperature['raw_value']} {temperature['unit']}",
                )
            )
    return checks


def _read_required_sensor(name: str, reader) -> Check:
    try:
        reading = reader()
    except Exception as exc:
        return Check("FAIL", name, str(exc))
    return Check("OK", name, f"{reading['raw_value']} {reading['unit']}")


def _forbidden_import_checks() -> list[Check]:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "genus").rglob("*.py")
        if path.is_file()
    )
    checks = []
    model_hits = [token for token in FORBIDDEN_MODEL_TOKENS if token in text]
    network_hits = [token for token in FORBIDDEN_NETWORK_TOKENS if token in text]
    if model_hits:
        checks.append(Check("FAIL", "forbidden-model-imports", ", ".join(model_hits)))
    else:
        checks.append(Check("OK", "forbidden-model-imports", "none"))
    if network_hits:
        checks.append(Check("FAIL", "forbidden-network-imports", ", ".join(network_hits)))
    else:
        checks.append(Check("OK", "forbidden-network-imports", "none"))
    return checks
