"""Der ANTWORT-WÜRFEL (Ronny, 2026-07-04: „bau den antwort-würfel mit der stimme-anweisung") --
die Zwicky-Symmetrie an der Membran: der Verstehens-Würfel zerlegt, was REINKOMMT, dieser
Würfel setzt zusammen, was RAUSGEHT.

Zwickys vier Schritte, auf die Antwort angewandt:
(1) unabhängige Parameter: der KERN (Fakten + Ehrlichkeits-Hinweise, unwählbar -- die
    Leitplanke in Kasten-Form), der WORTLAUT (wörtlich | Stimme-Umformung), die Achsen der
    Persönlichkeit (Wärme, Umfang, Humor, Neugier) und das BEIWERK (Notiz-Einwebung,
    Rückfrage, nichts);
(2) die Werte je Achse sind die geordneten Stufen aus ``persoenlichkeit.MERKMALE``;
(3) jede Antwort IST eine Belegung dieses Kastens;
(4) KREUZ-KONSISTENZ zentral statt verstreut: knapp ⇒ kein Beiwerk (hier); wortlautfest ⇒
    keine Stimme (lebt strukturell in der Werkzeug-Spec, ``werkzeug.stimme_geeignet`` --
    schon EIN Ort, bleibt dort); die Rollen-Pins (Wache ⇒ nüchtern) leben im Code der
    Persönlichkeit (Wesens-Schutz, nie Daten).

Die WAHL der Zelle ist immer deterministisch (Register aus dem Graphen + Pins) -- kein
Modell wählt je eine Achse. Das Modell (die Stimme) formuliert nur INNERHALB der gewählten
Zelle: die :func:`anweisung` ist reine DATEN über die Membran (derselbe Weg wie die
GBNF-Grenze des Deuters), die Anker-Prüfung der Stimme bleibt die Leine. Ohne Modell zeigt
sich die Persönlichkeit ehrlich nur an den deterministischen Stellen (Floskel-Varianten,
Beiwerk, Morgen) -- Umformulieren ohne Modell wäre Erfindung.
"""
from __future__ import annotations

from genus import persoenlichkeit


def belegung(conn, rolle: str = "plausch", nutzer: str = persoenlichkeit.NUTZER) -> dict:
    """Die deterministische Belegung des Antwort-Würfels: das wirksame Register der Rolle,
    plus die Kreuz-Konsistenz-Folgen (Zwickys Schritt 4) als explizite Felder -- die eine
    Stelle, an der „knapp ⇒ kein Beiwerk" gilt, statt in jedem Verbraucher einzeln."""
    reg = persoenlichkeit.register(conn, rolle, nutzer)
    knapp = reg["knappheit"] == "knapp"
    reg["beiwerk_notiz"] = not knapp
    reg["beiwerk_rueckfrage"] = reg["neugier"] == "ja" and not knapp
    return reg


_TON = {
    "nuechtern": "sachlich und nüchtern",
    "warm": "freundlich und warm",
    "herzlich": "herzlich und zugewandt",
}


def anweisung(bel: dict) -> str | None:
    """Die Stil-Anweisung an die Stimme, aus der Belegung abgeleitet -- reine Daten für
    die Membran; ``None`` bei neutraler Belegung (die Stimme läuft dann wie bisher).

    EHRLICH BEGRENZT: nur Ton (Wärme) und Straffen (knapp). „ausführlich" kann die Stimme
    strukturell nie leisten -- sie fügt NIE hinzu (Anker-Leine), und mehr Worte ohne mehr
    Fakten wären Füllstoff oder Erfindung; mehr Umfang muss aus der ZELLE kommen (mehr
    Inhalt), nicht aus der Stimme. Humor bleibt bewusst draußen (heutiger Verbraucher:
    der Morgen-Schluss) -- ein Witz gehört nie in eine Wissens-Umformulierung."""
    teile = []
    ton = _TON.get(bel.get("waerme", ""))
    if ton:
        teile.append(f"Ton: {ton}.")
    if bel.get("knappheit") == "knapp":
        teile.append("Fasse dich so knapp wie möglich.")
    return " ".join(teile) or None


# Die Floskel-Varianten: reine SPRACHE (kein Fakt), deshalb hier an EINER Stelle statt in
# jedem Handler (Charta §2: keine zweite Wahrheit darüber, wie die Wärme wirkt). Der
# jeweilige Standard (test-verankerter Wortlaut) liegt auf der Saat-Stufe „warm".
FLOSKELN: dict[str, dict[str, str]] = {
    "gruss": {
        "nuechtern": "Hallo.",
        "neutral": "Hallo!",
        "warm": "Hallo! Schön, dass du da bist.",
        "herzlich": "Hallo! Wie schön, dass du da bist!",
    },
    "dank": {
        "nuechtern": "Gern.",
        "neutral": "Gern geschehen.",
        "warm": "Gern geschehen!",
        "herzlich": "Gern geschehen — jederzeit!",
    },
}
_GRUSS_RUECKFRAGE = " Was beschäftigt dich gerade?"
_GRUSS_HINWEIS = " Frag mich etwas, oder sag „was weißt du?“."


def floskel(conn, zelle: str, rolle: str = "plausch") -> str:
    """Die passende Floskel-Variante zur aktuellen Belegung; der Gruß trägt sein Beiwerk
    (die neugierige Rückfrage bzw. den Einstiegs-Hinweis) gemäß Kreuz-Konsistenz."""
    bel = belegung(conn, rolle)
    text = FLOSKELN[zelle].get(bel["waerme"], FLOSKELN[zelle]["neutral"])
    if zelle == "gruss":
        text += _GRUSS_RUECKFRAGE if bel["beiwerk_rueckfrage"] else _GRUSS_HINWEIS
    return text
