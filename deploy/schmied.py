"""Der SCHMIED (Edge): das Code-Modell der Werkstatt — entwirft den Handler-Code für ein
Raster-Blatt. Selbst-Codieren Stufe 2, Scheibe 2.

Wie Deuter und Stimme ein Organ am Rand: lebt in deploy/, der Kern importiert diese Datei
nie (Membran-Reinheit); das Modell ist ein GGUF via llama-cpp-python, lazy geladen, über
``GENUS_SCHMIED_MODEL`` gewählt — Modell-Wahl ist ein Konfig-Schalter, gemessen im
Benchmark (deploy/schmied_benchmark.py), nicht geraten.

Der Schmied ENTSCHEIDET nichts (Organ, nicht Orakel): sein Entwurf landet über
``genus werkstatt entwerfe --code-datei`` in der Werkstatt — außerhalb des Kerns, läuft
nie automatisch, Verbots-Scan + Sandbox-Probefahrt + menschlicher Merge wie bei jedem
Entwurf. Herkunft ehrlich: ``werkstatt:schmied``.

Die deterministische Leitplanke (dieselbe Denkweise wie der Anker-Check der Stimme):
Modell-Ausgabe wird per AST geprüft — sie muss GENAU eine Funktion ``zelle_<blatt>`` mit
dem uniformen Zellen-Vertrag definieren (conn, guess, question, last_question,
last_answer, stimme=None) und darf auf Modulebene nichts außer Imports/Konstanten/der
Funktion enthalten. Was die Prüfung nicht besteht, wird ``None`` — nie ein halbgarer
Entwurf, der später in der Werkstatt Zeit frisst.
"""
from __future__ import annotations

import ast
import os
import re
import sys

MODEL_PATH = os.environ.get(
    "GENUS_SCHMIED_MODEL",
    os.path.expanduser("~/.genus/models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"),
)
N_THREADS = int(os.environ.get("GENUS_SCHMIED_THREADS", "4"))

_model = None   # lazy Singleton, eigenes warmes Modell (Prompt-Cache-Lehre vom Deuter)

_CODEBLOCK = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL)

_VERTRAG = ["conn", "guess", "question", "last_question", "last_answer", "stimme"]


def _get_model():
    global _model
    if _model is None:
        from llama_cpp import Llama   # lokaler Import: Modul bleibt ohne die Dep importierbar
        _model = Llama(model_path=MODEL_PATH, n_threads=N_THREADS, n_ctx=4096, verbose=False)
    return _model


def _system_prompt() -> str:
    return (
        "Du schreibst EINE deutsche Python-Funktion für einen Sprach-Assistenten, der aus "
        "einem Wissens-Graphen antwortet.\n"
        "Vertrag (exakt einhalten):\n"
        "- Signatur: def zelle_<name>(conn, guess, question, last_question, last_answer, "
        "stimme=None):\n"
        "- conn ist eine sqlite3-Verbindung (row_factory=Row). guess ist ein dict mit "
        "'absicht', 'subject', 'object' (Strings oder None). question ist die Nutzerfrage.\n"
        "- Die Funktion LIEST NUR (SELECT) — niemals schreiben, niemals importieren von "
        "Netzwerk/Prozess/Modell-Bibliotheken.\n"
        "- Rückgabe: ein deutscher Antwortsatz (str) — oder None, wenn ehrlich nichts "
        "Belegbares da ist. NIEMALS Fakten erfinden.\n"
        "- Nur Standardbibliothek. Kein Code auf Modulebene außer Imports und der Funktion.\n"
        "Gib NUR den Python-Code zurück, in einem ```python-Block, ohne Erklärtext."
    )


def _signatur_ok(fn: ast.FunctionDef) -> bool:
    args = [a.arg for a in fn.args.args]
    if args != _VERTRAG:
        return False
    # genau ein Default (stimme=None), keine *args/**kwargs
    return (len(fn.args.defaults) == 1 and fn.args.vararg is None
            and fn.args.kwarg is None and not fn.args.kwonlyargs)


def _ast_leitplanke(code: str, blatt: str) -> str | None:
    """Deterministische Annahme-Prüfung: parsebar, genau die Vertragsfunktion, nichts
    Fremdes auf Modulebene. Gibt den (unveränderten) Code zurück oder ``None``."""
    name = "zelle_" + blatt.replace("-", "_")
    try:
        baum = ast.parse(code)
    except SyntaxError:
        return None
    funktionen = [k for k in baum.body if isinstance(k, ast.FunctionDef)]
    if len(funktionen) != 1 or funktionen[0].name != name:
        return None
    if not _signatur_ok(funktionen[0]):
        return None
    for knoten in baum.body:
        if isinstance(knoten, ast.Expr):
            # auf Modulebene ist ein Ausdruck nur als Docstring erlaubt -- ein Aufruf
            # (print, os.irgendwas) wäre Code, der beim IMPORT liefe
            if not (isinstance(knoten.value, ast.Constant)
                    and isinstance(knoten.value.value, str)):
                return None
            continue
        if not isinstance(knoten, (ast.FunctionDef, ast.Import, ast.ImportFrom, ast.Assign)):
            return None   # kein Code auf Modulebene außer Imports/Konstanten/Docstring
    return code


