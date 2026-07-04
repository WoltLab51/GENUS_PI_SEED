"""Deuter (edge): eine Nachricht in ihre SEGMENTE zerlegen und jedes lesen -- keine einzelne
Absicht mehr, sondern eine LISTE. Ronny (2026-07-03): "Nachrichten können auch Fragen, Aussagen,
Floskeln und Aufforderungen in EINER Nachricht enthalten, sogar mehrfach!!!" -- das ist keine
Ad-hoc-Beobachtung, sondern genau das, was ISO 24617-2 (Dialogue Act Markup Language) als
Standard vorschreibt: ein Gesprächs-Turn zerfällt in mehrere FUNKTIONALE SEGMENTE, jedes mit
seinem eigenen Dialogakt. "Hallo! Was ist ein Hund? Danke dir!" sind drei Segmente, nicht eins.

Jedes Segment wird gelesen als {"text": <die Klausel>, "absicht": <ein Blatt aus
genus.verstehen.RASTER_SEED, oder "unklar">, "subject": ..., "object": ...}. Die angebotenen
Blätter sind nach Zwickys Kreuz-Konsistenz-Tabelle gruppiert (Sprechakt × Gegenstand, siehe
genus/verstehen.py) -- das lehrt das Modell die STRUKTUR mit, nicht nur eine flache Liste.
Kein Ankreuzzwang mehr durch eine Freitext-Ausweichklausel (die hatte selbst Nebenwirkungen,
live gefunden: "Danke" wich plötzlich auf "erleben" aus) -- die Kategorien sind jetzt
Zwicky-geprüft und sollen erschöpfend sein; bei echter Unsicherheit ist "unklar" die sichere
Antwort, kein Freitext.

Der Deuter WAEHLT nur (pro Segment ein Blatt aus der Liste, ein bis zwei Wörter aus dem
Segment) -- er formuliert NIE eine Antwort selbst. Jede Nennung wird graph-verifiziert, bevor
irgendetwas wirkt (genus.companion).

Modell-Wahl gemessen, nicht geraten: 7 Modelle/4 Familien auf dem Pi verglichen (0.5B-3.8B,
Qwen/Llama/Gemma/Phi). Qwen2.5-1.5B-Instruct traf 7/8 bei den geringsten Kosten der
zuverlässigen Gruppe.

Anders als der Embedder lebt dieses Modell WARM im selben Prozess wie der Telegram-Bot (lazy
Modul-Singleton, llama-cpp-python in der bestehenden .venv; der Kern importiert diese Datei nie).

Zwei deterministische Leitplanken, unabhängig vom Modell:
- `_looks_like_question`: eine "tatsache"-Lesart wird NIE geglaubt, wenn das SEGMENT strukturell
  eine Frage ist (Fragezeichen oder Fragewort am Anfang) -- geprüft pro Segment, nicht pro
  ganzer Nachricht (sonst würde ein Frage-Segment ein Aussage-Segment in derselben Nachricht
  fälschlich mitreißen).
- lenient JSON: das {...}/[...]-Objekt wird aus der Antwort gezogen, auch wenn das Modell Prosa
  oder einen Markdown-Zaun drumherum setzt.
"""
from __future__ import annotations

import json
import os
import re
import sys

MODEL_PATH = os.environ.get(
    "GENUS_DEUTER_MODEL",
    os.path.expanduser("~/.genus/models/qwen2.5-1.5b-instruct-q4_k_m.gguf"),
)
N_THREADS = int(os.environ.get("GENUS_DEUTER_THREADS", "4"))

