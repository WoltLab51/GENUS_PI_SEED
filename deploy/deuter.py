"""Deuter (edge): eine frei formulierte deutsche Nachricht OFFEN lesen -- klare Fragestellungen,
keine Ankreuzliste. Das Modell beantwortet drei Fragen über die Nachricht ({"absicht": ...,
"subject": ..., "object": ...}); die bekannten Absichten werden ihm ANGEBOTEN (sie kommen aus
GENUS' eigenem Absichts-Raster, einem Teilgraphen im Ledger -- genus.verstehen), aber wenn
keine wirklich passt, darf es die Absicht mit eigenen Worten beschreiben. Der alte
Ankreuzzwang war die Wurzel eines echten Live-Fehlgriffs ("was ist ein Hund" -> "statement"):
ein Modell, das IRGENDWAS wählen muss, wählt bei Unsicherheit falsch. Offen beim Beobachten,
geschlossen beim Handeln: die eigentliche AUSWAHL trifft GENUS (genus.companion bildet die
Lesart aufs Raster ab, handelt nur aus bekannten Zellen, klettert die is_a-Kette für weiche
Landungen, und sammelt raster-fremde Lesarten als Lernmaterial für neue Ausprägungen).

Der Deuter WAEHLT/liest nur -- er formuliert NIE eine Antwort selbst; die kommt weiterhin aus
dem gläsernen Graphen. Jede Nennung wird graph-verifiziert, bevor irgendetwas wirkt.

Modell-Wahl gemessen, nicht geraten: 7 Modelle/4 Familien auf dem Pi verglichen (0.5B-3.8B,
Qwen/Llama/Gemma/Phi). Qwen2.5-1.5B-Instruct traf 7/8 bei den geringsten Kosten der
zuverlässigen Gruppe. Kleine Modelle können kleine Aufgaben -- und der Würfel hält jede
Modell-Aufgabe klein.

Anders als der Embedder (eigene venv, pro Wort neu geladen) lebt dieses Modell WARM im selben
Prozess wie der Telegram-Bot (lazy Modul-Singleton, llama-cpp-python in der bestehenden .venv;
der Kern importiert diese Datei nie -- Membran-Reinheit bleibt gewahrt).

Zwei deterministische Leitplanken, unabhängig vom Modell:
- `_looks_like_question`: eine "tatsache"-Lesart wird NIE geglaubt, wenn der Text strukturell
  eine Frage ist (Fragezeichen oder Fragewort am Anfang) -- der Live-Fund vom 2026-07-02.
- lenient JSON: das {...}-Objekt wird aus der Antwort gezogen, auch wenn das Modell Prosa
  oder einen Markdown-Zaun drumherum setzt (ebenfalls live gesehen).
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

# Mirror of the sown leaf cells (genus.verstehen.RASTER_SEED) -- the OFFER, not a cage. The
# bot passes the live list from the graph; this default keeps the module usable standalone.
DEFAULT_ABSICHTEN = (
    "definition", "beziehung", "vergleich", "eigenschaft", "ursache", "menge", "grammatik",
    "zustand", "offene-fragen", "faehigkeiten", "erinnerungs-abruf",
    "merken", "lernen", "tun",
    "tatsache", "meinung", "korrektur", "empfehlungsfrage",
    "gruss", "dank", "lob", "kritik", "abschied",
    "kuerzer", "ausfuehrlicher", "anders-erklaeren", "wiederholen",
    "warum-herkunft", "vertiefung", "bezug", "unklar",
)

_ERKLAERUNGEN = {
    "definition": "was ist X",
    "beziehung": "ist/zaehlt X (zu) ein(em) Y",
    "vergleich": "was haben X und Y gemeinsam",
    "eigenschaft": "welche Eigenschaft hat X",
    "ursache": "warum ist etwas in der Welt so",
    "menge": "wie viele",
    "grammatik": "Artikel/Geschlecht eines Wortes",
    "zustand": "wie geht es dir / dein Zustand",
    "offene-fragen": "was beschaeftigt dich",
    "faehigkeiten": "was kannst du",
    "erinnerungs-abruf": "was weisst du ueber mich / hast du dir gemerkt",
    "merken": "merk dir etwas",
    "lernen": "lern etwas Neues",
    "tun": "tu etwas",
    "tatsache": "persoenliche Aussage, KEINE Frage (z.B. ich habe zwei Hunde)",
    "meinung": "Meinung/Gefuehl der Person",
    "korrektur": "das stimmt nicht / Korrektur",
    "empfehlungsfrage": "was empfiehlst du / was ist besser",
    "gruss": "Begruessung", "dank": "Dank", "lob": "Lob", "kritik": "Kritik",
    "abschied": "Verabschiedung",
    "kuerzer": "bitte kuerzer", "ausfuehrlicher": "bitte ausfuehrlicher",
    "anders-erklaeren": "bitte anders erklaeren", "wiederholen": "bitte nochmal",
    "warum-herkunft": "warum / woher weisst du das (zur letzten Antwort)",
    "vertiefung": "mehr dazu (zur letzten Antwort)",
    "bezug": "bezieht sich auf die letzte Antwort (z.B. und er?)",
    "unklar": "nicht zuordenbar",
}

_QUESTION_STARTERS = {
    "was", "wer", "wie", "wo", "warum", "wieso", "weshalb",
    "welche", "welcher", "welches", "welchen", "welchem",
    "ist", "sind", "hat", "haben", "kannst", "kennst", "weißt", "weisst",
}
_FIRST_WORD = re.compile(r"^\s*([^\s?!.,]+)", re.UNICODE)
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)

_model = None   # lazy singleton -- loaded once per process (~2-3s), then warm


def _looks_like_question(text: str) -> bool:
    """A cheap, deterministic structural check -- not a model guess. Used as a hard veto: a
    "tatsache" reading is never trusted for text that is structurally a question, regardless
    of what the model says (see the module docstring for the live misfire this guards against)."""
    t = text.strip()
    if t.endswith("?"):
        return True
    m = _FIRST_WORD.match(t)
    return bool(m and m.group(1).lower() in _QUESTION_STARTERS)


def _system_prompt(absichten) -> str:
    angebot = "\n".join(
        f"- {a}: {_ERKLAERUNGEN[a]}" if a in _ERKLAERUNGEN else f"- {a}"
        for a in absichten
    )
    return (
        "Du bist ein Deuter fuer einen deutschen Sprach-Assistenten. Beantworte fuer die "
        "Nachricht drei klare Fragen und gib NUR ein kompaktes JSON zurueck: "
        "{\"absicht\": ..., \"subject\": ..., \"object\": ...}.\n"
        "1. absicht -- was will die Person? Waehle die passende aus dieser Liste:\n"
        + angebot + "\n"
        "Wenn KEINE davon wirklich passt, beschreibe die Absicht frei in 2-4 deutschen "
        "Woertern (kein Zwang zur Liste).\n"
        "2. subject -- das Hauptwort, um das es geht (Grundform, ohne Artikel, korrekt "
        "geschrieben inkl. Umlaute) oder null.\n"
        "3. object -- das zweite Bezugswort, falls vorhanden, sonst null.\n"
        "Kein Fliesstext, kein Kommentar -- nur das JSON mit GENAU diesen drei Feldern.\n"
        "Beispiele:\n"
        "was ist eigentlich ein Hund? -> {\"absicht\": \"definition\", \"subject\": \"Hund\", \"object\": null}\n"
        "zaehlt ein Apfel zu den Pflanzen -> {\"absicht\": \"beziehung\", \"subject\": \"Apfel\", \"object\": \"Pflanze\"}\n"
        "was haben Hund und Katze gemeinsam -> {\"absicht\": \"vergleich\", \"subject\": \"Hund\", \"object\": \"Katze\"}\n"
        "ich hab mir einen Wellensittich gekauft -> {\"absicht\": \"tatsache\", \"subject\": \"Wellensittich\", \"object\": null}\n"
        "warum -> {\"absicht\": \"warum-herkunft\", \"subject\": null, \"object\": null}\n"
        "kannst du mir ein Haustier empfehlen -> {\"absicht\": \"empfehlungsfrage\", \"subject\": \"Haustier\", \"object\": null}\n"
        "kannst du das nochmal sagen -> {\"absicht\": \"wiederholen\", \"subject\": null, \"object\": null}\n"
        "hallo -> {\"absicht\": \"gruss\", \"subject\": null, \"object\": null}\n"
        "na wie laeufts -> {\"absicht\": \"gruss\", \"subject\": null, \"object\": null}\n"
        "Wenn du DIR SELBST unsicher bist, welche Absicht wirklich passt (auch nicht "
        "annaehernd), beschreibe sie lieber frei in eigenen Worten -- rate NIEMALS eine "
        "Absicht aus der Liste nur, weil irgendein Wort oberflaechlich aehnlich klingt."
    )


def _get_model():
    global _model
    if _model is None:
        from llama_cpp import Llama   # local import: this module stays importable without the dep
        _model = Llama(model_path=MODEL_PATH, n_threads=N_THREADS, n_ctx=2048, verbose=False)
    return _model


def get_model():
    """The warm Llama singleton, exposed so ``stimme.py`` can SHARE it (one loaded 1.5B model
    in the bot process, not two -- every GB of RAM counts on the Pi) instead of loading its
    own. ``None`` if the model isn't installed on this machine."""
    if not os.path.exists(MODEL_PATH):
        return None
    return _get_model()


