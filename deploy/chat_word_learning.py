#!/usr/bin/env python3
"""Small, deletable edge-state for explicit chat word learning.

The ledger remains the source of acquired knowledge.  This file only lets the Telegram
membrane tell ``queued`` from ``learning`` and ``failed`` while the asynchronous learner is
working.  It stores no message text, Telegram identifier, or answer.
"""
from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from typing import Iterator

STATUSES = frozenset({"queued", "learning", "learned", "failed"})
MAX_ENTRIES = 200
MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def normalize_term(term: str) -> str:
    """Use the same conservative spelling at the queue, status, and graph boundaries."""
    cleaned = " ".join((term or "").strip().split())
    if not cleaned:
        return ""
    return cleaned if cleaned.isupper() else cleaned[:1].upper() + cleaned[1:]


def default_path() -> str:
    return os.environ.get(
        "GENUS_CHAT_WORD_STATUS_FILE",
        os.path.join(os.path.expanduser("~"), ".genus", "chat_word_learning_status.json"),
    )


@contextmanager
def _locked(path: str) -> Iterator[None]:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lock_path = path + ".lock"
    with open(lock_path, "a", encoding="ascii") as lock:
        os.chmod(lock_path, 0o600)
        try:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        except ImportError:  # pragma: no cover - production is Linux
            pass
        yield


def _load(path: str, now: float) -> dict[str, dict]:
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return {}
    entries = raw.get("entries", {}) if isinstance(raw, dict) else {}
    if not isinstance(entries, dict):
        return {}
    valid = {}
    for key, entry in entries.items():
        if not isinstance(entry, dict) or entry.get("status") not in STATUSES:
            continue
        try:
            updated = float(entry.get("updated", 0))
        except (TypeError, ValueError):
            continue
        term = normalize_term(str(entry.get("term", "")))
        if term and now - updated <= MAX_AGE_SECONDS:
            valid[str(key)] = {"term": term, "status": entry["status"], "updated": updated}
    newest = sorted(valid.items(), key=lambda item: item[1]["updated"], reverse=True)
    return dict(newest[:MAX_ENTRIES])


def _write(path: str, entries: dict[str, dict]) -> None:
    tmp = f"{path}.tmp-{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            os.chmod(tmp, 0o600)
            json.dump({"version": 1, "entries": entries}, handle, ensure_ascii=False,
                      separators=(",", ":"))
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        try:
            os.remove(tmp)
        except FileNotFoundError:
            pass


def get_status(term: str, *, path: str | None = None, now: float | None = None) -> str | None:
    normalized = normalize_term(term)
    if not normalized:
        return None
    path = path or default_path()
    now = time.time() if now is None else now
    with _locked(path):
        entry = _load(path, now).get(normalized.casefold())
    return str(entry["status"]) if entry else None


def mark(term: str, status: str, *, path: str | None = None,
         now: float | None = None) -> bool:
    normalized = normalize_term(term)
    if not normalized or status not in STATUSES:
        return False
    path = path or default_path()
    now = time.time() if now is None else now
    with _locked(path):
        entries = _load(path, now)
        previous = entries.get(normalized.casefold(), {}).get("status")
        # The bot writes ``queued`` just after appending to the queue.  The learner may already
        # have dequeued the word in that tiny window; never let the later bot write move a
        # concurrent ``learning``/``learned`` state backwards.
        if status == "queued" and previous in {"learning", "learned"}:
            return True
        entries[normalized.casefold()] = {
            "term": normalized,
            "status": status,
            "updated": now,
        }
        newest = sorted(entries.items(), key=lambda item: item[1]["updated"], reverse=True)
        _write(path, dict(newest[:MAX_ENTRIES]))
    return True


def explainable(conn, term: str) -> bool:
    """Use the real deterministic definition contract, not mere lexical presence."""
    from genus import auskunft

    normalized = normalize_term(term)
    return bool(normalized and auskunft.erklaerbar(auskunft.answer(conn, normalized)))


def _finish(term: str, db_path: str) -> bool:
    from genus import db

    normalized = normalize_term(term)
    conn = db.connect(db_path)
    try:
        learned = explainable(conn, normalized)
    finally:
        conn.close()
    mark(normalized, "learned" if learned else "failed")
    return learned


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 3 and args[0] == "mark":
        return 0 if mark(args[1], args[2]) else 2
    if len(args) == 3 and args[0] == "finish":
        return 0 if _finish(args[1], args[2]) else 1
    print("usage: chat_word_learning.py mark TERM STATUS | finish TERM DB_PATH", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