# Spiegel der gesäten Blätter (genus.verstehen.RASTER_SEED) -- das ANGEBOT, kein Käfig. Der
# Bot übergibt die lebende Liste aus dem Graphen; dieser Default hält das Modul eigenständig
# nutzbar. Gruppiert nach Zwickys Kreuz-Konsistenz-Zellen (Sprechakt × Gegenstand) -- lehrt
# die Struktur mit, nicht nur eine flache Liste.
DEFAULT_ABSICHTEN = (
    "definition", "beziehung", "vergleich", "grammatik", "eigenschaft", "ursache", "menge",
    "zustand", "offene-fragen", "faehigkeiten", "empfehlungsfrage", "ziele",
    "erinnerungs-abruf",
    "warum-herkunft", "vertiefung", "anschlussfrage",
    "weltfrage",
    "korrektur",
    "tatsache", "merken", "meinung",
    "lernen", "berechnen",
    "kuerzer", "ausfuehrlicher", "anders-erklaeren", "wiederholen",
    "tun",
    "gruss", "dank", "lob", "kritik", "abschied",
    "unklar",
)

# Zelle (Sprechakt-Gegenstand) -> welche der obigen Blätter dort hinein gehören, nur für die
# GRUPPIERTE Prompt-Darstellung (genus.verstehen.ZELLEN/RASTER_SEED bleibt die Quelle der
# Wahrheit für den Dispatch; das hier ist reine Prompt-Lesbarkeit).
_GRUPPEN = (
    ("FRAGEN über einen Begriff/ein Wort", ("definition", "beziehung", "vergleich", "grammatik",
                                             "eigenschaft", "ursache", "menge")),
    ("FRAGEN über GENUS selbst", ("zustand", "offene-fragen", "faehigkeiten", "empfehlungsfrage",
                                   "ziele")),
    ("FRAGEN über dich (den Menschen)", ("erinnerungs-abruf",)),
    ("FRAGEN über das laufende GESPRÄCH (rückbezüglich auf die letzte Antwort)",
     ("warum-herkunft", "vertiefung", "anschlussfrage")),
    ("FRAGEN über die WELT draußen (nicht im eigenen Graphen gespeichert)", ("weltfrage",)),
    ("AUSSAGEN über einen Begriff (Korrektur von Wissen)", ("korrektur",)),
    ("AUSSAGEN über dich", ("tatsache", "merken", "meinung")),
    ("AUFFORDERUNGEN an GENUS (etwas lernen oder rechnen)", ("lernen", "berechnen")),
    ("AUFFORDERUNGEN ans Gespräch (rückbezüglich)", ("kuerzer", "ausfuehrlicher",
                                                       "anders-erklaeren", "wiederholen")),
    ("AUFFORDERUNGEN in der Welt (eine Handlung, Planung, Hilfe)", ("tun",)),
    ("FLOSKELN (kein Gegenstand)", ("gruss", "dank", "lob", "kritik", "abschied")),
)

_ERKLAERUNGEN = {
    "definition": "was ist X",
    "beziehung": "ist/zaehlt X (zu) ein(em) Y",
    "vergleich": "was haben X und Y gemeinsam",
    "grammatik": "Artikel/Geschlecht eines Wortes",
    "eigenschaft": "welche Eigenschaft hat X",
    "ursache": "warum ist etwas in der Welt so",
    "menge": "wie viele",
    "zustand": "wie geht es dir / dein Zustand",
    "offene-fragen": "was beschaeftigt dich",
    "faehigkeiten": "was kannst du",
    "ziele": "was sind deine Ziele / deine Mission / was willst du werden / was fehlt dir",
    "empfehlungsfrage": "was empfiehlst du / was ist besser / deine Meinung dazu",
    "erinnerungs-abruf": "was weisst du ueber mich / hast du dir gemerkt",
    "warum-herkunft": "warum / woher weisst du das (zur letzten Antwort)",
    "vertiefung": "mehr dazu (zur letzten Antwort)",
    "anschlussfrage": "bezieht sich auf die letzte Antwort (z.B. und er?)",
    "weltfrage": "Wetter, Nachrichten, aktuelle Ereignisse -- irgendwas Reales, nicht Gespeichertes",
    "korrektur": "das stimmt nicht / eine Korrektur an einer Tatsache",
    "tatsache": "persoenliche Aussage, KEINE Frage (z.B. ich habe zwei Hunde)",
    "merken": "merk dir etwas",
    "meinung": "Meinung/Gefuehl der Person",
    "lernen": "lern etwas Neues",
    "berechnen": "rechne etwas aus (Ableitung, Integral, Extremstellen ...)",
    "kuerzer": "bitte kuerzer",
    "ausfuehrlicher": "bitte ausfuehrlicher",
    "anders-erklaeren": "bitte anders erklaeren",
    "wiederholen": "bitte nochmal",
    "tun": "eine Handlung/Hilfe/Planung in der echten Welt, kein Wissensabruf",
    "gruss": "Begruessung", "dank": "Dank", "lob": "Lob", "kritik": "Kritik",
    "abschied": "Verabschiedung",
    "unklar": "passt WIRKLICH zu nichts Obigem",
}

