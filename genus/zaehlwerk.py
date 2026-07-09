"""Das ZÄHLWERK des Planers (③ Scheibe C): Treffer / Rückfall / Anker-Verweigerung je
Absicht -- die Rohdaten für das Skill-Dashboard (④, das Thermometer). Ein JSONL-Puffer
am Membran-Rand (~/.genus/, wie der News-Puffer -- Ledger ≠ Memory: Gesprächs-Telemetrie
gehört nicht ins Ereignis-Ledger; ob ④ später eine Beförderung braucht, entscheidet ④).

FAIL-SILENT in beide Richtungen: eine Antwort darf NIE an der Telemetrie scheitern
(kaputter Pfad, volle Platte -> die Zählung fällt still aus, das Gespräch läuft weiter),
und ein kaputter Puffer liest sich als leer. Kein HTTP, kein Modell -- reine Datei.
"""
from __future__ import annotations

import json
import os
import time


def _pfad() -> str:
    return os.environ.get(
        "GENUS_PLANER_ZAEHLWERK",
        os.path.join(os.path.expanduser("~"), ".genus", "planer_zaehlwerk.jsonl"),
    )


def zaehle(absicht: str, ereignis: str) -> None:
    """Zählt EIN Ereignis (``treffer`` | ``rueckfall`` | ``anker_verweigert`` | ...) für eine
    Absicht -- append-only, fail-silent."""
    zeile = json.dumps({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "absicht": absicht,
        "ereignis": ereignis,
    }, ensure_ascii=False)
    try:
        pfad = _pfad()
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, "a", encoding="utf-8") as f:
            f.write(zeile + "\n")
    except OSError:
        pass   # Telemetrie bricht nie eine Antwort


def stand() -> dict:
    """Die Zählung je (absicht, ereignis) -- read-only, robust gegen fehlend/kaputt.
    Das Lese-Ende für ④ und für die Abbau-Entscheidung („stirbt die Zelle?")."""
    zaehlung: dict[tuple[str, str], int] = {}
    try:
        with open(_pfad(), encoding="utf-8") as f:
            for zeile in f:
                try:
                    d = json.loads(zeile)
                    schluessel = (str(d.get("absicht")), str(d.get("ereignis")))
                    zaehlung[schluessel] = zaehlung.get(schluessel, 0) + 1
                except (ValueError, TypeError):
                    continue   # eine kaputte Zeile verdirbt nicht die Zählung
    except OSError:
        pass
    return {f"{a}:{e}": n for (a, e), n in sorted(zaehlung.items())}
