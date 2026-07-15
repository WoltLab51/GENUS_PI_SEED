#!/usr/bin/env python3
"""Selektiver Remote-Deuter fuer offene Telegram-Formulierungen.

Nur die aktuelle, bereits auf 1.000 Zeichen begrenzte Nachricht verlaesst den Pi. Verlauf,
Ledger, Antwort, Korrekturbeispiele und Nutzer-ID sind nicht Teil des Requests. Das Modell
liefert ausschliesslich strukturierte Lesarten; ``deuter.clean_segments`` und danach der
deterministische Kern pruefen Herkunft und Wirkung. Eine 0600-Zustimmungsdatei schaltet diesen
Pfad bewusst frei. Fehler, Rate-Limit und Tagesbudget fallen ohne lokales Grossmodell auf die
lokale Kernkette zurueck.
"""
from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Callable, Sequence

import deuter
import model_gateway


DEFAULT_MODEL = "openai/gpt-4.1-nano"
DEFAULT_CONSENT_FILE = os.path.expanduser("~/.genus/remote_deuter.enabled")
DEFAULT_BUDGET_FILE = os.path.expanduser("~/.genus/remote_deuter_budget.json")
CONSENT_VALUE = "github-models:remote_minimal"
MAX_TEXT_CHARS = 1000
MAX_OUTPUT_TOKENS = 160
DEFAULT_MINUTE_LIMIT = 10
DEFAULT_DAILY_LIMIT = 120
DEFAULT_TIMEOUT = 8.0
_MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*$", re.ASCII)


def schema_for(absichten: Sequence[str]) -> model_gateway.JsonSchema:
    leaves = tuple(dict.fromkeys((*absichten, "unklar")))
    if not leaves or any(not isinstance(leaf, str) or not leaf for leaf in leaves):
        raise ValueError("Remote-Deuter braucht ein nichtleeres Absichtsangebot")
    return model_gateway.JsonSchema(
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
                            "absicht": {"type": "string", "enum": list(leaves)},
                            "subject": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                            "object": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        },
                    },
                },
            },
        },
    )


def _private_regular_text(path: str | os.PathLike[str], *, missing_ok: bool = False) -> str | None:
    target = Path(path).expanduser()
    try:
        info = target.lstat()
    except FileNotFoundError:
        if missing_ok:
            return None
        raise model_gateway.GatewayError(f"Datei nicht lesbar: {target}") from None
    except OSError as exc:
        raise model_gateway.GatewayError(f"Datei nicht lesbar: {target}") from exc
    if not stat.S_ISREG(info.st_mode) or (os.name == "posix" and info.st_mode & 0o077):
        raise model_gateway.GatewayError(f"Datei muss regulaer und chmod 600 sein: {target}")
    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise model_gateway.GatewayError(f"Datei nicht lesbar: {target}") from exc


def consent_given(path: str | os.PathLike[str] = DEFAULT_CONSENT_FILE) -> bool:
    value = _private_regular_text(path, missing_ok=True)
    return value is not None and value.strip() == CONSENT_VALUE


def _write_budget(path: Path, day: str, count: int) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"utc_day": day, "requests": count}, handle, separators=(",", ":"))
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


