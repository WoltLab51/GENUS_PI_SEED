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

Zwei Modi: der Default erntet die bestehenden Q-id-SUBJEKTE (dynamische Schicht, is_a hat der
Kletter-Lerner). ``--tiefung`` erntet die INSELN — Q-ids, die erst durch den Backfill als Objekt
auftauchten und noch kein Subjekt sind — und nimmt dabei is_a HINZU, um sie in der Hierarchie zu
platzieren (der Kletterer erreicht sie nicht). Getrennte Fortschrittsdateien je Modus.

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
# Wikidata-Property -> GENUS-Prädikat. Für die bestehenden Subjekte OHNE P279/is_a (die Leiter
# ist dort schon dicht, der Kletter-Lerner baut sie). Die TIEFUNG neuer Objekt-Konzepte nimmt is_a
# HINZU (PROP_MAP_TIEFUNG): eine Insel (nur als Objekt aufgetaucht, nie als Subjekt) erreicht der
# Kletterer nicht (er klettert is_a-Objekte, keine dynamischen Objekte) -- sie braucht ihr is_a
# hier, sonst bleibt sie ohne Platz in der Hierarchie und ohne Geschwister (kein Analogie-Anker).
PROP_MAP = {"P361": "part_of", "P527": "has_part", "P186": "made_of",
            "P366": "used_for", "P1542": "causes", "P828": "caused_by"}
PROP_MAP_TIEFUNG = {"P279": "is_a", **PROP_MAP}
# die transitiven Prädikate: eine importierte Kante, die einen Ring schlösse, wird NICHT gesät
# (Azyklizität; ein Fremd-Zyklus ist ein Quellen-Problem, kein Selbst-Widerspruch von GENUS).
ZYKLUS_PRAEDIKATE = ("is_a", "part_of")
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


def extrahiere_kanten(entities: dict, prop_map: dict | None = None
                      ) -> tuple[list[tuple[str, str, str]], set[str]]:
    """Aus einer wbgetentities-Antwort (props=claims) die (subject, praedikat, object)-Tripel für
    ``prop_map`` (Default: die dynamische Schicht; die Tiefung reicht PROP_MAP_TIEFUNG mit is_a)
    + die Menge der Objekt-Q-ids. REINE Funktion (testbar, kein I/O)."""
    prop_map = prop_map or PROP_MAP
    tripel: list[tuple[str, str, str]] = []
    objids: set[str] = set()
    for qid, ent in entities.items():
        claims = ent.get("claims", {})
        for pid, pred in prop_map.items():
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


_DYN = ("part_of", "has_part", "made_of", "used_for", "causes", "caused_by")


def _ziel_qids(conn) -> list[str]:
    """Alle Q-id-Konzepte, die als Subjekt im Graphen stehen (die möglichen Analogie-Anker)."""
    rows = conn.execute("SELECT DISTINCT subject FROM relation_projection "
                        "WHERE subject GLOB 'Q[0-9]*' ORDER BY subject").fetchall()
    return [r["subject"] for r in rows]


def _insel_qids(conn) -> list[str]:
    """Die TIEFUNGS-Ziele: Q-ids, die als OBJEKT einer dynamischen Kante auftauchen, aber noch
    KEIN Subjekt sind (Inseln — benannt, aber ohne is_a/Geschwister/eigene Kanten). Genau die, die
    der Kletter-Lerner nicht erreicht (er klettert is_a-Objekte, keine dynamischen Objekte)."""
    ph = ",".join("?" for _ in _DYN)
    rows = conn.execute(
        f"SELECT DISTINCT object FROM relation_projection "
        f"WHERE predicate IN ({ph}) AND object GLOB 'Q[0-9]*' "
        f"AND object NOT IN (SELECT subject FROM relation_projection WHERE subject GLOB 'Q[0-9]*') "
        f"ORDER BY object", _DYN).fetchall()
    return [r["object"] for r in rows]


