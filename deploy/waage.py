"""Die WAAGE (edge, Antwort-Seele / LLM-Spektrum ⑥): das Modell WIEGT, es schreibt nicht.

Ronnys zweimal gestellte Idee: „kleinste Stücke reingeben, GENUS baut das Puzzle." Ein
Sprachmodell IST im Kern eine Wahrscheinlichkeitsmaschine — P(nächstes Stück | Kontext). Statt
es erzeugen zu lassen (autoregressiv, teuer, Halluzinationskanal offen), liest die Waage die
Log-Wahrscheinlichkeit vorgegebener Kandidaten AB, ohne je ein Token zu erzeugen: GENUS baut die
Kandidaten selbst (aus dem Graphen, Fakten verbatim), das Modell sagt nur, welches Puzzleteil am
besten sitzt.

Der Nullpunkt des LLM-Spektrums (wiegen → Lücken → sequenziell → fließend): die SICHERSTE Stufe.
Halluzination ist nicht verboten, sondern UNMÖGLICH — es gibt keinen Erzeugungskanal. Anker-Leine,
Verbatim-Insel, Reihenfolge-Prüfung: alle überflüssig, weil nichts zu schützen ist. Rein lesend,
deterministisch (temperature 0, keine Stichprobe) → gleiche Eingabe, gleiches Gewicht → testbar,
replay-freundlich, planfähig.

Wie (der SCHNELLE Weg -- live gemessen, warum er nötig ist): NICHT `create_completion(echo,
logits_all=True)` -- das rechnet die Vokabular-Projektion (~150k) an JEDER Position und braucht
auf dem Pi Minuten. Stattdessen low-level: den Kontext EINMAL durchrechnen, dann pro Kandidaten-
Token nur die LETZTE Position lesen (`model.eval` + `model.scores`, logits_all=False) und den
Log-Softmax des jeweiligen Tokens nehmen. Gemittelt PRO TOKEN (sonst wiegt Längeres scheinbar
leichter -- mehr Token, kleinere Summe). Die Kandidaten-Token werden am längsten GEMEINSAMEN
Token-Präfix von Kontext und Kontext+Kandidat abgetrennt (nicht bei ``len(ctx_tok)``), damit ein
BPE-Merge an der Grenze -- etwa ein Kontext-Leerzeichen, das ins Folgewort gezogen wird -- weder
ein Token verschluckt noch doppelt zählt. Dieses Modul importiert nie genus.* (Membran).
"""
from __future__ import annotations

import math
import os

MODEL_PATH = os.environ.get(
    "GENUS_DEUTER_MODEL",
    os.path.expanduser("~/.genus/models/qwen2.5-1.5b-instruct-q4_k_m.gguf"),
)
N_THREADS = int(os.environ.get("GENUS_DEUTER_THREADS", "4"))

_model = None   # lazy singleton -- geladen mit logits_all (Prompt-Logprobs), einmal pro Prozess


def _get_model():
    global _model
    if _model is None:
        if not os.path.exists(MODEL_PATH):
            return None
        from llama_cpp import Llama   # local import: Modul bleibt ohne die Abhängigkeit importierbar
        # logits_all=False (Default): nur die LETZTE Position bekommt Logits -- genau das braucht
        # der Token-für-Token-Weg, und es ist um Größenordnungen billiger als logits_all.
        _model = Llama(model_path=MODEL_PATH, n_threads=N_THREADS, n_ctx=512, verbose=False)
    return _model


def _lies_logits(model):
    """Die Logits (n_vocab Floats) der ZULETZT ausgewerteten Position, roh aus llama.cpp.
    Bewusst NICHT ``model.scores``: in llama-cpp-python füllt ``eval`` mit logits_all=False die
    scores-Matrix nicht (der Zweig ist auskommentiert) -- man läse eine uniforme Nullzeile
    (Log-Softmax == -log(Vokabular) für alles). ``get_logits()`` liefert dagegen die echte
    Ausgabezeile des letzten Tokens (bei logits_all=False genau eine Zeile). Lokaler numpy-Import,
    damit das Modul ohne die Abhängigkeit importier- und (über einen Fake) testbar bleibt."""
    import numpy as np

    return np.ctypeslib.as_array(model._ctx.get_logits(), shape=(model._n_vocab,))


def _mittel_logprob(model, ctx_tok: list[int], cand_tok: list[int]) -> float | None:
    """Der mittlere Log-Prob PRO TOKEN der Kandidaten-Token, gegeben den schon getokenisierten
    Kontext. Rechnet den Kontext einmal, liest dann Token für Token nur die letzte Position
    (Log-Softmax des jeweiligen Kandidaten-Tokens) und rückt vor. ``None`` bei leerem Kandidaten.
    Reines ``math`` (kein numpy-Zwang) -- der Log-Softmax über das Vokabular ist gegenüber dem
    Modell-Vorwärtsschritt vernachlässigbar, und das Modul bleibt ohne numpy importier-/testbar."""
    if not cand_tok:
        return None
    model.reset()
    model.eval(ctx_tok)
    total = 0.0
    for tok in cand_tok:
        zeile = _lies_logits(model)
        m = max(float(x) for x in zeile)
        log_z = m + math.log(sum(math.exp(float(x) - m) for x in zeile))
        total += float(zeile[tok]) - log_z
        model.eval([tok])
    return total / len(cand_tok)


