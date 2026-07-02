"""Deuter (edge): frei formulierte deutsche Fragen in eine kleine, gedeckelte Routing-Struktur
uebersetzen -- {"intent": ..., "subject": ...}. Der Deuter WAEHLT nur (ein Intent aus einer
festen Liste, ein Wort aus der Frage), er formuliert NIE eine Antwort selbst -- die kommt
weiterhin aus dem gläsernen Graphen (genus.companion). Erst wenn die deterministische Kette
(Zustand -> Nachfrage -> Beziehung -> Vergleich -> Genus -> Wort) nichts findet, kommt der
Deuter ueberhaupt zum Zug -- letzte, gedeckelte Stufe, keine erste (genus.companion.
respond_with_deuter graph-verifiziert jeden Vorschlag, bevor er wirkt).

Modell-Wahl gemessen, nicht geraten: 7 Modelle/Familien auf dem Pi verglichen (0.5B-3.8B,
Qwen/Llama/Gemma/Phi). Qwen2.5-1.5B-Instruct traf 7/8 bei den geringsten Kosten (Ladezeit,
Latenz, RAM) der zuverlässigen Gruppe -- groessere Modelle trafen nicht besser, nur langsamer.

Anders als der Embedder (fastembed, eigene venv, pro Wort neu geladen im Lerner) lebt dieses
Modell WARM im selben Prozess wie der Telegram-Bot -- ein Neuladen pro Nachricht waere ~2-3s
Extra-Kosten pro Frage. Deshalb: kein eigenes venv, sondern llama-cpp-python direkt in der
bestehenden .venv (der Kern importiert diese Datei nie -- Membran-Reinheit bleibt gewahrt,
das ist eine Frage von WAS genus/ importiert, nicht von WO eine deploy/-Abhaengigkeit installiert
ist), und ein lazy geladenes Modul-Singleton.
"""
from __future__ import annotations

import json
import os

MODEL_PATH = os.environ.get(
    "GENUS_DEUTER_MODEL",
    os.path.expanduser("~/.genus/models/qwen2.5-1.5b-instruct-q4_k_m.gguf"),
)
N_THREADS = int(os.environ.get("GENUS_DEUTER_THREADS", "4"))

_SYSTEM = (
    "Du bist ein Deuter fuer einen deutschen Sprach-Assistenten. Gib NUR ein kompaktes JSON "
    "zurueck: {\"intent\": ..., \"subject\": ...}. intent ist genau eines von: "
    "definition (was ist X), relation (ist X ein Y), followup (bezieht sich auf die letzte "
    "Antwort, z.B. \"warum\", \"und er?\"), chitchat (Small Talk, keine Wissensfrage), "
    "unclear (nicht zuordenbar). subject ist das Hauptwort der Frage (Grundform, ohne Artikel) "
    "oder null. Kein Fliesstext, kein Kommentar -- nur das JSON, IMMER GENAU diese zwei Felder.\n"
    "Beispiele:\n"
    "Was ist eine Katze? -> {\"intent\": \"definition\", \"subject\": \"Katze\"}\n"
    "ist ein hund ein saeugetier -> {\"intent\": \"relation\", \"subject\": \"Hund\"}\n"
    "warum -> {\"intent\": \"followup\", \"subject\": null}\n"
    "na wie laeufts -> {\"intent\": \"chitchat\", \"subject\": null}"
)
_VALID_INTENTS = {"definition", "relation", "followup", "chitchat", "unclear"}

_model = None   # lazy singleton -- loaded once per process (~2-3s), then warm


def _get_model():
    global _model
    if _model is None:
        from llama_cpp import Llama   # local import: this module stays importable without the dep
        _model = Llama(model_path=MODEL_PATH, n_threads=N_THREADS, n_ctx=512, verbose=False)
    return _model


def interpret(question: str) -> dict | None:
    """A capped, best-effort routing guess for ``question`` -- ``{"intent", "subject"}`` or
    ``None`` on ANY problem (model not installed, inference error, malformed output). Never
    raises: this is a last-resort convenience for genus.companion.respond_with_deuter, not a
    dependency the rest of the system leans on. Never invents facts -- only picks an intent
    label and copies a word out of the question; the caller graph-verifies the subject and
    supplies the actual answer content itself."""
    if not os.path.exists(MODEL_PATH):
        return None
    try:
        model = _get_model()
        result = model.create_chat_completion(
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": question},
            ],
            max_tokens=60,
            temperature=0.0,
        )
        text = result["choices"][0]["message"]["content"].strip()
        parsed = json.loads(text)
    except Exception:
        return None
    if not isinstance(parsed, dict) or parsed.get("intent") not in _VALID_INTENTS:
        return None
    subject = parsed.get("subject")
    return {"intent": parsed["intent"], "subject": subject if isinstance(subject, str) else None}


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "Was ist ein Hund?"
    print(f"[DEUTER] \"{q}\" -> {interpret(q)}")
