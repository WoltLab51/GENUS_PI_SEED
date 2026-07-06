#!/usr/bin/env python3
"""Backfill der DYNAMISCHEN Schicht (Ronny 2026-07-06: „mach das Backfill").

Der Ernter deploy/observe_konzept.sh holt EIN Konzept je Aufruf (ein API-Call + ein Python-
Prozess je Kante) — für die ~12k Konzepte des lebenden Graphen zu teuer. Dieser Backfill
BÜNDELT: ``wbgetentities`` holt bis zu 50 Konzepte je Call (props=claims), extrahiert die
verbindende dynamische Schicht (part_of/has_part/made_of/used_for/causes/caused_by), holt die
Objekt-Labels gebündelt nach und sät ALLES über EINEN Prozess mit ``reactors.sae_fehlende``
(idempotent, dieselbe Schreib-Naht wie überall). Read-only gegenüber Wikidata, höflich
rate-limited, RESUMIERBAR über eine Fortschrittsdatei — ein Absturz bei 8k setzt bei 8k fort.

is_a (P279) sät der Backfill NICHT: die Taxonomie baut der Kletter-Lerner schon dicht; die
FEHLENDE Schicht ist das Verbindende (Teil-Ganzes, Zweck, Kausal) — genau der Rohstoff, nach dem
die Hypothese-/Deduktions-Denkweisen hungern (Methoden-Landkarte 2026-07-05).

Off-Pi testbar: ``--dry-run`` schreibt nichts, ``--ids Q11442,Q726`` erntet genau diese (statt
aus dem Ledger zu lesen) — so lässt sich die Extraktion gegen echtes Wikidata prüfen, ohne den
Organismus anzufassen.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://www.wikidata.org/w/api.php"
UA = "GENUS-PI/0.1 (epistemic core research; ronnywolter87@gmail.com)"
# Wikidata-Property -> GENUS-Prädikat. Bewusst OHNE P279/is_a (die Leiter ist schon dicht).
PROP_MAP = {"P361": "part_of", "P527": "has_part", "P186": "made_of",
            "P366": "used_for", "P1542": "causes", "P828": "caused_by"}
LANGS = ("de", "en", "fr")
BATCH = 50            # wbgetentities nimmt bis zu 50 Ids je Call
PAUSE = 0.6           # höflich gegen die öffentliche API
SOURCE = "wikidata"


def _hole(params: dict, tries: int = 3):
    """Ein wbgetentities-Call, mit ein paar höflichen Wiederholungen. None bei anhaltendem Fehler."""
    url = API + "?" + urllib.parse.urlencode(params) + "&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if i == tries - 1:
                return None
            time.sleep(2 * (i + 1))
    return None


def extrahiere_kanten(entities: dict) -> tuple[list[tuple[str, str, str]], set[str]]:
    """Aus einer wbgetentities-Antwort (props=claims) die dynamischen (subject, praedikat, object)-
    Tripel + die Menge der Objekt-Q-ids. REINE Funktion (testbar, kein I/O)."""
    tripel: list[tuple[str, str, str]] = []
    objids: set[str] = set()
    for qid, ent in entities.items():
        claims = ent.get("claims", {})
        for pid, pred in PROP_MAP.items():
            for c in claims.get(pid, []):
                dv = c.get("mainsnak", {}).get("datavalue")
                if not (dv and isinstance(dv.get("value"), dict)):
                    continue
                obj = dv["value"].get("id")
                # nur echte Item-Ziele (Q…), nie eine Property/ein Lexem; nie ein Selbst-Loop
                # (X part_of X ist nie legitim und wäre ein sofortiger Azyklizitäts-Widerspruch)
                if not obj or not obj.startswith("Q") or obj == qid:
                    continue
                tripel.append((qid, pred, obj))
                objids.add(obj)
    return tripel, objids


def extrahiere_labels(entities: dict) -> list[tuple[str, str, str]]:
    """label/expresses-Tripel für Objekt-Konzepte — eine Sprache genügt zum Benennen (Vorzug
    de>en>fr), sonst blieben die dynamischen Ziele kryptische Q-ids (aus jeder Antwort gefiltert).
    REINE Funktion."""
    out: list[tuple[str, str, str]] = []
    for q, e in entities.items():
        labels = e.get("labels", {})
        for lg in LANGS:
            v = labels.get(lg, {}).get("value")
            if v and "\t" not in v and "@" not in v:
                out += [(f"{v}@{lg}", "label", q), (f"{v}@{lg}", "expresses", q)]
                break
    return out


def _batches(xs: list, n: int):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def _ziel_qids(conn) -> list[str]:
    """Alle Q-id-Konzepte, die als Subjekt im Graphen stehen (die möglichen Analogie-Anker)."""
    rows = conn.execute("SELECT DISTINCT subject FROM relation_projection "
                        "WHERE subject GLOB 'Q[0-9]*' ORDER BY subject").fetchall()
    return [r["subject"] for r in rows]


def _schon_gelabelt(conn) -> set[str]:
    """Q-ids, die schon einen Namen tragen (Objekt einer label-Kante) — die überspringt Phase 2."""
    rows = conn.execute("SELECT DISTINCT object FROM relation_projection WHERE predicate='label'").fetchall()
    return {r["object"] for r in rows}


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill der dynamischen Schicht aus Wikidata")
    ap.add_argument("--dry-run", action="store_true", help="nichts schreiben, nur zählen/zeigen")
    ap.add_argument("--limit", type=int, default=0, help="höchstens N Konzepte (0 = alle)")
    ap.add_argument("--ids", default="", help="genau diese Q-ids (Komma), statt aus dem Ledger")
    ap.add_argument("--skip-labels", action="store_true", help="Phase 2 (Objekt-Labels) auslassen")
    ap.add_argument("--resume-file", default="", help="Fortschrittsdatei (Default: neben dem Ledger)")
    args = ap.parse_args()

    if args.ids and not args.dry_run:
        ap.error("--ids ist nur für den Off-Pi-Test mit --dry-run vorgesehen (kein Ledger).")

    conn = None
    if args.ids:
        ziele = [q.strip() for q in args.ids.split(",") if q.strip()]
        gelabelt: set[str] = set()
    else:
        from genus import cli
        conn = cli.get_conn()
        ziele = _ziel_qids(conn)
        gelabelt = _schon_gelabelt(conn)

    resume = Path(args.resume_file) if args.resume_file else None
    if resume is None and conn is not None:
        resume = Path(conn.execute("PRAGMA database_list").fetchone()["file"] or ".").parent / "backfill_konzepte.done"
    fertig: set[str] = set()
    if resume and resume.exists():
        fertig = set(resume.read_text(encoding="utf-8").split())
    if fertig:
        ziele = [q for q in ziele if q not in fertig]
    if args.limit:
        ziele = ziele[:args.limit]

    print(f"[BF] {len(ziele)} Konzepte zu ernten"
          f"{' (dry-run)' if args.dry_run else ''}"
          f"{f', {len(fertig)} schon fertig' if fertig else ''}", file=sys.stderr)

    def saee(tripel) -> tuple[int, int]:
        """Sät die Tripel (idempotent, source=wikidata). Eine ``part_of``-Kante, die einen Ring
        schlösse, wird NICHT importiert: part_of ist transitiv, ein Ring in Wikidatas Fremd-Daten
        ist ein Quellen-Problem, kein Denkfehler von GENUS — ihn über observe_relation als eigenen
        Selbst-Widerspruch (Inquiry) zu protokollieren würde die Introspektion mit Rauschen fluten.
        So bleibt die Teil-Ganzes-Hierarchie azyklisch. Gibt (neu gesät, ring-übersprungen) zurück."""
        if not tripel:
            return 0, 0
        if args.dry_run:
            return len(tripel), 0
        from genus import reactors, inference
        neu, uebersprungen, rest = 0, 0, []
        for s, p, o in tripel:
            if p == "part_of":
                if inference.closes_cycle(conn, s, p, o):
                    uebersprungen += 1
                else:                               # einzeln säen, damit der nächste Ring-Check
                    neu += reactors.sae_fehlende(conn, [(s, p, o)], SOURCE)   # diese Kante schon sieht
            else:
                rest.append((s, p, o))
        if rest:
            neu += reactors.sae_fehlende(conn, rest, SOURCE)
        return neu, uebersprungen

    kanten_neu, konzepte_mit, ringe = 0, 0, 0
    alle_objids: set[str] = set()
    verarbeitet: list[str] = []
    for batch in _batches(ziele, BATCH):
        data = _hole({"action": "wbgetentities", "ids": "|".join(batch), "props": "claims"})
        if data is None:
            print(f"[BF] Batch fehlgeschlagen ({batch[0]}…) — übersprungen, wird beim nächsten Lauf erneut versucht",
                  file=sys.stderr)
            time.sleep(PAUSE)
            continue
        tripel, objids = extrahiere_kanten(data.get("entities", {}))
        neu, uebersprungen = saee(tripel)
        kanten_neu += neu
        ringe += uebersprungen
        konzepte_mit += len({s for s, _, _ in tripel})
        alle_objids |= objids
        verarbeitet += batch
        if resume and not args.dry_run:                      # Fortschritt sofort festhalten (resumierbar)
            with resume.open("a", encoding="utf-8") as f:
                f.write("\n".join(batch) + "\n")
        if args.dry_run:
            for s, p, o in tripel[:12]:
                print(f"    {s} {p} {o}")
        time.sleep(PAUSE)

    print(f"[BF] Phase 1: {kanten_neu} dynamische Kanten aus {len(verarbeitet)} Konzepten "
          f"({konzepte_mit} trugen welche); {ringe} part_of-Ringe nicht importiert (Azyklizität)",
          file=sys.stderr)

    if args.skip_labels:
        return 0
    zu_labeln = sorted(alle_objids - gelabelt)
    print(f"[BF] Phase 2: {len(zu_labeln)} Objekt-Konzepte zu benennen", file=sys.stderr)
    labels_neu = 0
    for batch in _batches(zu_labeln, BATCH):
        data = _hole({"action": "wbgetentities", "ids": "|".join(batch),
                      "props": "labels", "languages": "|".join(LANGS)})
        if data is None:
            time.sleep(PAUSE)
            continue
        lbls = extrahiere_labels(data.get("entities", {}))
        neu, _ = saee(lbls)
        labels_neu += neu
        if args.dry_run:
            for s, p, o in lbls[:8]:
                print(f"    {s} {p} {o}")
        time.sleep(PAUSE)
    print(f"[BF] Phase 2: {labels_neu} Label-Kanten gesät", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