def _schon_gelabelt(conn) -> set[str]:
    """Q-ids, die schon einen Namen tragen (Objekt einer label-Kante) — die überspringt Phase 2."""
    rows = conn.execute("SELECT DISTINCT object FROM relation_projection WHERE predicate='label'").fetchall()
    return {r["object"] for r in rows}


def _saee(conn, tripel, dry_run: bool) -> tuple[int, int]:
    """Sät die Tripel (idempotent, source=wikidata). Eine transitive Kante (is_a/part_of), die
    einen Ring schlösse, wird NICHT importiert: ein Ring in Wikidatas Fremd-Daten ist ein
    Quellen-Problem, kein Denkfehler von GENUS — ihn über observe_relation als eigenen
    Selbst-Widerspruch (Inquiry) zu protokollieren würde die Introspektion mit Rauschen fluten.
    So bleiben is_a und part_of azyklisch. Gibt (neu gesät, ring-übersprungen) zurück."""
    if not tripel:
        return 0, 0
    if dry_run:
        return len(tripel), 0
    from genus import reactors, inference
    neu, uebersprungen, rest = 0, 0, []
    for s, p, o in tripel:
        if p in ZYKLUS_PRAEDIKATE:                  # is_a UND part_of sind transitiv
            if inference.closes_cycle(conn, s, p, o):
                uebersprungen += 1
            else:                                   # einzeln säen, damit der nächste Ring-Check
                neu += reactors.sae_fehlende(conn, [(s, p, o)], SOURCE)   # diese Kante schon sieht
        else:
            rest.append((s, p, o))
    if rest:
        neu += reactors.sae_fehlende(conn, rest, SOURCE)
    return neu, uebersprungen