class RemoteDeuter:
    """Ein kleiner, zustandsbehafteter Kosten- und Ausfallwaechter vor GitHub Models."""

    def __init__(
        self,
        provider: model_gateway.GitHubModels,
        *,
        model: str = DEFAULT_MODEL,
        budget_file: str | os.PathLike[str] = DEFAULT_BUDGET_FILE,
        minute_limit: int = DEFAULT_MINUTE_LIMIT,
        daily_limit: int = DEFAULT_DAILY_LIMIT,
        timeout: float = DEFAULT_TIMEOUT,
        clock: Callable[[], float] = time.time,
        reporter: Callable[[str], None] | None = None,
    ) -> None:
        if not _MODEL_ID.fullmatch(model):
            raise ValueError("ungueltige Remote-Modell-ID")
        if not 1 <= minute_limit <= 60 or not 1 <= daily_limit <= 1000:
            raise ValueError("ungueltiges Remote-Deuter-Budget")
        if not 1.0 <= timeout <= 30.0:
            raise ValueError("ungueltiger Remote-Deuter-Timeout")
        self.provider = provider
        self.model = model
        self.budget_file = Path(budget_file).expanduser()
        self.minute_limit = minute_limit
        self.daily_limit = daily_limit
        self.timeout = timeout
        self.clock = clock
        self.reporter = reporter or (lambda _message: None)
        self._recent: deque[float] = deque()
        self._blocked_until = 0.0

    def _consume_budget(self, now: float) -> None:
        while self._recent and now - self._recent[0] >= 60.0:
            self._recent.popleft()
        if now < self._blocked_until:
            raise model_gateway.GatewayError("Remote-Deuter ist nach einem Fehler kurz gesperrt")
        if len(self._recent) >= self.minute_limit:
            raise model_gateway.GatewayError("Remote-Deuter-Minutenbudget erreicht")

        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        count = 0
        raw = _private_regular_text(self.budget_file, missing_ok=True)
        if raw is not None:
            try:
                saved = json.loads(raw)
                if saved.get("utc_day") == day:
                    count = int(saved.get("requests", 0))
            except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise model_gateway.GatewayError("Remote-Deuter-Budgetdatei ist ungueltig") from exc
        if not 0 <= count < self.daily_limit:
            raise model_gateway.GatewayError("Remote-Deuter-Tagesbudget erreicht")
        _write_budget(self.budget_file, day, count + 1)
        self._recent.append(now)

    def interpret(self, message: str, *, absichten: Sequence[str] | None = None) -> list[dict]:
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Remote-Deuter braucht Nachrichtentext")
        if len(message) > MAX_TEXT_CHARS:
            raise model_gateway.GatewayError("Nachricht ist fuer Remote-Deutung zu lang")
        leaves = tuple(absichten or deuter.DEFAULT_ABSICHTEN)
        now = self.clock()
        self._consume_budget(now)
        try:
            result = self.provider.complete(
                model_gateway.ModelRequest(
                    role="deuter",
                    model=self.model,
                    privacy="remote_minimal",
                    messages=(
                        model_gateway.Message("system", deuter._system_prompt(leaves)),
                        model_gateway.Message("user", message),
                    ),
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    temperature=0.0,
                    schema=schema_for(leaves),
                ),
                timeout=self.timeout,
            )
            parsed = json.loads(result.content)
            entries = parsed.get("segments") if isinstance(parsed, dict) else None
            if not isinstance(entries, list):
                raise model_gateway.GatewayError("Remote-Deuter verletzte den Segmentvertrag")
            cleaned = deuter.clean_segments(entries, message)
        except (model_gateway.GatewayError, json.JSONDecodeError, AttributeError, TypeError) as exc:
            self._blocked_until = now + (300.0 if "HTTP 429" in str(exc) else 30.0)
            self.reporter(f"remote Deuter unavailable ({type(exc).__name__})")
            if isinstance(exc, model_gateway.GatewayError):
                raise
            raise model_gateway.GatewayError("Remote-Deuter lieferte ungueltige Struktur") from exc
        receipt = result.receipt
        self.reporter(
            f"remote Deuter used — model={receipt.model}, elapsed_ms={receipt.elapsed_ms}, "
            f"input_tokens={receipt.input_tokens}, output_tokens={receipt.output_tokens}, "
            f"segments={len(cleaned)}"
        )
        return cleaned


def from_environment(*, reporter: Callable[[str], None] | None = None) -> RemoteDeuter | None:
    consent_file = os.environ.get("GENUS_REMOTE_DEUTER_CONSENT_FILE", DEFAULT_CONSENT_FILE)
    if not consent_given(consent_file):
        return None
    model = os.environ.get("GENUS_REMOTE_DEUTER_MODEL", DEFAULT_MODEL).strip()
    token_file = os.environ.get("GENUS_GITHUB_MODELS_TOKEN_FILE", model_gateway.DEFAULT_TOKEN_FILE)
    provider = model_gateway.github_from_token_file(token_file, allow_remote_minimal=True)
    return RemoteDeuter(
        provider,
        model=model,
        budget_file=os.environ.get("GENUS_REMOTE_DEUTER_BUDGET_FILE", DEFAULT_BUDGET_FILE),
        minute_limit=int(os.environ.get("GENUS_REMOTE_DEUTER_MINUTE_LIMIT", DEFAULT_MINUTE_LIMIT)),
        daily_limit=int(os.environ.get("GENUS_REMOTE_DEUTER_DAILY_LIMIT", DEFAULT_DAILY_LIMIT)),
        timeout=float(os.environ.get("GENUS_REMOTE_DEUTER_TIMEOUT", DEFAULT_TIMEOUT)),
        reporter=reporter,
    )
