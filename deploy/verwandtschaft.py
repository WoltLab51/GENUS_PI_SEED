#!/usr/bin/env python3
"""Die VERWANDTSCHAFTS-Weberei (edge, embed-venv) — Ronnys „Gewichte statt Definitionen".

Für jedes Konzept berechnet der lokale Embedder die BEDEUTUNGS-NÄHE zu seinen Graph-Nachbarn
(Geschwister + Cousins unter geteilten is_a-Eltern — der Kandidatenkreis bleibt so beschränkt
UND sinnvoll) und schreibt die engsten als GEWICHTETE Kante ``Q -verwandt-> Q'`` mit dem Cosinus
in der Herleitung (``cos=0.71``), gedeckelt als ``model:embedder`` (model:* überstimmt nie
Gegründetes). So bekommt das kristalline Netz erstmals ein „wie nah" — „Wolf" liegt näher an
„Hund" als „Goldfisch", obwohl beide unter „Tier" hängen.

Gleiches Muster wie bridge_senses.py: Modell lebt HIER am Rand, Schreibungen gehen über die
genus-CLI (eigener, gegründeter Prozess). Der Kern liest die Kanten rein lesend (genus.verwandt).
GENUS_VERWANDT_DRYRUN=1 zeigt die Paare, ohne den Graphen zu berühren — prüfen vor dem Schreiben.
"""
import os
import sqlite3
import subprocess
import sys

# numpy/fastembed werden LAZY in verwandt_konzept()/main() geladen -- so bleibt das Modul (und
# damit seine reine Graph-Logik: concept_desc/kandidaten) ohne die embed-venv importier- und
# lokal testbar; nur der eigentliche Wiege-Lauf braucht die schweren Abhängigkeiten.
DB = os.environ.get("GENUS_DB_PATH", os.path.expanduser("~/.genus/genus.sqlite3"))
MODEL = os.environ.get("GENUS_EMBED_MODEL",
                       "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
LANG = os.environ.get("GENUS_BRIDGE_LANG", "de")
GENUS = os.environ.get("GENUS_BIN",
                       os.path.join(os.path.dirname(__file__), "..", ".venv", "bin", "genus"))
MIN_SIM = float(os.environ.get("GENUS_VERWANDT_MIN_SIM", "0.60"))   # nur echt nahe Nachbarn
TOP_K = int(os.environ.get("GENUS_VERWANDT_TOP_K", "8"))            # engste je Konzept
MAX_KANDIDATEN = int(os.environ.get("GENUS_VERWANDT_MAX_CAND", "80"))
# Eine über-breite Kategorie („Artefakt" mit Tausenden Kindern) ist KEIN Bedeutungs-Nachbarschafts-
# Kreis -- ihre Kinder sind ein Gemischtwarenladen. Solche Knoten werden beim Sammeln übersprungen
# (Messer zieht dann aus „Stichwaffe"/„Werkzeug", nicht aus dem ganzen Artefakt-Universum).
MAX_FANOUT = int(os.environ.get("GENUS_VERWANDT_MAX_FANOUT", "20"))
DRYRUN = os.environ.get("GENUS_VERWANDT_DRYRUN", "0") == "1"


def german_label(conn, qid):
    row = conn.execute(
        "SELECT subject FROM relation_projection WHERE predicate IN ('label', 'expresses') "
        "AND object = ? AND subject LIKE '%@' || ? LIMIT 1", (qid, LANG)).fetchone()
    return row[0].rsplit("@", 1)[0] if row else None


def concept_desc(conn, qid):
    """Der Bedeutungs-Fingerabdruck eines Konzepts: sein deutsches Label plus seine is_a-Eltern
    (wie in bridge_senses). ``None``, wenn es keinen deutschen Namen hat (nichts zu vektorisieren)."""
    lbl = german_label(conn, qid)
    if lbl is None:
        return None
    parents = [german_label(conn, r[0]) for r in conn.execute(
        "SELECT DISTINCT object FROM relation_projection WHERE subject = ? AND predicate = 'is_a'",
        (qid,))]
    return " · ".join([lbl] + [p for p in parents if p])


def _eltern(conn, qid):
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT object FROM relation_projection WHERE subject = ? AND predicate = 'is_a'",
        (qid,))]


def _kinder(conn, knoten):
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT subject FROM relation_projection WHERE object = ? AND predicate = 'is_a'",
        (knoten,))]