_QUESTION_STARTERS = {
    "was", "wer", "wie", "wo", "warum", "wieso", "weshalb",
    "welche", "welcher", "welches", "welchen", "welchem",
    "ist", "sind", "hat", "haben", "kannst", "kennst", "weißt", "weisst",
}
_FIRST_WORD = re.compile(r"^\s*([^\s?!.,]+)", re.UNICODE)
_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)

_model = None   # lazy singleton -- loaded once per process (~2-3s), then warm


def _looks_like_question(text: str) -> bool:
    """Eine strukturelle, deterministische Prüfung -- keine Modell-Vermutung. Harte
    Gegenprobe: eine "tatsache"-Lesart wird nie geglaubt, wenn der TEXT DES SEGMENTS wie eine
    Frage aussieht (Fragezeichen oder Fragewort am Anfang), egal was das Modell sagt."""
    t = text.strip()
    if t.endswith("?"):
        return True
    m = _FIRST_WORD.match(t)
    return bool(m and m.group(1).lower() in _QUESTION_STARTERS)


def _system_prompt(absichten) -> str:
    angebot_set = set(absichten or DEFAULT_ABSICHTEN)
    zeilen = []
    gezeigt: set[str] = set()
    for titel, blaetter in _GRUPPEN:
        vorhanden = [b for b in blaetter if b in angebot_set]
        if not vorhanden:
            continue
        zeilen.append(f"{titel}:")
        zeilen += [f"  - {b}: {_ERKLAERUNGEN[b]}" for b in vorhanden if b in _ERKLAERUNGEN]
        gezeigt.update(vorhanden)
    # Auffangnetz gegen die Membran-Drift (Naht 5, docs/GENUS_ARCHITEKTUR.md §8): ein im
    # Graphen gesätes Blatt, das dieser Spiegel (noch) keiner Gruppe zuordnet, wurde bisher
    # STILL aus dem Prompt verschluckt -- das Modell konnte es nie wählen (live so passiert:
    # "berechnen" war gesät, aber nie im Angebot). Das lebende Angebot ist autoritativ:
    # alles Ungezeigte wird sichtbar nachgereicht statt zu verschwinden.
    rest = sorted(angebot_set - gezeigt - {"unklar"})
    if rest:
        zeilen.append("WEITERE:")
        zeilen += [f"  - {b}: {_ERKLAERUNGEN.get(b, '')}".rstrip(": ") for b in rest]
    zeilen.append("UNKLAR (passt wirklich zu nichts): unklar")
    angebot = "\n".join(zeilen)
    return (
        "Du bist ein Deuter fuer einen deutschen Sprach-Assistenten. Eine Nachricht kann MEHRERE "
        "Sprechhandlungen enthalten (z.B. ein Gruss gefolgt von einer Frage und einem Dank) -- "
        "zerlege sie in ihre einzelnen Segmente. Gib NUR ein kompaktes JSON-ARRAY zurueck, ein "
        "Eintrag pro Segment: [{\"text\": ..., \"absicht\": ..., \"subject\": ..., "
        "\"object\": ...}, ...].\n"
        "Pro Segment:\n"
        "1. text -- die exakte Textklausel dieses Segments aus der Nachricht.\n"
        "2. absicht -- waehle GENAU eine aus dieser Liste (nach Kategorie geordnet):\n"
        + angebot + "\n"
        "3. subject -- das Hauptwort (Grundform, ohne Artikel, korrekt geschrieben inkl. "
        "Umlaute) oder null.\n"
        "4. object -- das zweite Bezugswort, falls vorhanden, sonst null.\n"
        "Kein Fliesstext, kein Kommentar -- nur das JSON-Array.\n"
        "Beispiele:\n"
        "was ist eigentlich ein Hund? -> "
        "[{\"text\": \"was ist eigentlich ein Hund?\", \"absicht\": \"definition\", "
        "\"subject\": \"Hund\", \"object\": null}]\n"
        "Hallo! Was ist ein Hund? Danke dir schonmal! -> "
        "[{\"text\": \"Hallo!\", \"absicht\": \"gruss\", \"subject\": null, \"object\": null}, "
        "{\"text\": \"Was ist ein Hund?\", \"absicht\": \"definition\", \"subject\": \"Hund\", "
        "\"object\": null}, "
        "{\"text\": \"Danke dir schonmal!\", \"absicht\": \"dank\", \"subject\": null, "
        "\"object\": null}]\n"
        "zaehlt ein Apfel zu den Pflanzen -> "
        "[{\"text\": \"zaehlt ein Apfel zu den Pflanzen\", \"absicht\": \"beziehung\", "
        "\"subject\": \"Apfel\", \"object\": \"Pflanze\"}]\n"
        "Wie wird das Wetter morgen? -> "
        "[{\"text\": \"Wie wird das Wetter morgen?\", \"absicht\": \"weltfrage\", "
        "\"subject\": null, \"object\": null}]\n"
        "Ich moechte einen Familienausflug planen. Kannst du mir helfen? -> "
        "[{\"text\": \"Ich moechte einen Familienausflug planen. Kannst du mir helfen?\", "
        "\"absicht\": \"tun\", \"subject\": \"Familienausflug\", \"object\": null}]\n"
        "kannst du das nochmal sagen -> "
        "[{\"text\": \"kannst du das nochmal sagen\", \"absicht\": \"wiederholen\", "
        "\"subject\": null, \"object\": null}]\n"
        "danke dir -> [{\"text\": \"danke dir\", \"absicht\": \"dank\", \"subject\": null, "
        "\"object\": null}]\n"
        "Fuer eindeutige, ALLTAEGLICHE Hoeflichkeitsfloskeln (Gruss, Dank, Abschied) waehle "
        "immer die passende Kategorie aus der Liste -- rate NIEMALS eine andere Absicht nur, "
        "weil ein Wort oberflaechlich aehnlich klingt. Wenn WIRKLICH nichts passt: unklar."
    )


