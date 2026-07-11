"""Die BLIND-PROBE (edge, Waage Scheibe 2): messen, WO die Waage Vertrauen verdient.

54 adversarial geprüfte Proben (deploy/blindproben.json; erzeugt und zweifach geprüft am
2026-07-11) mit objektiv richtiger Antwort. Jede Probe trägt zwei Etiketten:

  klasse  -- das sprachliche THEMA (morphologie, genus-artikel, wsd, stil, einordnung, fakten)
  gestalt -- die ENTSCHEIDUNGS-Gestalt, die eigentliche Vertrauens-Einheit:
             "form"   = gleiches Inhaltswort, nur Funktionswörter/Flexion verschieden
                        (ein Fehlgriff wäre ein Grammatikfehler, nie ein Faktenfehler)
             "stil"   = fakten-identische ganze Sätze, andere Wortstellung
             "inhalt" = verschiedene Inhaltswörter (hier wohnen die Modell-Fehlgriffe,
                        z.B. der selbstbewusst-falsche „mit der Stift", margin 4.9)

Die Kalibrierung lernt die Handlungs-Schwelle PRO GESTALT/KLASSE aus den eigenen Messwerten
(Selbst-Kalibrierung, kein Preset): gibt es Fehlgriffe, liegt die Schwelle über dem größten
Fehlgriff-Margin (Präzision 1.0 auf dem Gemessenen); gibt es keine, ist sie der kleinste
richtige Margin -- unterhalb des Gemessenen gibt es keine Evidenz, also kein Handeln. Das
Ergebnis wandert nach ~/.genus/waage_kalibrierung.json; OHNE diese Datei baut waage.py kein
Organ (messen vor vertrauen, strukturell). Dieses Modul importiert nie genus.* (Membran).
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import waage  # noqa: E402

PROBEN_PFAD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blindproben.json")


def lade_proben() -> list[dict]:
    with open(PROBEN_PFAD, encoding="utf-8") as f:
        return json.load(f)


def messe(proben: list[dict] | None = None, model=None) -> list[dict] | None:
    """Wiegt jede Probe und hält fest, ob die erwartete Antwort gewann und mit welchem Margin.
    ``None`` ohne Modell (nichts gemessen ist nichts gemessen -- keine leere Kalibrierung)."""
    if model is None:
        model = waage._get_model()
        if model is None:
            return None
    ergebnisse = []
    for p in proben if proben is not None else lade_proben():
        r = waage.waehle(p["kontext"], p["kandidaten"], model=model)
        ergebnisse.append({
            "name": p["name"], "klasse": p["klasse"], "gestalt": p["gestalt"],
            "ok": r is not None and r["kandidat"] == p["erwartet"],
            "margin": r["margin"] if r is not None else None,
            "gewaehlt": r["kandidat"] if r is not None else None,
        })
    return ergebnisse


def _schwelle(ergebnisse: list[dict]) -> dict:
    """Die selbst-kalibrierte Handlungs-Schwelle einer Gruppe: über dem größten Fehlgriff-
    Margin (falls Fehlgriffe), sonst der kleinste richtige Margin (nur im gemessenen Bereich
    handeln). ``schwelle=None``, wenn nichts Richtiges gemessen wurde (dann nie handeln)."""
    richtig = sorted(e["margin"] for e in ergebnisse if e["ok"] and e["margin"] is not None)
    falsch = sorted(e["margin"] for e in ergebnisse if not e["ok"] and e["margin"] is not None)
    if not richtig:
        schwelle, regel = None, "nichts-richtig"
    elif falsch:
        # knapp ÜBER dem größten Fehlgriff (margin >= schwelle handelt) -- Präzision 1.0
        # auf dem Gemessenen; behält nur richtige Wägungen oberhalb aller falschen
        schwelle, regel = round(max(falsch) + 1e-4, 4), "ueber-max-fehlgriff"
        if not any(m >= schwelle for m in richtig):
            schwelle, regel = None, "kein-sicherer-bereich"
    else:
        schwelle, regel = round(richtig[0], 4), "min-richtig"
    return {"n": len(ergebnisse), "treffer": sum(e["ok"] for e in ergebnisse),
            "schwelle": schwelle, "regel": regel}


def kalibriere(ergebnisse: list[dict]) -> dict:
    """Schwellen pro GESTALT (die Vertrauens-Einheit der Konsumenten) und pro KLASSE
    (der gläserne Bericht) aus einem Mess-Lauf."""
    gruppen: dict[str, dict[str, list[dict]]] = {"gestalten": {}, "klassen": {}}
    for e in ergebnisse:
        gruppen["gestalten"].setdefault(e["gestalt"], []).append(e)
        gruppen["klassen"].setdefault(e["klasse"], []).append(e)
    return {ebene: {name: _schwelle(zs) for name, zs in sorted(mitglieder.items())}
            for ebene, mitglieder in gruppen.items()}


def schreibe_kalibrierung(kal: dict, pfad: str | None = None) -> str:
    pfad = pfad or waage.KALIBRIERUNG_PFAD
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(kal, f, ensure_ascii=False, indent=1)
    return pfad


def main() -> int:
    t0 = time.time()
    ergebnisse = messe()
    if ergebnisse is None:
        print("[BLINDPROBE] kein Modell gefunden (GENUS_DEUTER_MODEL) -- nichts kalibriert.")
        return 1
    kal = {"stand": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "modell": os.path.basename(waage.MODEL_PATH),
           **kalibriere(ergebnisse)}
    pfad = schreibe_kalibrierung(kal)
    print(f"[BLINDPROBE] {len(ergebnisse)} Proben in {time.time()-t0:.0f}s -> {pfad}")
    for ebene in ("gestalten", "klassen"):
        for name, g in kal[ebene].items():
            print(f"  {ebene[:-2]:8} {name:14} {g['treffer']}/{g['n']}  "
                  f"schwelle={g['schwelle']}  ({g['regel']})")
    fehlgriffe = [e for e in ergebnisse if not e["ok"]]
    if fehlgriffe:
        print("  Fehlgriffe (die Waage las das Modell treu; das Modell lag daneben):")
        for e in fehlgriffe:
            print(f"    [{e['gestalt']}/{e['klasse']}] {e['name']}: "
                  f"gewählt {e['gewaehlt']!r} (margin {e['margin']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
