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

Eigenes warmes Modell, bewusst NICHT mit dem Deuter geteilt -- live gemessen (2026-07-03): ein
geteiltes Modell verwarf bei jedem Stimme-Aufruf den Prompt-Cache des Deuter (ein komplett
anderer System-Prompt), sodass der NÄCHSTE Deuter-Aufruf seinen ganzen ~1300-Token-Prompt neu
verarbeiten musste -- 26s statt 3s, ein Zufalls-Faktor abhängig von der Aufrufreihenfolge.
Kostet dauerhaft ein zweites 1.5B-Modell im RAM (~1-1.5 GB, auf dem Pi reichlich frei), macht
die Latenz dafür durchgehend vorhersagbar.
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
_SATZ_TRENNER = re.compile(r"[.!?]+\s*")
_TOKEN = re.compile(r"[\wäöüÄÖÜß»«]+")
_SUBSTANTIV = re.compile(r"[A-ZÄÖÜ][a-zäöüß]{3,}")

_model = None   # lazy singleton -- only used standalone; the bot shares deuter's warm model


def _anchors(satz: str) -> list[str]:
    """The facts that must survive a rephrase: every quoted word, every confidence number."""
    return _QUOTED.findall(satz) + _NUMBER.findall(satz)


def _reihenfolge_haelt(text: str, quoted: list[str]) -> bool:
    """Die zitierten Begriffe müssen im umformulierten Satz in DERSELBEN Reihenfolge auftauchen
    wie im Original -- die Leine gegen Richtungs-Umkehr (Antwort-Seele Scheibe 2). Die reine
    Vorkommens-Prüfung (:func:`_anchors`) sah nur, DASS »Hund« und »Haustier« beide da sind,
    nicht in welcher Reihenfolge -- genau diese Lücke (live-Fund 2026-07-06: „Staubsauger
    verursacht Sog" wurde zu „Sog verursacht Staubsauger") entzog gerichtete Relationen bisher
    der Stimme ganz. Mit dieser Prüfung kann die Stimme sie umformulieren, und eine Umkehr wird
    erkannt und verworfen (der Aufrufer fällt auf den deterministischen Voice-1-Satz zurück)."""
    pos = -1
    for q in quoted:
        i = text.find(q, pos + 1)
        if i < 0:
            return False   # ein Begriff fehlt oder steht vor seinem Vorgänger -> Reihenfolge gebrochen
        pos = i
    return True


def _inhaltsworte(satz: str) -> list[str]:
    """Die zweite, härtere Leine — live gefunden (2026-07-04, beim ersten Anweisungs-Test):
    unter einer Stil-Anweisung machte das 1.5B aus „Haustier" ein „Hausvögel", und die
    Anker-Prüfung ließ es durch (sie sah nur zitierte Wörter + Zahlen, der Gloss-Text ist
    frei). Deutsche GROSSSCHREIBUNG = Substantive = die tragenden Inhaltswörter: jedes
    großgeschriebene Wort (≥4 Zeichen) muss die Umformulierung als Teilwort überleben.
    Satzanfänge sind ausgenommen (großgeschrieben ohne Substantiv zu sein); GENUS selbst
    fällt als Versalien-Wort automatisch heraus (der Sprecher darf wegformuliert werden)."""
    worte: list[str] = []
    for teil in _SATZ_TRENNER.split(satz):
        for i, roh in enumerate(_TOKEN.findall(teil)):
            tok = roh.strip("»«")
            if i > 0 and _SUBSTANTIV.fullmatch(tok):
                worte.append(tok)
    return worte


def _get_model():
    global _model
    if _model is None:
        from llama_cpp import Llama
        _model = Llama(model_path=MODEL_PATH, n_threads=N_THREADS, n_ctx=1024, verbose=False)
    return _model


def formuliere(satz: str, model=None, anweisung: str | None = None,
               kern: str | None = None) -> str | None:
    """A faithfulness-checked rephrasing of an ALREADY-VERIFIED sentence -- ``None`` on any
    problem (model missing, inference error, malformed output) OR when an anchor (a quoted
    word, a confidence number) went missing from the rephrase, so the caller always has a
    safe fallback: the original ``satz`` itself. Never invents new claims -- it can only
    reorder/rephrase words already present; the anchor check is what makes that a guarantee
    and not just an instruction.

    ``anweisung`` (der Antwort-Würfel, ``genus.antwort.anweisung``): eine deterministisch
    gewählte STIL-Vorgabe („Ton: freundlich und warm."), als reine Daten über die Membran
    gereicht -- dieselbe Rolle wie die GBNF-Grammatik beim Deuter. Sie ändert nur, WIE
    formuliert wird; die Anker-Prüfung danach ist von ihr völlig unabhängig.

    ``kern`` (Antwort-Seele Scheibe 2, „Rahmen frei, Kern fest"): eine VERBATIM-INSEL -- der
    gerichtete Fakt-Satz (»Hund« zählt zu »Haustier«), der WORTWÖRTLICH und unverändert im
    Ergebnis stehen muss. Nur so ist eine Richtungs-Umkehr strukturell unmöglich: die Stimme
    darf frei DRUMHERUM formulieren (Anrede, Wärme, Anschluss), aber den Kern nicht anfassen.
    Fehlt der Kern-Satz als exakte Teilzeichenkette, gilt der Versuch als gescheitert (``None``,
    Rückfall auf den deterministischen Voice-1-Satz). ``None`` = keine Insel (freie Umformung,
    nur die üblichen Anker), für die ungerichteten Zellen (Definition, Vergleich)."""
    if model is None:
        if not os.path.exists(MODEL_PATH):
            return None
        model = _get_model()
    anchors = _anchors(satz)
    system = _SYSTEM if not anweisung else (
        _SYSTEM + " Halte dich zusaetzlich an diese Stil-Vorgabe, ohne je Fakten zu "
        "aendern oder zu ergaenzen: " + anweisung
    )
    if kern:
        system += (" Dieser Kern-Satz MUSS WORTWOERTLICH und voellig unveraendert erhalten "
                   "bleiben (formuliere nur davor und dahinter, nie mittendrin): " + kern)
    try:
        result = model.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
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
    if any(wort not in text for wort in _inhaltsworte(satz)):
        return None   # ein tragendes Substantiv wurde wegformuliert/korrumpiert (Hausvögel-Fund)
    if not _reihenfolge_haelt(text, _QUOTED.findall(satz)):
        return None   # die zitierten Begriffe stehen in anderer Reihenfolge -> Richtung evtl. gekippt
    if kern and kern not in text:
        return None   # die Verbatim-Insel (gerichteter Kern-Satz) wurde angetastet -> verworfen
    if text == satz:
        return None   # wortidentisch ist keine Glättung -- ehrlich kein Gewinn, kein Tag
    return text


if __name__ == "__main__":
    import sys
    satz = " ".join(sys.argv[1:]) or "Unter »Hund« versteht GENUS: Haustier, dessen Vorfahre der Wolf ist."
    print(f"[STIMME] \"{satz}\" -> {formuliere(satz)}")
