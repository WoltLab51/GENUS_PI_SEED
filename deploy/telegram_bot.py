#!/usr/bin/env python3
"""Telegram bridge — a conversational membrane at the edge, nothing more.

Long-polls Telegram's Bot API (outbound HTTPS only; no inbound port, no public server needed)
and answers each allowed message with `genus.companion.respond_with_deuter` -- the
Verstehens-Würfel (Rituale -> Muster-Zellen -> offene Deuter-Lesart aufs Absichts-Raster ->
Wort-Lesart), aware of a bounded WINDOW of previous turns in the same chat (siehe
„Arbeitsgedächtnis“ in docs/design/MEMORY.md) -- a bare "warum?"/"woher weißt du das?"
retraces the last turn, and "... von vorhin"/"... von eben" can reach further back, instead of
failing (per-chat state lives here in the membrane, in-process only -- the ledger stays the
source of epistemic truth, this is UX plumbing, not knowledge).
The capped `deuter.py` edge model reads free phrasing INTO the deterministic core (an
intent/subject/object GUESS, graph-verified before anything acts). The optional `stimme.py`
model can read an ALREADY-verified answer back OUT more naturally (a faithfulness-checked
rephrase -- every quoted word/number must survive, or the original template stands). It is
disabled by default: keeping both 1.5B models warm made the bridge occupy roughly 4 GiB on the
Pi, while Stimme changes style only and the verified template is already a complete answer.
Without explicit remote consent, the required local Deuter is lazy-loaded and released after an
idle interval (90 seconds by default), so an idle bot does not permanently reserve its roughly
two GiB working set. With the private remote-consent marker, only unresolved current messages
(at most 1,000 characters; no history or ledger) are classified by GPT-4.1 Nano through GitHub
Models. Its structured guess crosses the same deterministic verification line.
Set GENUS_TELEGRAM_STIMME=1 explicitly to accept that extra memory cost (the hardened systemd
service also requires an intentional MemoryMax override). Sharing one model is not the fallback
because the two system prompts evict each other's llama.cpp prompt cache and made measured
latency jump from about 3s to 26s. Neither model ever writes the answer itself.
The core is untouched: this is a new DOOR, not a new ROOM. Strictly answer-only -- no proposal,
governance, pause/resume, or any state-changing command is reachable here, on purpose (Hände
stay parked; this is a Mundstück).

Security: a message is answered ONLY if its sender's Telegram user id is on the allow-list
(GENUS_TELEGRAM_ALLOWED_IDS). Everyone else is silently ignored (logged, not replied to, so a
stranger probing the bot learns nothing). The bot token is a real secret: read from
GENUS_TELEGRAM_BOT_TOKEN or, failing that, a file (default ~/.genus/telegram_bot_token, meant to
be chmod 600) -- never hardcoded, never logged, never committed.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import stat
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
INSTANCE_LOCK_FILE = os.environ.get(
    "GENUS_TELEGRAM_LOCK_FILE", os.path.join(GENUS_USER_HOME, ".genus", "telegram_bot.lock")
)
UA = "GENUS-PI/0.1 (personal companion bridge)"
_CTX = ssl.create_default_context()
_VERLAUF_MAX = 6   # Mehr-Zug-Arbeitsgedächtnis: wie viele Züge pro Chat im Blick bleiben
_TELEGRAM_TEXT_MAX = 4000  # eine Wahrheit für Transport UND zugestellten Session-Text
_RESTART_EXIT_CODE = 75  # EX_TEMPFAIL: Restart=on-failure startet nach einem Deploy-Flag neu

# Der Lernkreis v1 (Naht 4): korrigierte Beispiele sind MEMBRAN-Wissen -- eine Edge-Datei
# wie die Lerner-Cursor (learn.cursor, learn.gap_attempts), nie das Ledger. Der Text der
# korrigierten Frage wohnt nur hier: löschbar, nicht versiegelt, nicht Teil des Organismus.
# Das Ledger trägt weiterhin nur die Struktur (fehlgriff/fehlgriff_statt-Kanten).
KORREKTUR_DATEI = os.environ.get(
    "GENUS_KORREKTUR_DATEI", os.path.join(GENUS_USER_HOME, ".genus", "korrekturen.jsonl")
)

# Der Selbst-Neustart (Ronnys Frage 2026-07-04: „eine einfachere Möglichkeit für die
# nötigen Neustarts") -- derselbe Flag-Stil wie der Pause-Schalter, KEIN sudo: der Deploy
# berührt diese Datei, der Bot sieht sie im nächsten Poll-Zyklus (~25 s), beendet sich
# sauber mit EX_TEMPFAIL, und systemd (Restart=on-failure) startet ihn mit frischem Code.
NEUSTART_DATEI = os.environ.get(
    "GENUS_BOT_NEUSTART_DATEI",
    os.path.join(GENUS_USER_HOME, ".genus", "telegram_bot.neustart"),
)

# Der TAGESPUFFER (docs/design/MEMORY.md, „Tagesrhythmus“): pro Zug nur destillierte Struktur
# (Konzept-IDs, Lesarten, Warum-Folge), niemals Frage/Antwort/Telegram-ID. Die Nacht rotiert
# ihn atomar und fasst Tagesmuster zusammen. Ledger ≠ Memory; Datenminimierung vor Retention.
TAGESPUFFER = os.environ.get(
    "GENUS_TAGESPUFFER", os.path.join(GENUS_USER_HOME, ".genus", "chat_tag.jsonl")
)


# Die LERN-WARTESCHLANGE (Vokabel-bei-Begegnung, Ronny 2026-07-05): begegnet der Bot einem
# unbekannten Wort, landet es hier -- eine Membran-Datei wie die Lerner-Cursor, nie das Ledger.
# Der Lerner-Daemon (pi_learn.sh) holt sie beim nächsten Tick VOR den Frequenzlisten: das Wort,
# das DU gerade benutzt hast, springt an die Spitze, statt auf die Frequenzliste zu warten.
LERNWUNSCH = os.environ.get(
    "GENUS_LERNWUNSCH", os.path.join(GENUS_USER_HOME, ".genus", "lernwunsch.txt")
)
CHAT_WORD_CONSENT_FILE = os.environ.get(
    "GENUS_CHAT_WORD_CONSENT_FILE",
    os.path.join(GENUS_USER_HOME, ".genus", "chat_word_learning.enabled"),
)
CHAT_WORD_CONSENT_VALUE = "external-lexicon:definition-term"
CHAT_WORD_STATUS_FILE = os.environ.get(
    "GENUS_CHAT_WORD_STATUS_FILE",
    os.path.join(GENUS_USER_HOME, ".genus", "chat_word_learning_status.json"),
)
_LERNWUNSCH_MAX = 200   # die Schlange bleibt gedeckelt (jüngste Begegnungen zuletzt)


def _schreibe_lernwunsch(woerter: list[str]) -> str | None:
    """Unbekannt begegnete Wörter in die Lern-Warteschlange -- dedupliziert gegen die
    bestehende Schlange, gedeckelt; darf nie eine Antwort kosten (still bei jedem Fehler)."""
    tmp = None
    try:
        os.makedirs(os.path.dirname(LERNWUNSCH) or ".", exist_ok=True)
        lock_path = LERNWUNSCH + ".lock"
        with open(lock_path, "a", encoding="ascii") as lock:
            os.chmod(lock_path, 0o600)
            try:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            except ImportError:  # pragma: no cover - production is Linux
                pass
            try:
                with open(LERNWUNSCH, encoding="utf-8") as f:
                    vorhanden = [z.strip() for z in f if z.strip()]
            except FileNotFoundError:
                vorhanden = []
            neu = [w for w in woerter if w not in vorhanden]
            if not neu:
                return "existing" if woerter else None
            alle = (vorhanden + neu)[-_LERNWUNSCH_MAX:]
            tmp = LERNWUNSCH + f".tmp-{os.getpid()}"
            with open(tmp, "w", encoding="utf-8") as f:
                os.chmod(tmp, 0o600)
                f.write("\n".join(alle) + "\n")
            os.replace(tmp, LERNWUNSCH)
            tmp = None
            return "queued"
    except Exception:
        if tmp is not None:
            try:
                os.remove(tmp)
            except OSError:
                pass
    return False


def _lernkandidaten(conn, question: str) -> list[str]:
    """Nur bewusst erfragte unbekannte Einzelbegriffe duerfen die externe Lernqueue sehen.

    Freier Chat, persoenliche Aussagen, URLs, Zahlen und mehrteilige Phrasen bleiben lokal.
    Damit bedeutet das Opt-in nicht mehr "jedes grossgeschriebene Wort senden", sondern genau
    "diesen unbekannten Begriff habe ich GENUS als Definitionsfrage vorgelegt".
    """
    from genus import dialogplanung, sources

    from chat_word_learning import normalize_term

    term = normalize_term(dialogplanung.definitionsbegriff(question) or "")
    if not term or len(term) > 64 or sources.bekanntes_wort(conn, term):
        return []
    return [term]


def _schreibe_tagespuffer(conn, frage: str, gelesen: list[str]) -> None:
    """Eine rohtextfreie Tagesstruktur puffern -- nie Frage, Antwort oder Telegram-ID.

    Der separate Advisory-Lock schließt das Rennen mit der atomaren Nacht-Rotation. Auf
    Nicht-POSIX-Testsystemen bleibt der Schreibweg ohne ``fcntl`` nutzbar.
    """
    try:
        from genus import konsolidierung

        eintrag = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **konsolidierung.tagesstruktur(conn, frage, gelesen),
        }
        os.makedirs(os.path.dirname(TAGESPUFFER) or ".", exist_ok=True)
        lock_path = TAGESPUFFER + ".lock"
        with open(lock_path, "a", encoding="ascii") as lock:
            os.chmod(lock_path, 0o600)
            try:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            except ImportError:  # pragma: no cover - production is Linux
                pass
            with open(TAGESPUFFER, "a", encoding="utf-8") as f:
                os.chmod(TAGESPUFFER, 0o600)
                f.write(json.dumps(eintrag, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _neustart_angefordert(start_zeit: float) -> bool:
    """Wurde das Neustart-Flag NACH dem Start dieses Prozesses berührt? Ein älteres Flag
    (z.B. ein Überbleibsel) startet nie eine Schleife -- nur ein frisches zählt."""
    try:
        return os.path.getmtime(NEUSTART_DATEI) > start_zeit
    except OSError:
        return False


# Die MORGENZEIT-Zelle (Ronnys Entscheidung beim Push-Design: „kann ich ja jederzeit
# ändern über den chat einfach oder?"): die Push-Zeit ist MEMBRAN-Betriebskonfiguration
# (morgen_push.sh liest genau diese Datei), kein Wissen -- deshalb wohnt das Ritual hier
# in der Membran, nicht im Kern. Exakte Kommandos wie beim Chat-Regler der Persönlichkeit.
MORGENZEIT_DATEI = os.environ.get(
    "GENUS_MORGENPUSH_ZEIT", os.path.join(GENUS_USER_HOME, ".genus", "morgenpush.zeit")
)
_MORGENZEIT_STANDARD = "06:00"
_MORGENZEIT_SETZEN = re.compile(
    r"^stell den (?:morgen-?push|push|morgengruss|morgengruß) auf (\d{1,2})(?:[:.](\d{2}))?(?: uhr)?$"
)
_MORGENZEIT_FRAGE = re.compile(
    r"^wann kommt (?:der (?:morgen-?push|push)|die morgen-?nachricht)$"
)


def _morgenzeit_antwort(question: str) -> str | None:
    """Erkennt das Morgenzeit-Kommando (satzzeichen-tolerant) und stellt/nennt die
    Push-Zeit -- ``None``, wenn die Nachricht etwas anderes ist."""
    text = question.strip().strip(".!? ").casefold()
    m = _MORGENZEIT_SETZEN.match(text)
    if m:
        stunde, minute = int(m.group(1)), int(m.group(2) or 0)
        if stunde > 23 or minute > 59:
            return "Das ist keine gültige Uhrzeit — sag z.B. „stell den Push auf 6:30“."
        zeit = f"{stunde:02d}:{minute:02d}"
        os.makedirs(os.path.dirname(MORGENZEIT_DATEI), exist_ok=True)
        with open(MORGENZEIT_DATEI, "w", encoding="utf-8") as f:
            f.write(zeit)
        antwort = f"Gern — die Morgen-Nachricht kommt ab jetzt um {zeit}."
        if not 5 <= stunde <= 9:
            # ehrlich: das Cron-Fenster läuft 5-10 Uhr -- außerhalb feuert nichts
            antwort += (" Beachte: mein Morgen-Fenster läuft 5 bis 10 Uhr — "
                        "außerhalb davon kommt derzeit keine Nachricht.")
        return antwort
    if _MORGENZEIT_FRAGE.match(text):
        try:
            with open(MORGENZEIT_DATEI, encoding="utf-8") as f:
                zeit = f.read().strip() or _MORGENZEIT_STANDARD
        except FileNotFoundError:
            zeit = _MORGENZEIT_STANDARD
        return f"Die Morgen-Nachricht kommt um {zeit}."
    return None


# --- die erste HAND (P4): Erinnerungen. „erinnere mich <wann> an <was>" wird eine von Ronnys
# Wunsch aktions-genau bestätigte Hand (genus/hand.py); der Membran-Cron hand_ausfuehren.sh
# sendet sie fällig. Die ZEIT wird hier an der Membran aus der Wanduhr gerechnet; der Kern
# speichert nur den fertigen Zeitpunkt und hält das harte Gate. Reine Membran-Sache.
_ERINNERE = re.compile(r"^\s*erinner(?:e|)\s+mich\b\s*(?:bitte\s*)?", re.IGNORECASE)
_ERINN_IN = re.compile(r"\bin\s+(\d{1,3})\s*(minut|min|stund|std)\w*", re.IGNORECASE)
_ERINN_UM = re.compile(r"\bum\s+(\d{1,2})(?::(\d{2}))?\s*(?:uhr)?\b", re.IGNORECASE)


def _erinnerung(text, jetzt):
    """Parst „erinnere mich <wann> an <was>" -> ``(faellig_datetime, inhalt)`` oder ``None``.
    Ehrlich: OHNE erkennbare Zeit keine Erinnerung (nie eine Zeit raten)."""
    import datetime as _dt

    m = _ERINNERE.match(text or "")
    if not m:
        return None
    rest = text[m.end():]
    faellig = None
    d = _ERINN_IN.search(rest)
    if d:
        n = int(d.group(1))
        schritt = _dt.timedelta(minutes=n) if d.group(2).lower().startswith("min") \
            else _dt.timedelta(hours=n)
        faellig = jetzt + schritt
        rest = rest[:d.start()] + " " + rest[d.end():]
    else:
        u = _ERINN_UM.search(rest)
        if u:
            stunde, minute = int(u.group(1)), int(u.group(2) or 0)
            if stunde > 23 or minute > 59:
                return None
            faellig = jetzt.replace(hour=stunde, minute=minute, second=0, microsecond=0)
            if faellig <= jetzt:                         # heute schon vorbei -> morgen
                faellig = faellig + _dt.timedelta(days=1)
            rest = rest[:u.start()] + " " + rest[u.end():]
    if faellig is None:
        return None
    inhalt = re.sub(r"^\s*(?:,\s*)?(?:daran,?\s*dass|dass|an)\b\s*", "", rest.strip(),
                    flags=re.IGNORECASE).strip(" ,.")
    if not inhalt:
        return None
    return faellig, inhalt


def _wann_text(faellig, jetzt):
    import datetime as _dt

    if faellig.date() == jetzt.date():
        return f"heute um {faellig.strftime('%H:%M')}"
    if faellig.date() == jetzt.date() + _dt.timedelta(days=1):
        return f"morgen um {faellig.strftime('%H:%M')}"
    return f"am {faellig.strftime('%d.%m.')} um {faellig.strftime('%H:%M')}"


def _erinnerung_ritual(conn, question):
    """Membran-Ritual VOR dem Kern: eine Erinnerungs-Bitte wird zu einer bestätigten Hand.
    ``None``, wenn es keine Erinnerung ist (dann läuft die Nachricht normal weiter)."""
    import datetime as _dt

    from genus import hand

    jetzt = _dt.datetime.now()
    geparst = _erinnerung(question, jetzt)
    if geparst is None:
        return None
    faellig, inhalt = geparst
    v = hand.vorschlagen(conn, "nachricht", f"⏰ Erinnerung: {inhalt}",
                         faellig.strftime("%Y-%m-%dT%H:%M:%S"), quelle="ronny")
    if not v.get("vorgeschlagen"):
        return f"Das kann ich gerade nicht vormerken ({v.get('grund', '')})."
    hand.bestaetigen(conn, v["hand_id"])   # Ronnys ausdrücklicher Wunsch IST die aktions-genaue Freigabe
    return f"Mach ich — ich melde mich {_wann_text(faellig, jetzt)} wegen „{inhalt}“."
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
        os.chmod(KORREKTUR_DATEI, 0o600)
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


def _stimme_aktiv() -> bool:
    """Die zweite Modellkopie ist ein ausdrückliches Qualitäts-/RAM-Opt-in.

    Ohne Opt-in bleibt die bereits verifizierte, deterministische Antwort vollständig erhalten;
    nur ihre optionale sprachliche Glättung entfällt. Unbekannte Werte sind sicher AUS statt
    versehentlich einen weiteren dauerhaften 1.5B-Singleton zu laden.
    """
    return os.environ.get("GENUS_TELEGRAM_STIMME", "0").strip().casefold() in {
        "1", "true", "yes", "on", "ja",
    }


def _waage_aktiv() -> bool:
    """Die kalibrierte Modell-Waage ist im Kompaktmodus ein bewusstes RAM-Opt-in.

    Sie entscheidet nur zwischen bereits gebauten Formulierungsvarianten. Der deterministische
    Rückfall ist vollständig, während ein eigener llama.cpp-Kontext dasselbe große GGUF erneut
    mappt. Darum bleibt sie im dauerhaft laufenden Telegram-Dienst standardmäßig aus.
    """
    return os.environ.get("GENUS_TELEGRAM_WAAGE", "0").strip().casefold() in {
        "1", "true", "yes", "on", "ja",
    }


def _chat_wortlernen_aktiv() -> bool:
    """Chat-Wörter verlassen den Pi nur nach bewusstem Opt-in.

    Der Learner fragt externe Lexikonquellen ab und schreibt erworbenes Wissen ins Ledger.
    Deshalb ist die frühere automatische Queue für private Chats standardmäßig geschlossen.
    """
    if os.environ.get("GENUS_CHAT_WORD_LEARNING", "0").strip().casefold() in {
        "1", "true", "yes", "on", "ja",
    }:
        return True
    try:
        info = os.stat(CHAT_WORD_CONSENT_FILE, follow_symlinks=False)
        posix = hasattr(os, "getuid")
        owner = os.getuid() if posix else info.st_uid
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner
                or (posix and stat.S_IMODE(info.st_mode) & 0o077)):
            return False
        with open(CHAT_WORD_CONSENT_FILE, encoding="ascii") as handle:
            return handle.read().strip() == CHAT_WORD_CONSENT_VALUE
    except (OSError, UnicodeError):
        return False


def _acquire_instance_lock():
    """Exklusiven Prozess-Lock halten; ``None`` heißt: ein Poller läuft bereits.

    Telegram erlaubt je Bot-Token nur einen ``getUpdates``-Long-Poller. systemd ist der erste
    Wächter, dieser Linux-advisory-lock die letzte Barriere gegen manuell oder transient
    gestartete Doppelinstanzen. Der offene Dateideskriptor hält den Lock bis zum Prozessende;
    ein Absturz hinterlässt deshalb keinen stale PID-Lock. Auf nicht-POSIX-Testsystemen bleibt
    die Funktion importierbar, produktiv läuft die Brücke ausschließlich unter Linux/systemd.
    """
    os.makedirs(os.path.dirname(INSTANCE_LOCK_FILE) or ".", exist_ok=True)
    lock = open(INSTANCE_LOCK_FILE, "a+", encoding="ascii")
    try:
        os.chmod(INSTANCE_LOCK_FILE, 0o600)
        try:
            import fcntl
        except ImportError:  # pragma: no cover - production is Linux; keeps local Windows tests usable
            return lock
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return None
    except OSError:
        lock.close()
        raise
    return lock


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
                _log("ignoring one malformed entry in GENUS_TELEGRAM_ALLOWED_IDS")
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


def _send_message(token: str, chat_id: int, text: str) -> int | None:
    """Sendet eine Antwort und gibt nur einen belegten Telegram-``message_id`` zurück.

    Eine formal erfolgreiche HTTP-Antwort ohne ``ok`` oder ohne ganzzahlige Message-ID ist
    kein Zustellbeleg. Der Aufrufer kann dadurch fail-closed entscheiden, ob der zugehörige
    Session-Zug wirklich Gesprächswahrheit werden darf.
    """
    # Telegram caps a message at 4096 chars; a companion answer never gets close, but stay safe.
    body = _api(token, "sendMessage", {"chat_id": chat_id, "text": text[:_TELEGRAM_TEXT_MAX]}, timeout=15)
    result = body.get("result") if isinstance(body, dict) and body.get("ok") else None
    message_id = result.get("message_id") if isinstance(result, dict) else None
    return message_id if isinstance(message_id, int) and not isinstance(message_id, bool) else None


class _AntwortMelder:
    """Die „GENUS denkt …"-Statuszeile (Ronny 2026-07-09: „machts irgendwie spannender"):
    die erste Meldung wird als echte Nachricht gesendet, jede weitere Meldung und die fertige
    Antwort EDITIEREN sie (editMessageText) -- eine einzige, sich verwandelnde Nachricht statt
    Flacker-Zeilen. Ehrlich: gemeldet wird nur, was wirklich Zeit kostet (das Modell -- Deuten,
    Formulieren); die Graph-Arbeit ist Millisekunden und bekommt keine Show. FAIL-SILENT
    durchgehend: Status ist Zucker, nie Pflicht -- scheitert das Editieren, wird schlicht
    neu gesendet; scheitert die Meldung, läuft die Antwort unberührt weiter."""

    def __init__(self, token: str):
        self._token = token
        self._nachricht: dict[int, int] = {}   # chat_id -> message_id der Status-Nachricht

    def melde(self, chat_id: int, text: str) -> None:
        try:
            mid = self._nachricht.get(chat_id)
            if mid is None:
                body = _api(self._token, "sendMessage",
                            {"chat_id": chat_id, "text": text}, timeout=15)
                if body.get("ok"):
                    self._nachricht[chat_id] = body["result"]["message_id"]
            else:
                _api(self._token, "editMessageText",
                     {"chat_id": chat_id, "message_id": mid, "text": text}, timeout=15)
        except Exception:
            pass   # Status bricht nie eine Antwort

    def abschliessen(self, chat_id: int, antwort: str) -> int | None:
        """Die Status-Nachricht wird zur Antwort und liefert ihren Zustellbeleg.

        Ohne Status wird normal gesendet. Scheitert ein Edit, wird wie bisher eine neue
        Nachricht gesendet; deren ID ist dann der maßgebliche Beleg.
        """
        mid = self._nachricht.pop(chat_id, None)
        if mid is not None:
            try:
                body = _api(self._token, "editMessageText",
                            {"chat_id": chat_id, "message_id": mid,
                             "text": antwort[:_TELEGRAM_TEXT_MAX]},
                            timeout=15)
                result = body.get("result") if isinstance(body, dict) and body.get("ok") else None
                bestaetigt = result.get("message_id") if isinstance(result, dict) else None
                if (isinstance(bestaetigt, int) and not isinstance(bestaetigt, bool)
                        and bestaetigt == mid):
                    return mid
            except Exception:
                pass   # Editieren gescheitert -> ehrlich neu senden
        return _send_message(self._token, chat_id, antwort)

    def raeume_auf(self, text: str) -> None:
        """Hängengebliebene Status-Nachrichten (Absturz NACH der Meldung) ehrlich auflösen --
        nie ein ewiges „Ich denke nach …" stehen lassen."""
        for chat_id in list(self._nachricht):
            self.abschliessen(chat_id, text)


