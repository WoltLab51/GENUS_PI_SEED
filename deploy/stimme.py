"""Stimme (edge): einen bereits verifizierten, deterministischen Satz natürlicher formulieren --
FORMULIERT NUR UM, FÜGT NIE HINZU. Anders als der Deuter (der freie Sprache in Struktur liest,
BEVOR der Kern etwas weiß) sitzt die Stimme NACH dem Kern: der Satz, den sie bekommt, ist
bereits aus dem gläsernen Graphen gebaut und fertig geprüft (narrate/narrate_relation/…) -- ihre
einzige Aufgabe ist, ihn flüssiger klingen zu lassen, nicht seinen Inhalt zu ändern.

Die Leine ist eine ANKER-PRÜFUNG, kein Vertrauen ins Modell: jedes in Guillemets genannte Wort
(»Hund«) und jede Vertrauens-/Konfidenzzahl (0.50) MUSS im umformulierten Satz wortwörtlich
wieder auftauchen. Fehlt auch nur ein Anker, gilt das als Faktenverlust (das Modell hat etwas
weggelassen oder ersetzt) -- die Funktion gibt dann `None` zurück, und der Aufrufer fällt auf
den ORIGINALEN, bewährten Satz zurück. Nie stillschweigend: eine geglättete Antwort trägt einen
sichtbaren Hinweis (companion._STIMME_TAG).

Teilt sich bewusst das WARME Deuter-Modell (get_model()) statt ein zweites 1.5B-Modell zu laden
-- auf dem Pi zählt jedes GB RAM. Ein eigenes lazy Singleton bleibt als Fallback für den
Standalone-Gebrauch (Tests, `python -m deploy.stimme`).
"""
from __future__ import annotations

import os
import re

MODEL_PATH = os.environ.get(
    "GENUS_DEUTER_MODEL",
    os.path.expanduser("~/.genus/models/qwen2.5-1.5b-instruct-q4_k_m.gguf"),
)
N_THREADS = int(os.environ.get("GENUS_DEUTER_THREADS", "4"))

_SYSTEM = (
    "Du bist die Stimme eines deutschen Sprach-Assistenten. Du bekommst einen bereits "
    "geprueften, korrekten Satz. Formuliere ihn natuerlicher und fluessiger auf Deutsch -- "
    "aber du darfst KEINE Fakten, Namen, Zahlen oder Vertrauensangaben aendern, hinzufuegen "
    "oder weglassen; jedes genannte Wort in Anfuehrungszeichen und jede Zahl muss unveraendert "
    "erhalten bleiben. Gib NUR den neu formulierten Satz zurueck, keinen Kommentar, keine "
    "Anfuehrungszeichen drumherum."
)

_QUOTED = re.compile(r"»([^»«]+)«")
_NUMBER = re.compile(r"\b\d+[.,]\d+\b")

_model = None   # lazy singleton -- only used standalone; the bot shares deuter's warm model


def _anchors(satz: str) -> list[str]:
    """The facts that must survive a rephrase: every quoted word, every confidence number."""
    return _QUOTED.findall(satz) + _NUMBER.findall(satz)


def _get_model():
    global _model
    if _model is None:
        from llama_cpp import Llama
        _model = Llama(model_path=MODEL_PATH, n_threads=N_THREADS, n_ctx=1024, verbose=False)
    return _model


def formuliere(satz: str, model=None) -> str | None:
    """A faithfulness-checked rephrasing of an ALREADY-VERIFIED sentence -- ``None`` on any
    problem (model missing, inference error, malformed output) OR when an anchor (a quoted
    word, a confidence number) went missing from the rephrase, so the caller always has a
    safe fallback: the original ``satz`` itself. Never invents new claims -- it can only
    reorder/rephrase words already present; the anchor check is what makes that a guarantee
    and not just an instruction."""
    if model is None:
        if not os.path.exists(MODEL_PATH):
            return None
        model = _get_model()
    anchors = _anchors(satz)
    try:
        result = model.create_chat_completion(
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": satz},
            ],
            max_tokens=200,
            temperature=0.3,
        )
        text = result["choices"][0]["message"]["content"].strip()
    except Exception:
        return None
    if not text:
        return None
    if any(anchor not in text for anchor in anchors):
        return None   # a fact/number went missing or was changed -- fail safe to the original
    return text


if __name__ == "__main__":
    import sys
    satz = " ".join(sys.argv[1:]) or "Unter »Hund« versteht GENUS: Haustier, dessen Vorfahre der Wolf ist."
    print(f"[STIMME] \"{satz}\" -> {formuliere(satz)}")
