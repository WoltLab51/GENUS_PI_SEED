"""Deuter (edge): frei formulierte deutsche Fragen in eine kleine, gedeckelte Routing-Struktur
uebersetzen -- {"intent": ..., "subject": ..., "object": ...}. Der Deuter WAEHLT nur (ein Intent
aus einer festen Liste, ein bis zwei Woerter aus der Frage), er formuliert NIE eine Antwort
selbst -- die kommt weiterhin aus dem gläsernen Graphen (genus.companion). Der Deuter laeuft
JETZT VOR der deterministischen Kette (nicht mehr nur als letzter Ausweg): freie Formulierung
soll eine normale Unterhaltung tragen, nicht nur ein starres Muster-Set. Die deterministische
Kette bleibt trotzdem die einzige Stelle, die tatsaechlich antwortet -- der Deuter liefert nur
die Struktur, jeder Vorschlag wird graph-verifiziert, bevor er wirkt (genus.companion.
respond_with_deuter). Ein fest zugesagtes Ritual ("merke dir: ...", "was weißt du") bleibt eine
reine Mustererkennung ohne Modell -- eindeutige Befehle brauchen keine Deutung.

Modell-Wahl gemessen, nicht geraten: 7 Modelle/Familien auf dem Pi verglichen (0.5B-3.8B,
Qwen/Llama/Gemma/Phi). Qwen2.5-1.5B-Instruct traf 7/8 bei den geringsten Kosten (Ladezeit,
Latenz, RAM) der zuverlässigen Gruppe -- groessere Modelle trafen nicht besser, nur langsamer.

Anders als der Embedder (fastembed, eigene venv, pro Wort neu geladen im Lerner) lebt dieses
Modell WARM im selben Prozess wie der Telegram-Bot -- ein Neuladen pro Nachricht waere ~2-3s
Extra-Kosten pro Frage. Deshalb: kein eigenes venv, sondern llama-cpp-python direkt in der
bestehenden .venv (der Kern importiert diese Datei nie -- Membran-Reinheit bleibt gewahrt,
das ist eine Frage von WAS genus/ importiert, nicht von WO eine deploy/-Abhaengigkeit installiert
ist), und ein lazy geladenes Modul-Singleton.

Ein echter Live-Fund (2026-07-02): "was ist ein Hund" -- eine eindeutige Frage -- wurde vom
Modell als "statement" gedeutet, nicht als "definition" (vermutlich Wortassoziation mit dem
"statement"-Beispiel im Prompt, das zufaellig denselben Nomen-Typ nutzte). Klare Vorgaben statt
blindem Vertrauen: eine strukturelle, deterministische Gegenprobe (`_looks_like_question`)
verwirft eine "statement"-Deutung IMMER, wenn der Text wie eine Frage aussieht (Fragezeichen
oder Fragewort am Anfang) -- unabhaengig davon, ob das Modell das im Einzelfall richtig trifft.
"""
from __future__ import annotations

import json
import os
import re

MODEL_PATH = os.environ.get(
    "GENUS_DEUTER_MODEL",
    os.path.expanduser("~/.genus/models/qwen2.5-1.5b-instruct-q4_k_m.gguf"),
)
N_THREADS = int(os.environ.get("GENUS_DEUTER_THREADS", "4"))