def _load_offset() -> int:
    try:
        with open(OFFSET_FILE, encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except (FileNotFoundError, ValueError):
        return 0


def _save_offset(offset: int) -> None:
    with open(OFFSET_FILE, "w", encoding="utf-8") as f:
        f.write(str(offset))


def _finalisiere_pending_zug(
    sessions: dict[int, list[dict]], pending: dict, response_id: int | None,
) -> bool:
    """Übernimmt genau einen vorbereiteten Zug erst mit belegter ``response_id``.

    Der Helfer macht keinerlei I/O. Er leert ``pending`` auf jedem Pfad, damit ein fehlender,
    ungültiger oder doppelt verwendeter Zustellbeleg nie versehentlich beim nächsten Update
    einen alten Zug bestätigt. ``True`` bedeutet: der Zug wurde in die gedeckelte Session
    übernommen; ``False`` bedeutet: fail-closed verworfen.
    """
    vorbereitet = dict(pending)
    pending.clear()
    if (not isinstance(response_id, int) or isinstance(response_id, bool)
            or response_id <= 0):
        return False
    chat_id = vorbereitet.get("chat_id")
    zug = vorbereitet.get("zug")
    if (not isinstance(chat_id, int) or isinstance(chat_id, bool)
            or not isinstance(zug, dict)):
        return False
    zuege = sessions.get(chat_id) or []
    if any(z.get("response_id") == response_id for z in zuege):
        return False
    bestaetigt = dict(zug)
    bestaetigt["response_id"] = response_id
    sessions[chat_id] = (zuege + [bestaetigt])[-_VERLAUF_MAX:]
    return True


_NEGATIVES_FEEDBACK = frozenset({
    "falsch", "das ist falsch", "das war falsch", "stimmt nicht", "das stimmt nicht",
    "das passt nicht", "passt nicht", "das ergibt keinen sinn", "ergibt keinen sinn",
    "das wirkt zufällig", "das wirkt random", "wirkt zufällig", "wirkt random",
})
_WARUM_BEGRIFF = re.compile(
    r"^\s*(?:warum|wieso|weshalb)\s+(?:denn\s+)?(.+?)\s*[?!.]*\s*$", re.IGNORECASE,
)


def _explizites_feedback(
    question: str, ziel: dict | None = None,
) -> tuple[str, str | None] | None:
    """Deutungsfreie Qualitätssignale mit eindeutigem Bezug zur vorigen Antwort."""
    from genus import companion

    ist_korrektur, richtig = companion.korrektur_cue(question)
    if ist_korrektur:
        return "intent_correction", richtig
    modifier = {chr(0xFE0F), chr(0x200D)} | {chr(c) for c in range(0x1F3FB, 0x1F400)}
    kern = "".join(ch for ch in question if not ch.isspace() and ch not in modifier)
    if kern and set(kern) == {"👍"}:
        return "positive", None
    if kern and set(kern) == {"👎"}:
        return "negative", None
    normal = question.strip().casefold().rstrip(".!?").strip()
    if normal in _NEGATIVES_FEEDBACK:
        return "negative", None
    # "Warum Therapie?" ist nur dann Feedback, wenn GENUS exakt diesen Begriff im letzten
    # Zug als Anschluss angeboten hat. Ohne den strukturellen Beleg bleibt es eine Sachfrage.
    treffer = _WARUM_BEGRIFF.match(question)
    beleg = (ziel or {}).get("anschluss_beleg") or {}
    if (treffer and beleg.get("object")
            and treffer.group(1).strip().casefold() == str(beleg["object"]).casefold()):
        return "negative", None
    return None


def _letztes_feedbackziel(zuege: list[dict]) -> dict | None:
    """Letzte echte Antwort; Acks überspringen, an Ritual-/Fehlerbarrieren stoppen."""
    for zug in reversed(zuege):
        response_id = zug.get("response_id")
        if not (isinstance(response_id, int) and not isinstance(response_id, bool)
                and response_id > 0):
            continue
        if zug.get("feedback_eligible", True):
            return zug
        if zug.get("answer_mode") != "feedback_ack":
            return None
    return None


def _bereite_outcome(
    pending: dict | None,
    chat_id: int,
    zug: dict | None,
    *,
    outcome: str,
    readings: list[str],
    answer_mode: str,
    feedback_eligible: bool,
) -> None:
    if pending is None:
        return
    pending.clear()
    pending.update({
        "chat_id": chat_id,
        "zug": zug,
        "outcome": {
            "channel": "telegram",
            "outcome": outcome,
            "readings": list(dict.fromkeys(readings)),
            "answer_mode": answer_mode,
            "feedback_eligible": feedback_eligible,
        },
    })


def _bestaetige_zustellung(
    conn,
    sessions: dict[int, list[dict]],
    pending: dict,
    message_id: int | None,
) -> int | None:
    """Persistiert Outcome und Session erst nach einem belegten Telegram-Send/Edit.

    ``message_id`` beweist die Zustellung nur an dieser flüchtigen Kante und wird weder im
    Ledger noch in der Projektion gespeichert.
    """
    if (not isinstance(message_id, int) or isinstance(message_id, bool)
            or message_id <= 0):
        pending.clear()
        return None
    outcome = pending.get("outcome")
    if not isinstance(outcome, dict):
        pending.clear()
        return None
    from genus import response_outcomes

    try:
        response_id = response_outcomes.record_outcome(conn, **outcome)
    except Exception:
        pending.clear()
        raise
    if pending.get("zug") is None:
        pending.clear()
        return response_id
    if not _finalisiere_pending_zug(sessions, pending, response_id):
        return None
    return response_id


def handle_update(
    conn, update: dict, allowed: set[int], sessions: dict[int, list[dict]] | None = None,
    status=None, pending: dict | None = None, deuter_reader=None,
) -> tuple[int, str] | None:
    """Pure logic, no network: given one Telegram update + the allow-list, decide whether to
    answer and with what -- ``None`` if the sender isn't allowed or there's no text to answer.

    ``sessions`` (optional), keyed by chat_id, holds a bounded LIST of that conversation's last
    turns (``[{"question": ..., "answer": ...}, ...]``, oldest first, capped at
    :data:`_VERLAUF_MAX`) -- Mehr-Zug-Arbeitsgedächtnis (docs/design/MEMORY.md):
    a bare follow-up ("warum?", "kürzer", "nochmal", ...) reads against the LAST turn as before;
    a "... von vorhin"/"... von eben" question can additionally reach further back
    (``companion.is_backreference``). In-process only, forgotten on a restart -- an honest,
    small limitation: this is UX-session plumbing, not knowledge, so it deliberately doesn't
    touch the ledger (Ledger != Memory). Omit ``sessions`` for the plain, stateless behaviour
    (unchanged).

    ``status`` (optional): ein injizierter Callback ``status(chat_id, text)`` -- dasselbe
    Muster wie ``deuter``/``stimme``: OHNE ihn bleibt diese Funktion pur (kein Netz, testbar
    wie bisher); MIT ihm meldet sie ehrlich die zwei Phasen, die wirklich Zeit kosten
    (Deuten, Formulieren -- beides Modell; die Graph-Arbeit ist ms und bekommt keine Show).

    ``pending`` (optional) hält den neu erzeugten Session-Zug zunächst zurück. Der Aufrufer
    bestätigt ihn nach erfolgreichem Transport über :func:`_finalisiere_pending_zug` mit der
    transportneutralen Response-ID. Ohne ``pending`` bleibt das bisherige sofortige
    Session-Verhalten vollständig kompatibel."""
    from genus import companion, verstehen
    import deuter
    import waage

    if pending is not None:
        pending.clear()   # ein ignoriertes/fehlgeschlagenes Update darf nie einen alten Zug erben
    message = update.get("message") or update.get("edited_message")
    if not message or "text" not in message:
        return None
    sender = message.get("from", {}).get("id")
    chat_id = message.get("chat", {}).get("id")
    if sender is None or chat_id is None:
        return None
    if sender not in allowed:
        _log("ignored one message from an unauthorized sender")
        return None
    if chat_id != sender:
        _log("ignored one message outside the owner's private chat")
        return None
    question = message["text"]
    _log(f"accepted text message (characters={len(question)})")
    try:
        # Membran-Ritual VOR dem Kern: die Morgenzeit ist Betriebskonfiguration dieser
        # Membran (Datei, die morgen_push.sh liest), kein Wissen -- der Kern sieht sie nie.
        morgen = _morgenzeit_antwort(question)
        if morgen is not None:
            _bereite_outcome(
                pending, chat_id,
                {"feedback_eligible": False, "answer_mode": "edge_ritual"},
                outcome="answered", readings=[],
                answer_mode="edge_ritual", feedback_eligible=False,
            )
            return chat_id, morgen
        # die erste HAND: „erinnere mich …" wird eine bestätigte Hand (der Cron sendet sie fällig).
        # Auch ein Membran-Ritual vor dem Kern; der Kern hält das Gate, die Membran sendet später.
        # WICHTIG: INNERHALB dieses Wächters — das Ritual SCHREIBT ins Ledger; ein vorübergehender
        # Lock beim HANDELN darf nie das REDEN töten (sonst Neustart-Schleife, weil der Offset erst
        # nach handle_update gespeichert wird). Der Kern rollt die Transaktion sauber zurück.
        erinnerung = _erinnerung_ritual(conn, question)
        if erinnerung is not None:
            _bereite_outcome(
                pending, chat_id,
                {"feedback_eligible": False, "answer_mode": "edge_ritual"},
                outcome="answered", readings=[],
                answer_mode="edge_ritual", feedback_eligible=False,
            )
            return chat_id, erinnerung
        artikel_organ = waage.artikel_organ() if _waage_aktiv() else None
        if sessions is None:
            answer = companion.respond(conn, question, waage=artikel_organ)
        else:
            # the OFFER of known Absichten comes from GENUS's own sown raster (the graph is
            # authoritative); before the one clean seed-apply, the module default steps in.
            # DIE GRENZE (Phase 2 der Ziel-Architektur): aus demselben lebenden Angebot wird
            # die GBNF-Grammatik abgeleitet und als Daten über die Membran gereicht -- das
            # Modell kann pro Token nur bekannte Blätter wählen, eine erfundene Kategorie
            # ist strukturell unmöglich. Wächst das Raster, wächst die Grenze mit.
            angebot = verstehen.leaf_kinds(conn) or None
            grenze = verstehen.gbnf_grammatik(angebot)
            # Der Deuter bleibt nur bis zum Idle-Release warm. Die Stimme ist ein ausdrückliches
            # Opt-in: ihr zweiter 1.5B-Singleton machte aus dem Bot live einen ~4-GiB-Prozess,
            # obwohl ohne sie dieselbe verifizierte Template-Antwort vollständig erhalten bleibt.
            # Ein Modell zu teilen wäre keine robuste Sparvariante: die verschiedenen Prompts
            # verdrängen den Cache und machten den nächsten Deuter-Aufruf gemessen 26s langsam.
            zuege = sessions.get(chat_id) or []
            vorher = zuege[-1] if zuege else {}
            moegliches_feedbackziel = _letztes_feedbackziel(zuege)
            explizites_feedback = _explizites_feedback(question, moegliches_feedbackziel)
            feedback_ziel = moegliches_feedbackziel if explizites_feedback is not None else None
            # Eine Bestätigungs-Antwort ist selbst absichtlich nicht feedbackfähig. Folgt
            # darauf noch eine Korrektur oder reine 👍/👎-Gebärde, bleibt deshalb die
            # letzte echte Antwort der Bezug — nicht der Ack. Das ist nur flüchtiger Dialogkontext;
            # ins Ledger gelangt später ausschließlich dessen transportneutrale response_id.
            bezug = feedback_ziel or vorher
            hinweise = _korrektur_hinweise(conn)   # Lernkreis-Rückfluss, frisch berechnet
            if deuter_reader is None:
                deute = lambda q: deuter.interpret(
                    q, absichten=angebot, grammatik=grenze, korrekturen=hinweise,
                )
            else:
                # Remote-minimal bekommt nur den aktuellen Zug, das Raster-Angebot und maximal
                # vier rein strukturelle Intent-Verwechslungen. Verlauf, Beispieltexte,
                # Korrekturdatei und GBNF-Implementierungsdetails bleiben auf dem Pi.
                def deute(q):
                    try:
                        strukturell = [
                            {"gelesen": h.get("gelesen"), "gemeint": h.get("gemeint")}
                            for h in hinweise
                            if h.get("gelesen") and h.get("gemeint")
                        ][:_HINWEIS_BEISPIELE]
                        return deuter_reader(
                            q, absichten=angebot, korrekturen=strukturell,
                        )
                    except (RuntimeError, ValueError) as exc:
                        _log(f"remote Deuter fell back to local core ({type(exc).__name__})")
                        return None
            sprich = None
            if status is not None:
                status(chat_id, "🤔 Ich denke nach …")   # gleich ruft der Deuter (Sekunden)
            if _stimme_aktiv():
                import stimme
                sprich = stimme.formuliere
                if status is not None:
                    def sprich(text, **kw):   # die zweite ehrliche Modell-Phase: Formulieren
                        status(chat_id, "✍️ Ich formuliere …")
                        return stimme.formuliere(text, **kw)
            from genus import antwort as antwort_wuerfel

            result = companion.respond_with_deuter(
                conn, question, bezug.get("question"),
                deuter=deute,
                stimme=sprich,
                last_answer=bezug.get("answer"),
                verlauf=zuege[:-1],
                letzte_lesarten=bezug.get("gelesen"),
                letzter_anschluss=bezug.get("anschluss"),
                letzter_anschluss_beleg=bezug.get("anschluss_beleg"),
                # das Wiege-Organ der Formwahl-Kette: liest nur, handelt nur über seiner
                # Blind-Proben-Schwelle; ohne Kalibrierung (~/.genus/waage_kalibrierung.json)
                # ist es None und die Kette bleibt rein deterministisch
                waage=artikel_organ,
                renderer=antwort_wuerfel.rendere,
                previous_response_id=bezug.get("response_id"),
            )
            answer = result["text"][:_TELEGRAM_TEXT_MAX]
            if explizites_feedback is not None and feedback_ziel is not None:
                from genus import response_outcomes

                signal, corrected_intent = explizites_feedback
                bekannte_absichten = set(
                    angebot or (leaf for leaf, _ in verstehen.RASTER_SEED)
                )
                if corrected_intent not in bekannte_absichten:
                    corrected_intent = None
                feedback_gespeichert = False
                try:
                    response_outcomes.record_feedback(
                        conn,
                        response_id=feedback_ziel["response_id"],
                        signal=signal,
                        corrected_intent=corrected_intent,
                    )
                    feedback_gespeichert = True
                except Exception as exc:
                    # Feedback ist ein nachgelagerter Messpunkt, niemals der Preis der Antwort.
                    # Der Fehler bleibt ohne Rohtext im Journal sichtbar; der Ack darf trotzdem
                    # zugestellt werden und wird selbst nicht feedbackfähig.
                    _log(f"explicit feedback could not be recorded ({type(exc).__name__})")
                if feedback_gespeichert and signal == "negative":
                    answer = ("Verstanden — ich habe die vorige Antwort als unpassend markiert. "
                              "Wenn du mir die gemeinte Lesart nennst, kann ich auch den "
                              "konkreten Fehlgriff lernen.")
            # Lernkreis v1: eine angenommene Korrektur wird als Beispiel-Paar in der
            # Edge-Datei festgehalten (Text wohnt NUR an der Membran, nie im Ledger)
            ist_korrektur, richtig = companion.korrektur_cue(question)
            if ist_korrektur and bezug.get("gelesen") and bezug.get("question"):
                _merke_korrektur(bezug["question"], bezug["gelesen"], richtig)
            # "gelesen" wandert mit durch die Session (Korrektur-Kanal, Naht 1): ein
            # exaktes "falsch verstanden" im nächsten Zug weiß dann, WELCHE Lesart(en)
            # es korrigiert -- Struktur, nie der Nutzer-Text
            # "anschluss" wandert mit durch die Session (Antizipation): ein "ja" im nächsten
            # Zug löst das im letzten Zug gemachte, verifizierte Anschluss-Angebot ein
            feedback_ack = explizites_feedback is not None
            answer_mode = (
                "feedback_ack" if feedback_ack
                else "voice" if companion._STIMME_TAG in answer
                else "core"
            )
            neuer_zug = {"question": result["question"], "answer": answer,
                         "gelesen": result.get("gelesen") or [],
                         "anschluss": result.get("anschluss"),
                         "anschluss_beleg": result.get("anschluss_beleg"),
                         "feedback_eligible": not feedback_ack,
                         "answer_mode": answer_mode}
            if pending is None:
                sessions[chat_id] = (zuege + [neuer_zug])[-_VERLAUF_MAX:]
            else:
                _bereite_outcome(
                    pending, chat_id, neuer_zug,
                    outcome=result.get("outcome", "answered"),
                    readings=result.get("gelesen") or [],
                    answer_mode=answer_mode,
                    feedback_eligible=not feedback_ack,
                )
            _schreibe_tagespuffer(conn, question, result.get("gelesen") or [])
    except Exception as exc:  # a bug in answering must never take the bridge down
        _log(f"error answering message ({type(exc).__name__})")
        answer = "Da ist etwas schiefgelaufen — GENUS konnte diese Frage gerade nicht beantworten."
        _bereite_outcome(
            pending, chat_id, {"feedback_eligible": False, "answer_mode": "error"},
            outcome="fallback", readings=[],
            answer_mode="error", feedback_eligible=False,
        )
    # Kontrolliertes Begriffslernen: nur der unbekannte Einzelbegriff einer ausdruecklichen
    # Definitionsfrage geht in die externe Queue. Nach der Antwort, nie sie kostend.
    if _chat_wortlernen_aktiv():
        try:
            begegnet = _lernkandidaten(conn, question)
            if begegnet:
                from chat_word_learning import get_status, mark

                begriff = begegnet[0]
                status = get_status(begriff, path=CHAT_WORD_STATUS_FILE)
                if status in {"queued", "learning"}:
                    answer = f"Ich lerne »{begriff}« gerade noch. Frag mich gleich noch einmal."
                elif status == "failed":
                    answer = (f"Ich konnte »{begriff}« in meinen freigegebenen Quellen noch "
                              "nicht sicher erschließen. Nenn mir gern den Kontext oder versuch "
                              "es später noch einmal.")
                else:
                    queue_status = _schreibe_lernwunsch(begegnet)
                    if queue_status:
                        mark(begriff, "queued", path=CHAT_WORD_STATUS_FILE)
                        if queue_status == "queued":
                            answer = (f"»{begriff}« kenne ich noch nicht sicher. Ich schlage den "
                                      "Begriff jetzt in meinen freigegebenen Quellen nach. Frag "
                                      "mich gleich noch einmal.")
                        else:
                            answer = (f"Ich lerne »{begriff}« gerade noch. Frag mich gleich "
                                      "noch einmal.")
                if pending is not None and pending.get("zug") is not None:
                    pending["zug"]["answer"] = answer
                elif sessions is not None and sessions.get(chat_id):
                    sessions[chat_id][-1]["answer"] = answer
        except Exception:
            pass
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
    if len(allowed) != 1:
        _log("GENUS requires exactly one Telegram owner until personal memories are isolated")
        return 1

    os.makedirs(LOG_DIR, exist_ok=True)
    # Telegram beantwortet getUpdates mit HTTP 409, sobald derselbe Token parallel gepollt
    # wird. Vor DB und Netzwerk genau EINE Prozessinstanz zulassen; der offene Handle bleibt
    # absichtlich bis zum Ende dieses main()-Frames referenziert.
    _instance_lock = _acquire_instance_lock()
    if _instance_lock is None:
        _log("another telegram bridge instance already owns the poll lock — stopping")
        return 0
    remote_reader = None
    try:
        import remote_deuter
        remote_reader = remote_deuter.from_environment(reporter=_log)
    except (RuntimeError, ValueError, OSError) as exc:
        _log(f"remote Deuter disabled ({type(exc).__name__})")
    remote_label = remote_reader.model if remote_reader is not None else "off"
    _log(
        f"telegram bridge started — one private owner, Stimme={'on' if _stimme_aktiv() else 'off'}, "
        f"Waage={'on' if _waage_aktiv() else 'off'}, "
        f"Remote-Deuter={remote_label}, "
        f"Chat-Wortlernen={'on' if _chat_wortlernen_aktiv() else 'off'}"
    )

    # Über genus.db.connect statt rohem sqlite3.connect (Phase 0 der Ziel-Architektur):
    # der Bot bekommt damit dieselben Pragmas (WAL, busy_timeout, foreign_keys) und
    # Spalten-Migrationen wie die CLI -- vorher konnte dieser Pfad sich auf einer
    # frischen oder unmigrierten DB anders verhalten als jeder andere Zugang.
    from genus import db
    conn = db.connect(DB_PATH)
    import deuter

    offset = _load_offset()
    start_zeit = time.time()
    sessions: dict[int, list[dict]] = {}   # chat_id -> turn list; in-process only, see handle_update
    pending: dict = {}                     # genau ein noch nicht zugestellter Antwort-Zug
    melder = _AntwortMelder(token)          # die „GENUS denkt …"-Statuszeile (fail-silent)
    while True:
        if _neustart_angefordert(start_zeit):
            _log("Neustart angefordert (Deploy-Flag) — beende mich sauber; "
                 "systemd bringt den frischen Code zurück")
            try:
                os.remove(NEUSTART_DATEI)
            except OSError:
                pass
            return _RESTART_EXIT_CODE
        try:
            updates = _get_updates(token, offset)
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                # Ein älterer/unverwalteter Poller ohne unseren Lock kann während eines
                # Rolling-Deploys noch leben. Nicht mit endlosen Requests dagegen anrennen:
                # sauber stoppen; der Watchdog versucht die verwaltete Unit später erneut.
                _log("getUpdates conflict (HTTP 409) — another poller owns this token; stopping")
                return 0
            _log(f"getUpdates failed (HTTP {exc.code}) — retrying shortly")
            time.sleep(5)
            continue
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            _log(f"getUpdates failed ({type(exc).__name__}) — retrying shortly")
            time.sleep(5)
            continue
        if deuter.release_if_idle():
            _log("compact mode released the idle local Deuter model")
        for update in updates:
            offset = max(offset, update["update_id"] + 1)
            # Letzter Wächter: KEINE einzelne Nachricht darf die Brücke töten ODER den Offset
            # einfrieren. handle_update fängt seine eigenen Fehler schon graziös ab; sollte
            # dennoch je etwas durchschlagen, wird der Offset trotzdem gespeichert (unten) —
            # kein erneutes Zustellen derselben Nachricht, keine Neustart-Schleife.
            try:
                result = handle_update(
                    conn, update, allowed, sessions, status=melder.melde, pending=pending,
                    deuter_reader=(remote_reader.interpret if remote_reader is not None else None),
                )
            except Exception as exc:
                _log(f"handle_update crashed ({type(exc).__name__})")
                result = None
                pending.clear()
                # nie ein ewiges „Ich denke nach …" stehen lassen
                melder.raeume_auf("Da ist etwas schiefgelaufen — magst du es nochmal versuchen?")
            if result is not None:
                chat_id, answer = result
                try:
                    message_id = melder.abschliessen(
                        chat_id, answer,
                    )   # Status-Nachricht WIRD die Antwort
                    response_id = _bestaetige_zustellung(
                        conn, sessions, pending, message_id,
                    )
                    if message_id is None:
                        _log("answer transport returned no delivery receipt; outcome discarded")
                    elif response_id is None:
                        _log("delivered answer could not be linked to a response outcome")
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    pending.clear()
                    _log(f"sendMessage failed ({type(exc).__name__})")
                except Exception as exc:
                    pending.clear()
                    _log(f"response outcome could not be persisted ({type(exc).__name__})")
            _save_offset(offset)


if __name__ == "__main__":
    sys.exit(main())
