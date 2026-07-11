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

Wie: `create_completion(echo=True, logprobs=1)` gibt die Token-Log-Wahrscheinlichkeiten des
GESAMTEN Prompts zurück; über den Zeichen-Offset trennen wir die Kandidaten-Token vom Kontext
und mitteln PRO TOKEN (sonst wiegt Längeres scheinbar leichter — mehr Token, kleinere Summe).
Der Kontext sollte an einer natürlichen Grenze enden (Leerzeichen/Satzzeichen), damit kein
Token Kontext und Kandidat überspannt. Dieses Modul importiert nie genus.* (Membran).
"""
from __future__ import annotations

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
        # logits_all=True: nur so liefert echo die Logprobs JEDES Prompt-Tokens (das Wiege-Signal).
        # n_ctx klein -- Wiege-Kontexte sind kurz (ein Satz), das spart Speicher/Zeit.
        _model = Llama(model_path=MODEL_PATH, n_threads=N_THREADS, n_ctx=512,
                       logits_all=True, verbose=False)
    return _model


def _mittel_logprob(model, kontext: str, kandidat: str) -> float | None:
    """Der mittlere Log-Prob PRO TOKEN des Kandidaten im Kontext -- die eigentliche Wägung.
    ``None``, wenn kein Kandidaten-Token abgegrenzt werden konnte (leerer Kandidat o.ä.)."""
    r = model.create_completion(prompt=kontext + kandidat, max_tokens=0,
                                echo=True, logprobs=1, temperature=0.0)
    lp = r["choices"][0]["logprobs"]
    grenze = len(kontext)
    werte = [t for t, o in zip(lp["token_logprobs"], lp["text_offset"])
             if t is not None and o >= grenze]
    return sum(werte) / len(werte) if werte else None


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
        werte = [_mittel_logprob(model, kontext, k) for k in kandidaten]
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


if __name__ == "__main__":
    import sys
    ktx = sys.argv[1] if len(sys.argv) > 1 else "Ich habe zwei "
    kand = sys.argv[2:] or ["Hund", "Hunde"]
    print(f"[WAAGE] {ktx!r} + {kand} -> {waehle(ktx, kand)}")