def _ernte(conn, ziele, prop_map, gelabelt, resume, dry_run, skip_labels) -> tuple[int, int, int]:
    """Eine Ernte-Runde über ``ziele``: Phase 1 (Kanten) + Phase 2 (Objekt-Labels). Schreibt den
    Fortschritt fortlaufend in ``resume`` (resumierbar) und aktualisiert ``gelabelt`` in-place.
    Gibt (kanten_neu, ringe, labels_neu) zurück."""
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
        tripel, objids = extrahiere_kanten(data.get("entities", {}), prop_map)
        neu, uebersprungen = _saee(conn, tripel, dry_run)
        kanten_neu += neu
        ringe += uebersprungen
        konzepte_mit += len({s for s, _, _ in tripel})
        alle_objids |= objids
        verarbeitet += batch
        if resume and not dry_run:                       # Fortschritt sofort festhalten
            with resume.open("a", encoding="utf-8") as f:
                f.write("\n".join(batch) + "\n")
        if dry_run:
            for s, p, o in tripel[:12]:
                print(f"    {s} {p} {o}")
        time.sleep(PAUSE)
    print(f"[BF] Phase 1: {kanten_neu} Kanten aus {len(verarbeitet)} Konzepten "
          f"({konzepte_mit} trugen welche); {ringe} Ringe nicht importiert (Azyklizität)",
          file=sys.stderr)
    labels_neu = 0
    if not skip_labels:
        zu_labeln = sorted(alle_objids - gelabelt)
        print(f"[BF] Phase 2: {len(zu_labeln)} Objekt-Konzepte zu benennen", file=sys.stderr)
        for batch in _batches(zu_labeln, BATCH):
            data = _hole({"action": "wbgetentities", "ids": "|".join(batch),
                          "props": "labels", "languages": "|".join(LANGS)})
            if data is None:
                time.sleep(PAUSE)
                continue
            lbls = extrahiere_labels(data.get("entities", {}))
            neu, _ = _saee(conn, lbls, dry_run)
            labels_neu += neu
            gelabelt |= {o for _, _, o in lbls}          # frisch benannte nicht erneut holen
            if dry_run:
                for s, p, o in lbls[:8]:
                    print(f"    {s} {p} {o}")
            time.sleep(PAUSE)
        print(f"[BF] Phase 2: {labels_neu} Label-Kanten gesät", file=sys.stderr)
    return kanten_neu, ringe, labels_neu


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill der dynamischen Schicht aus Wikidata")
    ap.add_argument("--dry-run", action="store_true", help="nichts schreiben, nur zählen/zeigen")
    ap.add_argument("--limit", type=int, default=0, help="höchstens N Konzepte (0 = alle)")
    ap.add_argument("--ids", default="", help="genau diese Q-ids (Komma), statt aus dem Ledger")
    ap.add_argument("--skip-labels", action="store_true", help="Phase 2 (Objekt-Labels) auslassen")
    ap.add_argument("--tiefung", action="store_true",
                    help="TIEFUNG: die neuen Objekt-Konzepte (Inseln) ernten, MIT is_a (platzieren)")
    ap.add_argument("--rekursiv", action="store_true",
                    help="REKURSIV: Tiefung Runde um Runde über die immer neuen Schalen, gedeckelt")
    ap.add_argument("--max-runden", type=int, default=3, dest="max_runden",
                    help="harter Runden-Deckel für --rekursiv (die Schale schrumpft nicht von selbst)")
    ap.add_argument("--resume-file", default="", help="Fortschrittsdatei (Default: neben dem Ledger)")
    args = ap.parse_args()

    if args.ids and not args.dry_run:
        ap.error("--ids ist nur für den Off-Pi-Test mit --dry-run vorgesehen (kein Ledger).")
    if args.rekursiv:
        args.tiefung = True                          # Rekursion tieft, also is_a-platzierend

    prop_map = PROP_MAP_TIEFUNG if args.tiefung else PROP_MAP   # Tiefung platziert die Inseln (is_a)

    conn = None
    if args.ids:
        ziele = [q.strip() for q in args.ids.split(",") if q.strip()]
        gelabelt: set[str] = set()
    else:
        from genus import cli
        conn = cli.get_conn()
        ziele = _insel_qids(conn) if args.tiefung else _ziel_qids(conn)
        gelabelt = _schon_gelabelt(conn)

    resume = Path(args.resume_file) if args.resume_file else None
    if resume is None and conn is not None:
        name = "backfill_tiefung.done" if args.tiefung else "backfill_konzepte.done"
        resume = Path(conn.execute("PRAGMA database_list").fetchone()["file"] or ".").parent / name
    fertig: set[str] = set()
    if resume and resume.exists():
        fertig = set(resume.read_text(encoding="utf-8").split())
    if fertig:
        ziele = [q for q in ziele if q not in fertig]
    if args.limit:
        ziele = ziele[:args.limit]

    if not args.rekursiv:
        print(f"[BF] {len(ziele)} Konzepte zu ernten"
              f"{' (dry-run)' if args.dry_run else ''}"
              f"{f', {len(fertig)} schon fertig' if fertig else ''}", file=sys.stderr)
        _ernte(conn, ziele, prop_map, gelabelt, resume, args.dry_run, args.skip_labels)
        return 0

    # --rekursiv: gebundene Schleife über die immer NEUEN Schalen. Wichtig (Befund 2026-07-06):
    # die Schale schrumpft NICHT von selbst (jede Ebene ~gleich breit — die Wikidata-Nachbarschaft
    # weitet sich konstant), „bis leer" würde halb Wikidata importieren. Darum HART gedeckelt.
    for runde in range(1, args.max_runden + 1):
        if not ziele:
            print(f"[BF] Runde {runde}: keine neuen Inseln mehr — konvergiert.", file=sys.stderr)
            return 0
        print(f"[BF] === Runde {runde}/{args.max_runden}: {len(ziele)} neue Inseln ===", file=sys.stderr)
        _ernte(conn, ziele, prop_map, gelabelt, resume, args.dry_run, args.skip_labels)
        fertig |= set(ziele)
        ziele = [] if conn is None else [q for q in _insel_qids(conn) if q not in fertig]
        if args.limit:
            ziele = ziele[:args.limit]
    print(f"[BF] Runden-Deckel ({args.max_runden}) erreicht; noch {len(ziele)} Inseln offen — "
          f"die Schale schrumpft nicht, bewusst gestoppt (sonst importierte man ganz Wikidata).",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