def interpret(question: str, absichten=None) -> dict | None:
    """An OPEN, capped reading of ``question`` -- ``{"absicht", "subject", "object"}`` or
    ``None`` on ANY problem (model not installed, inference error, malformed output). Never
    raises. ``absicht`` is one of the offered kinds OR the model's own free words -- the
    caller (genus.companion) maps it onto the Absichts-Raster, acts only from known cells,
    and collects off-grid readings as learning material. Never invents facts: it only names
    an intent and copies words out of the question; every named term is graph-verified by
    the caller before anything happens."""
    if not os.path.exists(MODEL_PATH):
        return None
    try:
        model = _get_model()
        result = model.create_chat_completion(
            messages=[
                {"role": "system", "content": _system_prompt(absichten or DEFAULT_ABSICHTEN)},
                {"role": "user", "content": question},
            ],
            max_tokens=60,
            temperature=0.0,
        )
        text = result["choices"][0]["message"]["content"].strip()
        match = _JSON_OBJECT.search(text)
        parsed = json.loads(match.group(0) if match else text)
    except Exception:
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("absicht"), str):
        return None
    absicht = parsed["absicht"].strip()
    if not absicht:
        return None
    if absicht == "tatsache" and _looks_like_question(question):
        absicht = "definition"   # a question is never a statement -- retry it as a lookup
    subject = parsed.get("subject")
    obj = parsed.get("object")
    return {
        "absicht": absicht,
        "subject": subject if isinstance(subject, str) else None,
        "object": obj if isinstance(obj, str) else None,
    }


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "Was ist ein Hund?"
    print(f"[DEUTER] \"{q}\" -> {interpret(q)}")
