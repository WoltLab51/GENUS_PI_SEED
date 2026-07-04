#!/usr/bin/env python3
"""Telegram bridge — a conversational membrane at the edge, nothing more.

Long-polls Telegram's Bot API (outbound HTTPS only; no inbound port, no public server needed)
and answers each allowed message with `genus.companion.respond_with_deuter` -- the
Verstehens-Würfel (Rituale -> Muster-Zellen -> offene Deuter-Lesart aufs Absichts-Raster ->
Wort-Lesart), aware of a bounded WINDOW of previous turns in the same chat (Mehr-Zug-
Arbeitsgedächtnis, docs/GENUS_GEDAECHTNIS.md Punkt 4) -- a bare "warum?"/"woher weißt du das?"
retraces the last turn, and "... von vorhin"/"... von eben" can reach further back, instead of
failing (per-chat state lives here in the membrane, in-process only -- the ledger stays the
source of epistemic truth, this is UX plumbing, not knowledge).
Two capped edge models, both dependency-injected, never trusted blindly: `deuter.py` reads
free phrasing INTO the deterministic core (an intent/subject/object GUESS, graph-verified
before anything acts); `stimme.py` reads an ALREADY-verified answer back OUT more naturally
(a faithfulness-checked rephrase -- every quoted word/number must survive, or the original
template stands). Each keeps its OWN warm 1.5B model, deliberately NOT shared -- live measured
(2026-07-03): sharing one model meant every Stimme call evicted the Deuter's llama.cpp prompt
cache (a different system prompt), so the NEXT Deuter call had to reprocess its whole ~1300-
token prompt from scratch (26s instead of 3s). Two models cost ~1-1.5 GB more RAM (the Pi has
plenty free) but keep latency predictable instead of depending on call order. Neither ever
writes the answer itself. The core is untouched: this is a new DOOR, not a new ROOM. Strictly
answer-only -- no proposal, governance, pause/resume, or any state-changing command is
reachable here, on purpose (Hände stay parked; this is a Mundstück).

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
_VERLAUF_MAX = 6   # Mehr-Zug-Arbeitsgedächtnis: wie viele Züge pro Chat im Blick bleiben

# Der Lernkreis v1 (Naht 4): korrigierte Beispiele sind MEMBRAN-Wissen -- eine Edge-Datei
# wie die Lerner-Cursor (learn.cursor, learn.gap_attempts), nie das Ledger. Der Text der
# korrigierten Frage wohnt nur hier: löschbar, nicht versiegelt, nicht Teil des Organismus.
# Das Ledger trägt weiterhin nur die Struktur (fehlgriff/fehlgriff_statt-Kanten).
KORREKTUR_DATEI = os.environ.get(
    "GENUS_KORREKTUR_DATEI", os.path.join(GENUS_USER_HOME, ".genus", "korrekturen.jsonl")
)
_KORREKTUR_MAX = 50       # die Datei bleibt gedeckelt: die jüngsten 50 Korrekturen
_HINWEIS_BEISPIELE = 3    # wie viele Beispiele der Prompt höchstens trägt (nie wachsend)


def _merke_korrektur(frage: str, falsch: list[str], richtig: str | None) -> None:
    """Ein korrigiertes Paar in die Edge-Datei -- das künftige Futter des Embedder-
    Vergleichs. Gedeckelt auf die jüngsten _KORREKTUR_MAX Einträge."""
    eintrag = json.dumps({"text": frage, "falsch": falsch, "richtig": richtig},
                         ensure_ascii=False)
    zeilen: list[str] = []
    try:
        with open(KORREKTUR_DATEI, encoding="utf-8") as f:
            zeilen = [z for z in f.read().splitlines() if z.strip()]
    except FileNotFoundError:
        pass
    zeilen = (zeilen + [eintrag])[-_KORREKTUR_MAX:]
    os.makedirs(os.path.dirname(KORREKTUR_DATEI), exist_ok=True)
    with open(KORREKTUR_DATEI, "w", encoding="utf-8") as f:
        f.write("\n".join(zeilen) + "\n")


def _korrektur_hinweise(conn) -> list[dict]:
    """Der Rückfluss für den Deuter-Prompt, pro Nachricht frisch berechnet (erinnern +
    neu rechnen): bekannte Verwechslungen aus dem Graphen (selbst-kalibrierte Schwelle)
    plus die jüngsten korrigierten Beispiele mit benanntem Ziel-Blatt aus der Edge-Datei
    -- beides gedeckelt. Stabil zwischen zwei Korrekturen, damit der Prompt-Präfix-Cache
    des Deuters warm bleibt (der Abschnitt hängt am Prompt-ENDE)."""
    from genus import verstehen

    hinweise = [
        {"gelesen": v["gelesen"], "gemeint": v["gemeint"]}
        for v in verstehen.verwechslungen(conn)[:_HINWEIS_BEISPIELE]
    ]
    try:
        with open(KORREKTUR_DATEI, encoding="utf-8") as f:
            zeilen = [z for z in f.read().splitlines() if z.strip()]
    except FileNotFoundError:
        zeilen = []
    beispiele = 0
    for zeile in reversed(zeilen):
        if beispiele >= _HINWEIS_BEISPIELE:
            break
        try:
            k = json.loads(zeile)
        except ValueError:
            continue
        if k.get("richtig") and k.get("text"):
            hinweise.append({
                "gelesen": (k.get("falsch") or [None])[0],
                "gemeint": k["richtig"],
                "beispiel": k["text"],
            })
            beispiele += 1
    return hinweise


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
    conn, update: dict, allowed: set[int], sessions: dict[int, list[dict]] | None = None
) -> tuple[int, str] | None:
    """Pure logic, no network: given one Telegram update + the allow-list, decide whether to
    answer and with what -- ``None`` if the sender isn't allowed or there's no text to answer.

    ``sessions`` (optional), keyed by chat_id, holds a bounded LIST of that conversation's last
    turns (``[{"question": ..., "answer": ...}, ...]``, oldest first, capped at
    :data:`_VERLAUF_MAX`) -- Mehr-Zug-Arbeitsgedächtnis (docs/GENUS_GEDAECHTNIS.md, Punkt 4):
    a bare follow-up ("warum?", "kürzer", "nochmal", ...) reads against the LAST turn as before;
    a "... von vorhin"/"... von eben" question can additionally reach further back
    (``companion.is_backreference``). In-process only, forgotten on a restart -- an honest,
    small limitation: this is UX-session plumbing, not knowledge, so it deliberately doesn't
    touch the ledger (Ledger != Memory). Omit ``sessions`` for the plain, stateless behaviour
    (unchanged)."""
    from genus import companion, verstehen
    import deuter
    import stimme

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
            # the OFFER of known Absichten comes from GENUS's own sown raster (the graph is
            # authoritative); before the one clean seed-apply, the module default steps in.
            # DIE GRENZE (Phase 2 der Ziel-Architektur): aus demselben lebenden Angebot wird
            # die GBNF-Grammatik abgeleitet und als Daten über die Membran gereicht -- das
            # Modell kann pro Token nur bekannte Blätter wählen, eine erfundene Kategorie
            # ist strukturell unmöglich. Wächst das Raster, wächst die Grenze mit.
            angebot = verstehen.leaf_kinds(conn) or None
            grenze = verstehen.gbnf_grammatik(angebot)
            # Deuter und Stimme haben JEWEILS ihr eigenes warmes Modell -- live gemessen
            # (2026-07-03): geteilt verwarf jeder Stimme-Aufruf den Prompt-Cache des Deuter
            # (ein anderer System-Prompt), sodass der NÄCHSTE Deuter-Aufruf seinen ganzen
            # ~1300-Token-Prompt neu verarbeiten musste -- 26s statt 3s. Kostet dauerhaft ein
            # zweites 1.5B-Modell im RAM (~1-1.5 GB, auf dem Pi reichlich frei), aber macht die
            # Latenz durchgehend vorhersagbar statt vom Zufall der Aufrufreihenfolge abzuhängen.
            zuege = sessions.get(chat_id) or []
            vorher = zuege[-1] if zuege else {}
            hinweise = _korrektur_hinweise(conn)   # Lernkreis-Rückfluss, frisch berechnet
            result = companion.respond_with_deuter(
                conn, question, vorher.get("question"),
                deuter=lambda q: deuter.interpret(q, absichten=angebot, grammatik=grenze,
                                                  korrekturen=hinweise),
                stimme=stimme.formuliere,
                last_answer=vorher.get("answer"),
                verlauf=zuege[:-1],
                letzte_lesarten=vorher.get("gelesen"),
            )
            answer = result["text"]
            # Lernkreis v1: eine angenommene Korrektur wird als Beispiel-Paar in der
            # Edge-Datei festgehalten (Text wohnt NUR an der Membran, nie im Ledger)
            ist_korrektur, richtig = companion.korrektur_cue(question)
            if ist_korrektur and vorher.get("gelesen") and vorher.get("question"):
                _merke_korrektur(vorher["question"], vorher["gelesen"], richtig)
            # "gelesen" wandert mit durch die Session (Korrektur-Kanal, Naht 1): ein
            # exaktes "falsch verstanden" im nächsten Zug weiß dann, WELCHE Lesart(en)
            # es korrigiert -- Struktur, nie der Nutzer-Text
            neuer_zug = {"question": result["question"], "answer": answer,
                         "gelesen": result.get("gelesen") or []}
            sessions[chat_id] = (zuege + [neuer_zug])[-_VERLAUF_MAX:]
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
    # Über genus.db.connect statt rohem sqlite3.connect (Phase 0 der Ziel-Architektur):
    # der Bot bekommt damit dieselben Pragmas (WAL, busy_timeout, foreign_keys) und
    # Spalten-Migrationen wie die CLI -- vorher konnte dieser Pfad sich auf einer
    # frischen oder unmigrierten DB anders verhalten als jeder andere Zugang.
    from genus import db
    conn = db.connect(DB_PATH)

    offset = _load_offset()
    sessions: dict[int, list[dict]] = {}   # chat_id -> turn list; in-process only, see handle_update
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
