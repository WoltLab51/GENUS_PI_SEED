"""Die Gebärde: eine reine Emoji-Nachricht deterministisch lesen — die Antwort auf
Proposal #14 (die vom Fehlgriff-Konsumenten selbst erspürte „Emoji-Lücke": Nachrichten,
die GENUS gar nicht deuten konnte, 3-mal in echten Gesprächen).

Der Befund vom Testabend war klar: reine Emoji-Nachrichten („👍", „🙏") gingen an das
Deuter-Modell, und ein 1.5B-Modell rät bei nacktem Emoji unzuverlässig — es landete auf
„unklar". GENUS' eigener Plan im Proposal lautete „schärfere Anker-Beispiele oder ein
stärkeres Modell". Das hier ist BESSER als beides: ein Emoji ist die *deterministischste*
Eingabe überhaupt — ein 👍 heißt eindeutig Zustimmung, kein Modell muss das raten.

Also bekommen Gebärden dieselbe Behandlung wie die exakten Text-Kommandos: eine gläserne,
modellfreie SCHNELLSPUR vor dem Deuter (genus.companion.respond_with_deuter). Kein
Halluzinationsrisiko, keine Latenz, ehrliche Herkunft (Quelle „gebaerde", nie „model:deuter").
Eine Gebärde bildet auf ein bestehendes Floskel-Blatt des Rasters ab (lob/dank/gruss/kritik,
genus.verstehen.RASTER_SEED) — es entsteht KEINE neue Handler-Fläche, nur ein neuer, sicherer
Eingang zu den warmen Zellen, die es längst gibt.

Leitprinzip wie beim Deuter: NUR hoch-eindeutige Gesten. Zweideutiges (🤔 nachdenklich,
😴 müde) steht bewusst NICHT in der Liste — es fällt ehrlich durch (Modell, dann „nicht
verstanden"), statt eine plausible falsche Kategorie zu erzwingen (kein Ankreuzzwang).
"""
from __future__ import annotations

# Emoji -> Floskel-Blatt (genus.verstehen.RASTER_SEED). Nur Gesten, deren soziale Bedeutung
# im Chat eindeutig ist. Varianten-Selektoren (U+FE0F), Hautton-Modifikatoren und ZWJ werden
# vor dem Nachschlagen abgestreift, damit „👍🏽" und „👍️" dieselbe Geste sind wie „👍".
_GESTE: dict[str, str] = {
    # Zustimmung / Lob / positive Regung
    "👍": "lob", "👏": "lob", "🙌": "lob", "🙆": "lob", "👌": "lob",
    "🔥": "lob", "💪": "lob", "💯": "lob", "✨": "lob", "⭐": "lob", "🌟": "lob",
    "🎉": "lob", "🥳": "lob", "😊": "lob", "🙂": "lob", "😀": "lob", "😃": "lob",
    "😄": "lob", "😁": "lob", "😍": "lob", "🥰": "lob", "😘": "lob", "🤗": "lob",
    "❤": "lob", "🧡": "lob", "💛": "lob", "💚": "lob", "💙": "lob", "💜": "lob",
    "🤍": "lob", "🖤": "lob", "🤎": "lob", "💗": "lob", "💖": "lob", "💕": "lob",
    "💞": "lob", "💓": "lob", "💘": "lob", "💝": "lob",
    # Dank
    "🙏": "dank",
    # Begrüßung
    "👋": "gruss", "🤝": "gruss",
    # Kritik / Ablehnung
    "👎": "kritik",
}

# Zeichen, die eine Geste nicht verändern: Varianten-Selektor (U+FE0F), ZWJ (U+200D),
# Hautton-Modifikatoren (U+1F3FB..U+1F3FF). Als Codepoints, nicht als unsichtbare Literale.
_MODIFIKATOREN = {chr(0xFE0F), chr(0x200D)} | {chr(c) for c in range(0x1F3FB, 0x1F3FF + 1)}


def _gesten(nachricht: str) -> list[str]:
    """Die erkannten Floskel-Blätter in Reihenfolge des ersten Auftretens (dedupliziert):
    „👍👍👍" ist EINE lob-Geste, „🙏❤" sind zwei (dank, dann lob)."""
    reihenfolge: list[str] = []
    for ch in nachricht:
        blatt = _GESTE.get(ch)
        if blatt is not None and blatt not in reihenfolge:
            reihenfolge.append(blatt)
    return reihenfolge


def lies(nachricht: str) -> list[dict] | None:
    """Liest eine REINE Gebärden-Nachricht als Liste synthetischer Deuter-Segmente (dieselbe
    Form wie deploy.deuter.interpret liefert), oder ``None``, wenn es keine reine Gebärde ist.

    ``None`` (fällt an den Deuter/Wort-Pfad durch) in zwei Fällen:
    - die Nachricht enthält Buchstaben oder Ziffern (gemischter Text wie „danke 🙏") — das
      kann das Modell gut, das Emoji ist dort ohnehin redundant;
    - keine der bekannten Gesten kommt vor (nur unbekanntes Emoji wie „😴") — ehrlich
      durchfallen statt raten.

    Sonst ein Segment je erkannter Geste. ``text`` ist die ganze Nachricht (die Floskel-Zellen
    beurteilen die Wortzahl, und eine Emoji-Nachricht hat null Wörter — die Kurz-Bremse greift
    also nie fälschlich)."""
    if nachricht is None:
        return None
    kern = "".join(ch for ch in nachricht if ch not in _MODIFIKATOREN and not ch.isspace())
    if not kern:
        return None
    if any(ch.isalnum() for ch in kern):   # Buchstaben/Ziffern -> gemischter Text, Sache des Modells
        return None
    blaetter = _gesten(nachricht)
    if not blaetter:
        return None
    return [{"text": nachricht, "absicht": blatt, "subject": None, "object": None}
            for blatt in blaetter]