def _get_model():
    global _model
    if _model is None:
        from llama_cpp import Llama   # local import: this module stays importable without the dep
        _model = Llama(model_path=MODEL_PATH, n_threads=N_THREADS, n_ctx=2048, verbose=False)
    return _model


_grammatik_cache: dict[str, object] = {}   # GBNF-Text -> LlamaGrammar (einmal kompiliert, warm)


def _gbnf(text: str):
    """Kompiliert einen GBNF-Text zur llama.cpp-Grammatik, einmal pro Text (Cache).
    Scheitert die Kompilierung (llama_cpp fehlt, Grammatik fehlerhaft), wird LAUT gewarnt
    und ``None`` zurückgegeben -- der Deuter läuft dann unbeschränkt weiter (ehrliche
    Degradation: der Bot bleibt antwortfähig, der Verlust der Garantie steht im Log,
    er passiert nie still)."""
    if text in _grammatik_cache:
        return _grammatik_cache[text]
    try:
        from llama_cpp import LlamaGrammar
        grammatik = LlamaGrammar.from_string(text, verbose=False)
    except Exception as exc:
        print(f"[DEUTER] Grammatik unbrauchbar ({exc}) — deute UNBESCHRÄNKT weiter",
              file=sys.stderr)
        grammatik = None
    _grammatik_cache[text] = grammatik
    return grammatik