def _enge_kinder(conn, knoten):
    """Die Kinder eines Knotens — aber nur, wenn er ENG genug ist (≤ MAX_FANOUT). Eine über-breite
    Kategorie definiert keinen Bedeutungs-Nachbarschafts-Kreis und wird übersprungen."""
    kinder = _kinder(conn, knoten)
    return kinder if len(kinder) <= MAX_FANOUT else []


def kandidaten(conn, qid):
    """Der Nachbarschafts-Kreis eines Konzepts: Geschwister (Kinder der is_a-Eltern) plus Cousins
    (Kinder der Onkel = Kinder der Großeltern-Kinder), aber nur aus ENGEN Knoten (über-breite
    Kategorien wie „Artefakt" liefern keinen sinnvollen Kreis). Beschränkt UND bedeutungsverwandt
    — kein O(N²) übers ganze Netz, aber breit genug, dass echte Verwandte (Hund/Wolf) drin sind."""
    eltern = _eltern(conn, qid)
    if not eltern:
        return []
    onkel = [o for g in {gg for e in eltern for gg in _eltern(conn, e)} for o in _enge_kinder(conn, g)]
    kreis = set()
    for knoten in set(eltern) | set(onkel):     # Kinder der Eltern = Geschwister; Kinder der Onkel = Cousins
        kreis.update(_enge_kinder(conn, knoten))
    kreis.discard(qid)
    return sorted(kreis)[:MAX_KANDIDATEN]


def _konzepte_von(conn, word):
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT object FROM relation_projection WHERE subject = ? AND predicate = 'expresses'",
        (f"{word}@{LANG}",))]


def verwandt_konzept(conn, emb, qid, cache):
    """Wiegt die Nachbarn EINES Konzepts und schreibt die engsten als gewichtete Kante."""
    import numpy as np

    desc = concept_desc(conn, qid)
    cands = [c for c in kandidaten(conn, qid) if concept_desc(conn, c) is not None]
    if desc is None or not cands:
        return 0
    cos = lambda a, b: float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    def vektor(q):
        if q not in cache:
            cache[q] = list(emb.embed([concept_desc(conn, q)]))[0]
        return cache[q]

    qv = vektor(qid)
    gewichtet = sorted(((c, cos(qv, vektor(c))) for c in cands), key=lambda p: p[1], reverse=True)
    n = 0
    for other, sim in gewichtet[:TOP_K]:
        if sim < MIN_SIM:
            break                      # sortiert -> ab hier wird nichts mehr nah genug
        if DRYRUN:
            print(f"[VERW] {german_label(conn, qid)} ~{sim:.2f}~ {german_label(conn, other)}")
        else:
            subprocess.run([GENUS, "relate", qid, "verwandt", other,
                            "--source", "model:embedder", "--derivation", f"cos={sim:.4f}"],
                           check=False, stdout=subprocess.DEVNULL)
        n += 1
    return n


def eligible_words(conn):
    return [r[0].rsplit("@", 1)[0] for r in conn.execute(
        "SELECT DISTINCT subject FROM relation_projection "
        "WHERE predicate = 'is_a' AND subject LIKE 'Q%'").fetchall()] or []


def main() -> int:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)   # read-only graph access
    try:
        words = sys.argv[1:]
        # Wörter -> Konzepte; ohne Argumente: alle Konzepte mit is_a (der volle Nacht-Lauf)
        if words:
            qids = sorted({q for w in words for q in _konzepte_von(conn, w)})
        else:
            qids = sorted({r[0] for r in conn.execute(
                "SELECT DISTINCT subject FROM relation_projection "
                "WHERE predicate = 'is_a' AND subject LIKE 'Q%'")})
        from fastembed import TextEmbedding
        emb = TextEmbedding(model_name=MODEL)   # Modell EINMAL laden
        cache: dict = {}
        total, beruehrt = 0, 0
        for qid in qids:
            n = verwandt_konzept(conn, emb, qid, cache)
            total += n
            beruehrt += 1 if n else 0
    finally:
        conn.close()
    print(f"[VERW] {total} verwandt-Kante(n) über {beruehrt}/{len(qids)} Konzept(e) "
          f"({'dry-run' if DRYRUN else 'geschrieben als model:embedder, gewichtet'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
