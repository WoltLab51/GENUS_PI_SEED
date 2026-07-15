#!/usr/bin/env python3
"""Synthetischer Deuter-Vergleich über die providerneutrale GitHub-Models-Membran."""
from __future__ import annotations

import argparse
import json
import time

import deuter
from deuter_benchmark import CASES
import model_gateway


SCHEMA = model_gateway.JsonSchema(
    "genus_deuter_segmente",
    {
        "type": "object",
        "additionalProperties": False,
        "required": ["segments"],
        "properties": {
            "segments": {
                "type": "array",
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text", "absicht", "subject", "object"],
                    "properties": {
                        "text": {"type": "string"},
                        "absicht": {"type": "string", "enum": list(deuter.DEFAULT_ABSICHTEN)},
                        "subject": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        "object": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    },
                },
            },
        },
    },
)


def run(args, provider=None, *, clock=time.monotonic, sleeper=time.sleep) -> int:
    cases = CASES[args.offset:args.offset + args.limit]
    models = list(dict.fromkeys(args.model))
    requests = len(cases) * len(models)
    if requests > args.max_requests:
        raise ValueError(f"braeuchte {requests} Aufrufe, Budget ist {args.max_requests}")
    provider = provider or model_gateway.github_from_token_file(args.token_file)
    reports = []
    last_request_at = None
    for model in models:
        rows = []
        for text, expected in cases:
            if last_request_at is not None:
                wait = args.min_request_interval - (clock() - last_request_at)
                if wait > 0:
                    sleeper(wait)
            started = clock()
            try:
                result = provider.complete(
                    model_gateway.ModelRequest(
                        role="deuter",
                        model=model,
                        privacy="synthetic",
                        messages=(
                            model_gateway.Message(
                                "system", deuter._system_prompt(deuter.DEFAULT_ABSICHTEN),
                            ),
                            model_gateway.Message("user", text),
                        ),
                        max_output_tokens=160,
                        temperature=0.0,
                        schema=SCHEMA,
                    ),
                    timeout=args.timeout,
                )
                parsed = json.loads(result.content)["segments"]
                cleaned = deuter.clean_segments(parsed, text)
                actual = [item["absicht"] for item in cleaned]
                error = None
                receipt = result.receipt.as_dict()
            except (model_gateway.GatewayError, json.JSONDecodeError, TypeError) as exc:
                actual = None
                error = f"{type(exc).__name__}: {exc}"
                receipt = None
            last_request_at = clock()
            rows.append({
                "text": text,
                "expected": expected,
                "actual": actual,
                "ok": actual == expected,
                "elapsed_ms": round((clock() - started) * 1000),
                "error": error,
                "receipt": receipt,
            })
        reports.append({
            "model": model,
            "passed": sum(row["ok"] for row in rows),
            "total": len(rows),
            "failures": [row for row in rows if not row["ok"]],
        })
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0 if all(report["passed"] == report["total"] for report in reports) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--max-requests", type=int, default=20)
    parser.add_argument("--min-request-interval", type=float, default=4.1)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--token-file", default=model_gateway.DEFAULT_TOKEN_FILE)
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= len(CASES) or not 0 <= args.offset < len(CASES):
        parser.error(f"--limit muss zwischen 1 und {len(CASES)} liegen")
    if args.offset + args.limit > len(CASES):
        parser.error("--offset + --limit liegt ausserhalb der synthetischen Faelle")
    try:
        return run(args)
    except (ValueError, model_gateway.GatewayError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
