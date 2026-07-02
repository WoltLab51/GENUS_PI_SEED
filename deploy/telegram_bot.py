#!/usr/bin/env python3
"""Telegram bridge — a conversational membrane at the edge, nothing more.

Long-polls Telegram's Bot API (outbound HTTPS only; no inbound port, no public server needed)
and answers each allowed message with `genus.companion.respond_with_deuter` -- the same
read-only routing `genus ask` uses (state -> relational -> comparative -> gender -> word ->
help), aware of the PREVIOUS message in the same chat so a bare "warum?"/"woher weißt du das?"
retraces it instead of failing (per-chat state lives here in the membrane, in-process only --
the ledger stays the source of epistemic truth, this is UX plumbing, not knowledge). As the
LAST resort, when nothing deterministic answers at all, a local edge model (deuter.py, kept
warm in this process) may guess an intent + subject -- never trusted blindly, graph-verified
by the core before it acts, never writing the answer itself. The core is untouched: this is a
new DOOR, not a new ROOM. Strictly answer-only -- no proposal, governance, pause/resume, or any
state-changing command is reachable here, on purpose (Hände stay parked; this is a Mundstück).

Security: a message is answered ONLY if its sender's Telegram user id is on the allow-list
(GENUS_TELEGRAM_ALLOWED_IDS). Everyone else is silently ignored (logged, not replied to, so a
stranger probing the bot learns nothing). The bot token is a real secret: read from
GENUS_TELEGRAM_BOT_TOKEN or, failing that, a file (default ~/.genus/telegram_bot_token, meant to
be chmod 600) -- never hardcoded, never logged, never committed.
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

GENUS_USER_HOME = os.path.expanduser("~")
DB_PATH = os.environ.get("GENUS_DB_PATH", os.path.join(GENUS_USER_HOME, ".genus", "genus.sqlite3"))
LOG_DIR = os.environ.get("GENUS_LOG_DIR", os.path.join(GENUS_USER_HOME, ".genus", "logs"))
TOKEN_FILE = os.environ.get(
    "GENUS_TELEGRAM_TOKEN_FILE", os.path.join(GENUS_USER_HOME, ".genus", "telegram_bot_token")
)
OFFSET_FILE = os.path.join(GENUS_USER_HOME, ".genus", "telegram_bot.offset")
UA = "GENUS-PI/0.1 (personal companion bridge)"
_CTX = ssl.create_default_context()


def _log(msg: str) -> None:
    line = f"[TG] {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
    print(line, flush=True)


def _token() -> str:
    token = os.environ.get("GENUS_TELEGRAM_BOT_TOKEN", "").strip()
    if token:
        return token
    try:
        with open(TOKEN_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _allowed_ids() -> set[int]:
    raw = os.environ.get("GENUS_TELEGRAM_ALLOWED_IDS", "").strip()
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            try:
                ids.add(int(part))
            except ValueError:
                _log(f"ignoring malformed id in GENUS_TELEGRAM_ALLOWED_IDS: {part!r}")
    return ids


def _api(token: str, method: str, params: dict, timeout: int) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_updates(token: str, offset: int) -> list[dict]:
    body = _api(token, "getUpdates", {"offset": offset, "timeout": 25}, timeout=35)
    return body.get("result", []) if body.get("ok") else []


def _send_message(token: str, chat_id: int, text: str) -> None:
    # Telegram caps a message at 4096 chars; a companion answer never gets close, but stay safe.
    _api(token, "sendMessage", {"chat_id": chat_id, "text": text[:4000]}, timeout=15)


def _load_offset() -> int:
    try:
        with open(OFFSET_FILE, encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except (FileNotFoundError, ValueError):
        return 0


def _save_offset(offset: int) -> None:
    with open(OFFSET_FILE, "w", encoding="utf-8") as f:
        f.write(str(offset))


def handle_update(
    conn, update: dict, allowed: set[int], sessions: dict[int, str] | None = None
) -> tuple[int, str] | None:
    """Pure logic, no network: given one Telegram update + the allow-list, decide whether to
    answer and with what -- ``None`` if the sender isn't allowed or there's no text to answer.

    ``sessions`` (optional), keyed by chat_id, holds each conversation's last question so a bare
    follow-up ("warum?", "woher weißt du das?") can be read against it (``companion.
    respond_in_conversation``) instead of falling through to "kein Wort bekannt". In-process
    only, forgotten on a restart -- an honest, small limitation: this is UX-session plumbing,
    not knowledge, so it deliberately doesn't touch the ledger (Ledger != Memory). Omit
    ``sessions`` for the plain, stateless behaviour (unchanged)."""
    from genus import companion
    import deuter

    message = update.get("message") or update.get("edited_message")
    if not message or "text" not in message:
        return None
    sender = message.get("from", {}).get("id")
    chat_id = message.get("chat", {}).get("id")
    if sender is None or chat_id is None:
        return None
    if sender not in allowed:
        _log(f"ignored message from unauthorized id {sender}")
        return None
    question = message["text"]
    _log(f"question from {sender}: {question!r}")
    try:
        if sessions is None:
            answer = companion.respond(conn, question)
        else:
            result = companion.respond_with_deuter(
                conn, question, sessions.get(chat_id), deuter=deuter.interpret,
            )
            answer = result["text"]
            sessions[chat_id] = result["question"]
    except Exception as exc:  # a bug in answering must never take the bridge down
        _log(f"error answering {question!r}: {exc}")
        answer = "Da ist etwas schiefgelaufen — GENUS konnte diese Frage gerade nicht beantworten."
    return chat_id, answer


def main() -> int:
    token = _token()
    if not token:
        _log("no bot token (GENUS_TELEGRAM_BOT_TOKEN or telegram_bot_token file) — refusing to start")
        return 1
    allowed = _allowed_ids()
    if not allowed:
        _log("GENUS_TELEGRAM_ALLOWED_IDS is empty — refusing to start (no open bots)")
        return 1
    _log(f"telegram bridge started — {len(allowed)} allowed id(s)")

    os.makedirs(LOG_DIR, exist_ok=True)
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    offset = _load_offset()
    sessions: dict[int, str] = {}   # chat_id -> last question; in-process only, see handle_update
    while True:
        try:
            updates = _get_updates(token, offset)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            _log(f"getUpdates failed ({exc}) — retrying shortly")
            time.sleep(5)
            continue
        for update in updates:
            offset = max(offset, update["update_id"] + 1)
            result = handle_update(conn, update, allowed, sessions)
            if result is not None:
                chat_id, answer = result
                try:
                    _send_message(token, chat_id, answer)
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    _log(f"sendMessage failed ({exc})")
            _save_offset(offset)


if __name__ == "__main__":
    sys.exit(main())
