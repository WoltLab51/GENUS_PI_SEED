#!/usr/bin/env python3
"""Kleine, synthetische GENUS-Probe für lokale Deuter-Modelle.

Misst genau die Aufgabe des Edge-Modells (deutsche Äußerung -> bekannte Absicht), nicht
allgemeine Chat-Benchmarks. Die Texte sind künstlich und enthalten keine Chat- oder Nutzerdaten.
Ein Modell wird nach jeder Runde geschlossen, damit mehrere Kandidaten auf dem Pi fair und ohne
dauerhaft aufaddierten RAM verglichen werden können.
"""
from __future__ import annotations

import argparse
import json
import os
import time

import deuter
from genus import verstehen


CASES = (
    ("Hallo GENUS", ["gruss"]),
    ("Danke dir!", ["dank"]),
    ("Bis morgen, mach's gut.", ["abschied"]),
    ("Ich teste dich grad, denn wir haben einen neuen Worker angeschlossen", ["tatsache"]),
    ("Ich bin heute ziemlich müde.", ["tatsache"]),
    ("Merke dir: Mein Lieblingsgetränk ist Kaffee.", ["merken"]),
    ("Was ist ein Vulkan?", ["definition"]),
    ("Ist ein Hund ein Säugetier?", ["beziehung"]),
    ("Was haben Hund und Wolf gemeinsam?", ["vergleich"]),
    ("Welchen Artikel hat Sonne?", ["grammatik"]),
    ("Welche Eigenschaften hat Glas?", ["eigenschaft"]),
    ("Was löst Kopfschmerzen aus?", ["ursache"]),
    ("Wie viele Monde hat der Mars?", ["menge"]),
    ("Liegt Kassel in Hessen?", ["ort"]),
    ("Wie geht es dir gerade?", ["zustand"]),
    ("Wer bist du eigentlich?", ["selbstbild"]),
    ("Was kannst du schon?", ["faehigkeiten"]),
    ("Was sind deine Ziele?", ["ziele"]),
    ("Was weißt du über mich?", ["erinnerungs-abruf"]),
    ("Woher weißt du das?", ["warum-herkunft"]),
    ("Erklär das bitte genauer.", ["vertiefung"]),
    ("Kannst du das kürzer sagen?", ["kuerzer"]),
    ("Sag das bitte noch einmal.", ["wiederholen"]),
    ("Wie wird morgen das Wetter?", ["weltfrage"]),
    ("Nein, ein Wal ist kein Fisch.", ["korrektur"]),
    ("Ich finde deine Antwort zu technisch.", ["meinung"]),
    ("Lerne bitte etwas über Photosynthese.", ["lernen"]),
    ("Kannst du mir beim Planen eines Ausflugs helfen?", ["tun"]),
    ("Warum?", ["warum-herkunft"]),
    ("Hallo! Was ist ein Hund? Danke!", ["gruss", "definition", "dank"]),
)


def _rss_mib() -> float | None:
    try:
        with open("/proc/self/status", encoding="ascii") as status:
            for line in status:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        return None
    return None


def _model_arg(value: str) -> tuple[str, str]:
    name, separator, path = value.partition("=")
    if not separator or not name or not path:
        raise argparse.ArgumentTypeError("erwartet NAME=/pfad/zum/modell.gguf")
    return name, path


def run(name: str, path: str, cases=CASES) -> dict:
    deuter.release_model()
    deuter.MODEL_PATH = path
    grammar = verstehen.gbnf_grammatik(deuter.DEFAULT_ABSICHTEN)
    # Hält die Probe auch gegen einen noch nicht deployten Pi-Checkout repräsentativ.
    grammar = grammar.replace(
        '(ws "," ws segment)*',
        '(ws "," ws segment)? (ws "," ws segment)?',
    )
    grammar = grammar.replace(
        'ws ::= [ \\t\\n\\r]*',
        'ws ::= [ \\t\\n\\r]? [ \\t\\n\\r]? [ \\t\\n\\r]? [ \\t\\n\\r]?',
    )
    rows = []
    started = time.monotonic()
    for text, expected in cases:
        case_started = time.monotonic()
        result = deuter.interpret(text, grammatik=grammar)
        actual = None if result is None else [item["absicht"] for item in result]
        rows.append({
            "text": text,
            "expected": expected,
            "actual": actual,
            "ok": actual == expected,
            "seconds": round(time.monotonic() - case_started, 3),
        })
    rss = _rss_mib()
    report = {
        "model": name,
        "path": os.path.basename(path),
        "passed": sum(row["ok"] for row in rows),
        "total": len(rows),
        "seconds": round(time.monotonic() - started, 3),
        "rss_mib": round(rss, 1) if rss is not None else None,
        "failures": [row for row in rows if not row["ok"]],
    }
    deuter.release_model()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="append", required=True, type=_model_arg,
                        metavar="NAME=GGUF", help="wiederholbar; lokale Kandidaten")
    parser.add_argument("--limit", type=int, help="nur die ersten N synthetischen Faelle")
    args = parser.parse_args(argv)
    cases = CASES[:args.limit] if args.limit is not None else CASES
    reports = [run(name, path, cases) for name, path in args.model]
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0 if all(report["passed"] == report["total"] for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