def wiege(kontext: str, kandidaten: list[str], model=None) -> list[float] | None:
    """Die Gewichte (mittlerer Log-Prob pro Token) der Kandidaten im Kontext -- höher = besser
    passend. ``None`` bei fehlendem Modell / Ausnahme / unabgrenzbarem Kandidaten (der Aufrufer
    hat dann immer einen deterministischen Rückfall). Erfindet nie etwas -- wählt nicht einmal,
    misst nur; die Auswahl trifft :func:`waehle` oder der Aufrufer."""
    if model is None:
        model = _get_model()
        if model is None:
            return None
    try:
        ctx_tok = model.tokenize(kontext.encode("utf-8"), add_bos=True, special=True)
        werte: list[float | None] = []
        for kand in kandidaten:
            voll = model.tokenize((kontext + kand).encode("utf-8"), add_bos=True, special=True)
            # Am längsten GEMEINSAMEN Token-Präfix trennen, nicht bei len(ctx_tok): BPE zieht ein
            # Kontext-Leerzeichen ins Folgewort ("Ġzwei"+" " vs "Ġzwei"+"ĠHund"), die Tokenfolgen
            # weichen also schon VOR dem Kandidaten ab. Der gemeinsame Präfix ist der echte Kontext,
            # der Rest der Kandidat -- so wird kein Token verschluckt und keins doppelt gezählt.
            i = 0
            while i < len(ctx_tok) and i < len(voll) and ctx_tok[i] == voll[i]:
                i += 1
            werte.append(_mittel_logprob(model, voll[:i], voll[i:]))
    except Exception:
        return None
    if not werte or any(w is None for w in werte):
        return None
    return werte


def waehle(kontext: str, kandidaten: list[str], model=None) -> dict | None:
    """Der schwerste Kandidat PLUS der MARGIN zum zweiten -- der Abstand ist die ehrliche
    Konfidenz (kleiner Margin = „unsicher"). ``None``, wenn nicht gewogen werden konnte."""
    werte = wiege(kontext, kandidaten, model)
    if werte is None:
        return None
    rang = sorted(zip(kandidaten, werte), key=lambda p: p[1], reverse=True)
    margin = (rang[0][1] - rang[1][1]) if len(rang) > 1 else float("inf")
    return {
        "kandidat": rang[0][0],
        "margin": round(margin, 4),
        "gewichte": {k: round(w, 4) for k, w in zip(kandidaten, werte)},
    }


# --- Referenz-Proben: der erste Konsument, zugleich der Keim der Blind-Probe (Scheibe 2) --------
# Jede Probe hat eine erwartete Antwort. Hier NUR angezeigt (offen, ohne Urteil); Scheibe 2 macht
# daraus eine kalibrierte, gescorte Blind-Probe, die entscheidet, WO die Waage Vertrauen verdient.
REFERENZ_PROBEN = [
    ("Plural nach 'zwei'",      "Ich habe zwei ",         ["Hund", "Hunde"],            "Hunde"),
    ("Ursache Sing./Plural",    "Die ",                   ["Ursache", "Ursachen"],      "Ursache"),
    ("Artikel/Genus Tisch",     "Ich sehe den ",          ["Tisch", "Tische"],          "Tisch"),
    ("WSD Bergbau/Tier",        "Im Bergwerk zieht der ", ["Hund", "Wagen"],            "Wagen"),
    ("Eröffnung flüssig",       "",                       ["Guten Morgen!", "Morgen gut!"], "Guten Morgen!"),
    ("Genus 'die' Sonne",       "Am Himmel steht die ",   ["Sonne", "Mond"],            "Sonne"),
]


def _demo() -> int:
    """Wiegt die Referenz-Proben und zeigt Kandidat, Margin und Gewichte -- glass-box, read-only.
    Rückgabewert 1, wenn das Modell fehlt (nichts zu wiegen), sonst 0."""
    treffer = 0
    gewogen = 0
    for name, ktx, kand, erwartet in REFERENZ_PROBEN:
        r = waehle(ktx, kand)
        if r is None:
            print(f"  {name:22} -> (kein Modell / nicht wägbar)")
            continue
        gewogen += 1
        ok = r["kandidat"] == erwartet
        treffer += ok
        marke = "✓" if ok else "·"   # · = die Waage las das Modell treu, das Modell lag daneben
        print(f"  {marke} {name:22} -> {r['kandidat']!r:16} margin={r['margin']:.2f}  {r['gewichte']}")
    if gewogen == 0:
        print("  (Modell nicht gefunden -- GENUS_DEUTER_MODEL setzen)")
        return 1
    print(f"\n  Referenz: {treffer}/{gewogen} wie erwartet (die Waage misst treu; der Rest ist "
          f"Modell-Güte, die Scheibe 2 kalibriert).")
    return 0


if __name__ == "__main__":
    import sys
    if len(sys.argv) <= 1 or sys.argv[1] == "--demo":
        print("[WAAGE] Referenz-Proben (das Modell WIEGT, es schreibt nicht):")
        raise SystemExit(_demo())
    ktx = sys.argv[1]
    kand = sys.argv[2:]
    if len(kand) < 2:
        print("Aufruf: waage.py \"<Kontext>\" <Kandidat1> <Kandidat2> [...]   (oder --demo)")
        raise SystemExit(2)
    print(f"[WAAGE] {ktx!r} + {kand}\n        -> {waehle(ktx, kand)}")