def schmiede(blatt: str, beschreibung: str = "") -> str | None:
    """Entwirft den Handler-Code für ``blatt``. ``None``, wenn kein Modell installiert
    ist oder die Ausgabe die AST-Leitplanke nicht besteht — nie ein halbgarer Entwurf."""
    if not os.path.exists(MODEL_PATH):
        return None
    auftrag = (f"Schreibe die Funktion zelle_{blatt.replace('-', '_')} für die "
               f"Gesprächs-Lesart „{blatt}“.")
    if beschreibung:
        auftrag += f" Sie soll: {beschreibung}"
    try:
        model = _get_model()
        result = model.create_chat_completion(
            messages=[
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": auftrag},
            ],
            max_tokens=700,
            temperature=0.0,
        )
        text = result["choices"][0]["message"]["content"]
    except Exception as exc:
        print(f"[SCHMIED] Modell-Lauf gescheitert ({exc})", file=sys.stderr)
        return None
    m = _CODEBLOCK.search(text)
    code = (m.group(1) if m else text).strip() + "\n"
    return _ast_leitplanke(code, blatt)


_JSON_OBJEKT = re.compile(r"\{.*\}", re.DOTALL)


def _bauplan_prompt() -> str:
    return (
        "Du füllst einen kompakten BAUPLAN (JSON) für eine deutsche Antwort-Zelle eines "
        "Sprach-Assistenten. Du schreibst KEINEN Code — nur den Plan; ein deterministisches "
        "Fügewerk baut daraus den Code.\n"
        "Felder (exakt diese, keine weiteren):\n"
        '- "waechter": "subject" (die Zelle braucht guess[subject]) oder "keiner".\n'
        '- "beschaffung": {"art": "keine"} ODER {"art": "anzahl_kanten", "praedikat": '
        'optional} ODER {"art": "erstes_objekt", "praedikat": "<name>"}. anzahl_kanten '
        "zählt Graph-Kanten des Subjekts (liefert Slot {anzahl}); erstes_objekt liest das "
        "alphabetisch erste Objekt zum Prädikat (liefert Slot {wert}); keine liest nichts "
        "(nur Slot {subject}).\n"
        '- "formulierung": der EXAKTE deutsche Antwortsatz als Template. Übernimm den in '
        "der Aufgabe geforderten Wortlaut ZEICHENGENAU (inklusive deutscher "
        "Anführungszeichen „ und “), ersetze nur die variablen Teile durch Slots wie "
        "{subject}, {anzahl}, {wert}.\n"
        "Gib NUR das JSON-Objekt zurück, ohne Erklärtext."
    )


def schmiede_bauplan(blatt: str, beschreibung: str = "") -> dict | None:
    """Schmied v2 (Ronnys morphologische Zerlegung): das Modell liefert nur den BAUPLAN
    (kleines JSON) -- Wortlaut-Template, Wächter, Beschaffung. Den Code fügt das
    deterministische Fügewerk (genus/bauplan.py) im Kern. ``None``, wenn kein Modell da
    ist, kein JSON kam oder der Plan die Kern-Prüfung nicht bestünde (die läuft beim
    Fügen erneut -- hier nur die Membran-Vorprüfung: parsebares JSON-Objekt)."""
    if not os.path.exists(MODEL_PATH):
        return None
    auftrag = f"Fülle den Bauplan für die Gesprächs-Lesart „{blatt}“."
    if beschreibung:
        auftrag += f" Aufgabe: {beschreibung}"
    try:
        import json
        model = _get_model()
        result = model.create_chat_completion(
            messages=[
                {"role": "system", "content": _bauplan_prompt()},
                {"role": "user", "content": auftrag},
            ],
            max_tokens=300,
            temperature=0.0,
        )
        text = result["choices"][0]["message"]["content"]
        m = _JSON_OBJEKT.search(text)
        if m is None:
            return None
        return json.loads(m.group(0))
    except Exception as exc:
        print(f"[SCHMIED] Bauplan-Lauf gescheitert ({exc})", file=sys.stderr)
        return None


if __name__ == "__main__":
    blatt = sys.argv[1] if len(sys.argv) > 1 else "weltfrage"
    beschreibung = " ".join(sys.argv[2:])
    code = schmiede(blatt, beschreibung)
    if code is None:
        print("[SCHMIED] kein Entwurf (Modell fehlt oder Leitplanke nicht bestanden)",
              file=sys.stderr)
        sys.exit(1)
    print(code)
