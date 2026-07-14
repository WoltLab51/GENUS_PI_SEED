#!/usr/bin/env python3
"""Synthetischer Stimmen-Bake-off ueber die lebende GENUS-Alltagsprobe.

Es werden ausschliesslich lokal erzeugte Testantworten versendet. Der Pfad akzeptiert keine
Chatdatei und keine freie Nutzereingabe. Ergebnisse gehen als JSONL nach stdout; das Secret
bleibt in ``~/.genus/github_models_token`` (chmod 600).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "deploy"))

from genus import alltagsprobe  # noqa: E402
import model_gateway  # noqa: E402
import stimme  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Vergleicht GitHub-Modelle nur auf synthetischen GENUS-Antworten.",
    )
    parser.add_argument("--model", action="append", required=True,
                        help="GitHub-Modell-ID; mehrfach angeben fuer einen Vergleich")
    parser.add_argument("--token-file", default=model_gateway.DEFAULT_TOKEN_FILE,
                        help="private PAT-Datei (Default: ~/.genus/github_models_token)")
    parser.add_argument("--max-cases", type=int, default=5,
                        help="hoechstens so viele der 17 Alltagsfaelle (Default: 5)")
    parser.add_argument("--max-requests", type=int, default=20,
                        help="harte Obergrenze fuer Provideraufrufe (Default: 20)")
    parser.add_argument("--min-request-interval", type=float, default=4.1,
                        help="Mindestabstand zwischen Aufrufen in Sekunden (Default: 4.1)")
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser


def _synthetic_answers(max_cases: int) -> list[tuple[str, int, str]]:
    if not 1 <= max_cases <= len(alltagsprobe.ALLTAGSFAELLE):
        raise ValueError(f"max-cases muss zwischen 1 und {len(alltagsprobe.ALLTAGSFAELLE)} liegen")
    answers: list[tuple[str, int, str]] = []
    for scenario in alltagsprobe.ALLTAGSFAELLE[:max_cases]:
        result = alltagsprobe.run_scenario(scenario)
        if not result.hard_ok:
            raise RuntimeError(f"Alltagsfall {scenario.id} verletzt vor dem Bake-off harte Vertraege")
        answers.extend((scenario.id, index, turn.text) for index, turn in enumerate(result.turns))
    return answers


def run(args: argparse.Namespace, provider=None, *, clock=time.monotonic, sleeper=time.sleep) -> int:
    models = tuple(dict.fromkeys(model.strip() for model in args.model if model.strip()))
    if not models:
        raise ValueError("mindestens ein nichtleeres Modell ist erforderlich")
    answers = _synthetic_answers(args.max_cases)
    request_count = len(models) * len(answers)
    if not 1 <= args.max_requests <= 100:
        raise ValueError("max-requests muss zwischen 1 und 100 liegen")
    if request_count > args.max_requests:
        raise ValueError(
            f"Bake-off braeuchte {request_count} Aufrufe, Limit ist {args.max_requests}"
        )
    min_request_interval = args.min_request_interval
    if not 0 <= min_request_interval <= 60:
        raise ValueError("min-request-interval muss zwischen 0 und 60 Sekunden liegen")
    provider = provider or model_gateway.github_from_token_file(args.token_file)
    last_request_started: float | None = None
    for model in models:
        for case_id, turn_index, original in answers:
            request = model_gateway.ModelRequest(
                role="stimme",
                model=model,
                privacy="synthetic",
                messages=(
                    model_gateway.Message("system", stimme.system_prompt()),
                    model_gateway.Message("user", original),
                ),
                max_output_tokens=200,
                temperature=0.3,
            )
            try:
                if last_request_started is not None:
                    remaining = min_request_interval - (clock() - last_request_started)
                    if remaining > 0:
                        sleeper(remaining)
                last_request_started = clock()
                result = provider.complete(request, timeout=args.timeout)
                accepted, validation = stimme.pruefbericht(original, result.content)
                row = {
                    "case": case_id,
                    "turn": turn_index,
                    "accepted": accepted is not None,
                    "original": original,
                    "candidate": accepted,
                    "raw_candidate": result.content,
                    "validation": validation,
                    "receipt": result.receipt.as_dict(),
                }
            except model_gateway.GatewayError as exc:
                row = {
                    "case": case_id,
                    "turn": turn_index,
                    "accepted": False,
                    "original": original,
                    "candidate": None,
                    "raw_candidate": None,
                    "validation": "provider_fehler",
                    "error": str(exc),
                    "provider": provider.name,
                    "model": model,
                }
            print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (ValueError, RuntimeError, model_gateway.GatewayError) as exc:
        parser.exit(2, f"[BAKEOFF] {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