def _segment(eintrag: dict, ganze_nachricht: str) -> dict | None:
    """Ein rohes geparstes Segment in ein sauberes ``{"text","absicht","subject","object"}`` --
    ``None`` wenn kein gueltiges Blatt genannt wurde. ``text`` (die eigene Klausel des Segments)
    bleibt im Ergebnis -- ein Handler, der die Laenge/den Wortlaut beurteilen muss (Sozialgesten,
    tatsache), MUSS das SEGMENT beurteilen, nicht die ganze Nachricht: sonst reisst eine lange
    Nachricht ("Hallo! Was ist ein Hund? Danke!") ihr eigenes kurzes "Danke!"-Segment mit in
    die Wortzahl-Bremse, live gefunden."""
    if not isinstance(eintrag, dict) or not isinstance(eintrag.get("absicht"), str):
        return None
    absicht = eintrag["absicht"].strip()
    if not absicht:
        return None
    segment_text = eintrag.get("text") if isinstance(eintrag.get("text"), str) else ganze_nachricht
    if absicht == "tatsache" and _looks_like_question(segment_text):
        absicht = "definition"   # eine Frage ist nie eine Aussage -- pro Segment geprueft
    subject = eintrag.get("subject")
    obj = eintrag.get("object")
    return {
        "text": segment_text,
        "absicht": absicht,
        "subject": subject if isinstance(subject, str) else None,
        "object": obj if isinstance(obj, str) else None,
    }


def interpret(nachricht: str, absichten=None, grammatik: str | None = None) -> list[dict] | None:
    """Liest ``nachricht`` als eine LISTE von Sprechhandlungs-Segmenten -- ``[{"absicht",
    "subject", "object"}, ...]``. Zwei verschiedene "nichts"-Fälle, bewusst unterschieden:
    eine LEERE Liste ``[]`` heisst "das Modell lief und sagt ehrlich: keine Segmente passen"
    (das Modell gibt das selbst so zurueck, live gesehen); ``None`` heisst "das Modell konnte
    gar nicht erst gefragt werden oder ist gescheitert" (Modell fehlt, Ausnahme, kaputtes JSON).
    Der Aufrufer (companion.respond_with_deuter) behandelt beides unterschiedlich: eine leere
    Liste ist ein ehrliches Nichtverstehen (kein Rueckfall auf den Wort-Lookup mehr noetig),
    ``None`` bleibt ein legitimer Grund, es trotzdem mit dem Wort-Lookup zu versuchen. Nie eine
    Ausnahme. Erfindet nie Fakten -- waehlt pro Segment nur ein Blatt und kopiert Woerter aus
    dem Text; der Aufrufer graph-verifiziert subject/object und liefert den eigentlichen
    Antwort-Inhalt selbst.

    ``grammatik`` (optional): ein GBNF-Text -- DIE GRENZE (genus.verstehen.gbnf_grammatik,
    als Daten über die Membran gereicht; dieses Modul importiert weiterhin nie genus.*).
    Mit Grenze kann das Modell pro Token nur innerhalb des JSON-Segment-Vertrags und der
    bekannten Blätter fortsetzen -- eine erfundene Kategorie ist strukturell unmöglich.
    Die Beschränkung ist pro Token, der Aufruf bleibt EIN Generierungslauf."""
    if not os.path.exists(MODEL_PATH):
        return None
    try:
        model = _get_model()
        zusatz: dict = {}
        if grammatik:
            grammar = _gbnf(grammatik)
            if grammar is not None:
                zusatz["grammar"] = grammar
        result = model.create_chat_completion(
            messages=[
                {"role": "system", "content": _system_prompt(absichten)},
                {"role": "user", "content": nachricht},
            ],
            max_tokens=300,
            temperature=0.0,
            **zusatz,
        )
        text = result["choices"][0]["message"]["content"].strip()
        match = _JSON_ARRAY.search(text)
        if match:
            parsed = json.loads(match.group(0))
        else:
            # das Modell gab evtl. nur EIN Objekt statt eines Arrays -- lenient akzeptieren
            obj_match = _JSON_OBJECT.search(text)
            parsed = [json.loads(obj_match.group(0))] if obj_match else json.loads(text)
    except Exception:
        return None
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return None
    return [s for s in (_segment(e, nachricht) for e in parsed) if s is not None]


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "Was ist ein Hund?"
    print(f"[DEUTER] \"{q}\" -> {interpret(q)}")