_SYSTEM = (
    "Du bist ein Deuter fuer einen deutschen Sprach-Assistenten. Gib NUR ein kompaktes JSON "
    "zurueck: {\"intent\": ..., \"subject\": ..., \"object\": ...}. intent ist genau eines von: "
    "definition (was ist X), relation (ist X ein Y / zaehlt X zu Y), comparative (was haben X "
    "und Y gemeinsam), gender (welches Geschlecht/welchen Artikel hat X), followup (bezieht sich "
    "auf die letzte Antwort, z.B. \"warum\", \"und er?\"), statement (eine persoenliche Aussage "
    "oder Tatsachen-Behauptung -- NIEMALS eine Frage: jeder Satz mit Fragezeichen am Ende oder "
    "einem Fragewort am Anfang wie was/wer/wie/wo/warum/wieso/welche/ist/hat/kannst ist KEIN "
    "statement, ganz gleich worum es inhaltlich geht), chitchat (Small Talk, keine Wissensfrage), "
    "unclear (nicht zuordenbar). subject/object sind die Hauptwoerter (Grundform, ohne Artikel, "
    "korrekt geschrieben inkl. Umlaute) oder null, wenn nicht vorhanden. Kein Fliesstext, kein "
    "Kommentar -- nur das JSON, IMMER GENAU diese drei Felder.\n"
    "Beispiele:\n"
    "Was ist eine Katze? -> {\"intent\": \"definition\", \"subject\": \"Katze\", \"object\": null}\n"
    "was ist eigentlich ein Hund? -> {\"intent\": \"definition\", \"subject\": \"Hund\", \"object\": null}\n"
    "ist ein hund ein saeugetier -> {\"intent\": \"relation\", \"subject\": \"Hund\", \"object\": \"Säugetier\"}\n"
    "was haben Hund und Katze gemeinsam -> {\"intent\": \"comparative\", \"subject\": \"Hund\", \"object\": \"Katze\"}\n"
    "welchen Artikel hat Tisch -> {\"intent\": \"gender\", \"subject\": \"Tisch\", \"object\": null}\n"
    "warum -> {\"intent\": \"followup\", \"subject\": null, \"object\": null}\n"
    "ich hab mir gerade einen Wellensittich gekauft -> {\"intent\": \"statement\", "
    "\"subject\": \"Wellensittich\", \"object\": null}\n"
    "mein Geburtstag ist im Mai -> {\"intent\": \"statement\", \"subject\": \"Geburtstag\", \"object\": null}\n"
    "na wie laeufts -> {\"intent\": \"chitchat\", \"subject\": null, \"object\": null}"
)
_VALID_INTENTS = {
    "definition", "relation", "comparative", "gender", "followup", "statement", "chitchat", "unclear",
}
_QUESTION_STARTERS = {
    "was", "wer", "wie", "wo", "warum", "wieso", "weshalb",
    "welche", "welcher", "welches", "welchen", "welchem",
    "ist", "sind", "hat", "haben", "kannst", "kennst", "weißt", "weisst",
}
_FIRST_WORD = re.compile(r"^\s*([^\s?!.,]+)", re.UNICODE)

_model = None   # lazy singleton -- loaded once per process (~2-3s), then warm


def _looks_like_question(text: str) -> bool:
    """A cheap, deterministic structural check -- not a model guess. Used as a hard veto: a
    "statement" verdict is never trusted for text that is structurally a question, regardless
    of what the model says (see the module docstring for the live misfire this guards against)."""
    t = text.strip()
    if t.endswith("?"):
        return True
    m = _FIRST_WORD.match(t)
    return bool(m and m.group(1).lower() in _QUESTION_STARTERS)


def _get_model():
    global _model
    if _model is None:
        from llama_cpp import Llama   # local import: this module stays importable without the dep
        _model = Llama(model_path=MODEL_PATH, n_threads=N_THREADS, n_ctx=1024, verbose=False)
    return _model


def interpret(question: str) -> dict | None:
    """A capped, best-effort routing guess for ``question`` -- ``{"intent", "subject", "object"}``
    or ``None`` on ANY problem (model not installed, inference error, malformed output). Never
    raises: genus.companion.respond_with_deuter treats a ``None`` exactly like "nothing to add".
    Never invents facts -- only picks an intent label and copies up to two words out of the
    question; the caller graph-verifies subject/object and supplies the actual answer content
    itself."""
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
    intent = parsed["intent"]
    if intent == "statement" and _looks_like_question(question):
        intent = "definition"   # a question is never a statement -- retry it as a lookup instead
    subject = parsed.get("subject")
    obj = parsed.get("object")
    return {
        "intent": intent,
        "subject": subject if isinstance(subject, str) else None,
        "object": obj if isinstance(obj, str) else None,
    }


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "Was ist ein Hund?"
    print(f"[DEUTER] \"{q}\" -> {interpret(q)}")
