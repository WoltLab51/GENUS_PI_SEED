#!/usr/bin/env python3
"""Die VERWANDTSCHAFTS-Weberei (edge, embed-venv) — Ronnys „Gewichte statt Definitionen".

Für jedes Konzept berechnet der lokale Embedder die BEDEUTUNGS-NÄHE zu seinen Graph-Nachbarn
(Geschwister + Cousins unter geteilten is_a-Eltern — der Kandidatenkreis bleibt so beschränkt
UND sinnvoll) und schreibt die engsten als GEWICHTETE Kante ``Q -verwandt-> Q'`` mit dem Cosinus
in der Herleitung (``cos=0.71``), gedeckelt als ``model:embedder`` (model:* überstimmt nie
Gegründetes). So bekommt das kristalline Netz erstmals ein „wie nah" — „Wolf" liegt näher an
„Hund" als „Goldfisch", obwohl beide unter „Tier" hängen.

Auf 30k Konzepte ausgelegt: das is_a-Netz + die Labels werden EINMAL in den Speicher gelesen
(danach ist die Kandidaten-Suche reines Dict-Lesen, kein SQL pro Konzept), ALLE Beschreibungen
werden GEBÜNDELT embeddet (fastembed batcht intern — Größenordnungen schneller als einzeln), und
die Kanten werden INKREMENTELL geschrieben (Blöcke via ``genus relate-bulk``) — nichts geht bei
einem Abbruch verloren, und der Speicher bleibt beschränkt. Gleiches Membran-Muster wie
bridge_senses.py: Modell lebt HIER am Rand, Schreibungen über die genus-CLI.
GENUS_VERWANDT_DRYRUN=1 zeigt die Paare, ohne den Graphen zu berühren.
"""
import os
import subprocess
import sqlite3
import sys

# numpy/fastembed werden LAZY geladen -- so bleibt die reine Graph-Logik (lade_netz/concept_desc/
# kandidaten) ohne die embed-venv importier- und lokal testbar; nur der Wiege-Lauf braucht sie.
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
# Kreis -- ihre Kinder sind ein Gemischtwarenladen. Solche Knoten werden beim Sammeln übersprungen.
MAX_FANOUT = int(os.environ.get("GENUS_VERWANDT_MAX_FANOUT", "20"))
SCHREIB_BLOCK = int(os.environ.get("GENUS_VERWANDT_BLOCK", "10000"))  # inkrementell schreiben
DRYRUN = os.environ.get("GENUS_VERWANDT_DRYRUN", "0") == "1"


def lade_netz(conn):
    """Liest is_a (beide Richtungen) + deutsche Labels EINMAL in den Speicher. Danach ist die
    Kandidaten-Suche reines Dict-Lesen -- der Flaschenhals bei 30k Konzepten war das SQL pro Konzept."""
    eltern, kinder, label = {}, {}, {}
    for s, o in conn.execute(
            "SELECT subject, object FROM relation_projection WHERE predicate = 'is_a'"):
        eltern.setdefault(s, []).append(o)
        kinder.setdefault(o, []).append(s)
    for subj, o in conn.execute(
            "SELECT subject, object FROM relation_projection "
            "WHERE predicate IN ('label', 'expresses') AND subject LIKE '%@' || ?", (LANG,)):
        if o not in label:                       # erstes deutsches Wort je Konzept (wie german_label)
            label[o] = subj.rsplit("@", 1)[0]
    return {"eltern": eltern, "kinder": kinder, "label": label}


def concept_desc(netz, qid):
    """Der Bedeutungs-Fingerabdruck eines Konzepts: sein deutsches Label plus seine is_a-Eltern.
    ``None``, wenn es keinen deutschen Namen hat (nichts zu vektorisieren)."""
    lbl = netz["label"].get(qid)
    if lbl is None:
        return None
    return " · ".join([lbl] + [netz["label"][p] for p in netz["eltern"].get(qid, [])
                               if p in netz["label"]])


def _enge_kinder(netz, knoten):
    """Die Kinder eines Knotens — aber nur, wenn er ENG genug ist (≤ MAX_FANOUT); eine über-breite
    Kategorie definiert keinen Bedeutungs-Nachbarschafts-Kreis."""
    kids = netz["kinder"].get(knoten, [])
    return kids if len(kids) <= MAX_FANOUT else []


def kandidaten(netz, qid):
    """Der Nachbarschafts-Kreis: Geschwister (Kinder der Eltern) + Cousins (Kinder der Onkel),
    nur aus ENGEN Knoten. Beschränkt UND bedeutungsverwandt."""
    eltern = netz["eltern"].get(qid, [])
    if not eltern:
        return []
    onkel = [o for g in {gg for e in eltern for gg in netz["eltern"].get(e, [])}
             for o in _enge_kinder(netz, g)]
    kreis = set()
    for knoten in set(eltern) | set(onkel):
        kreis.update(_enge_kinder(netz, knoten))
    kreis.discard(qid)
    return sorted(kreis)[:MAX_KANDIDATEN]


def _konzepte_von(conn, word):
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT object FROM relation_projection WHERE subject = ? AND predicate = 'expresses'",
        (f"{word}@{LANG}",))]


def _schreibe_gebuendelt(edges):
    """Ein Block Kanten in EINEM ``genus relate-bulk``-Aufruf (JSONL über stdin)."""
    import json
    jsonl = "\n".join(json.dumps(e, ensure_ascii=False) for e in edges)
    subprocess.run([GENUS, "relate-bulk"], input=jsonl.encode("utf-8"), check=False)


def main() -> int:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        netz = lade_netz(conn)
        words = sys.argv[1:]
        if words:
            qids = sorted({q for w in words for q in _konzepte_von(conn, w)})
        else:   # der volle Lauf: alle Konzepte mit is_a UND deutschem Label
            qids = sorted(q for q in netz["eltern"] if q.startswith("Q") and q in netz["label"])
    finally:
        conn.close()
    print(f"[VERW] Netz geladen: {len(netz['eltern'])} Konzepte mit is_a, {len(netz['label'])} "
          f"Labels; {len(qids)} Ziel-Konzepte", flush=True)

    # 1. Kandidaten je Ziel (Dict-Lesen) + alle zu embeddenden Beschreibungen sammeln
    kand_map, brauchen = {}, set()
    for q in qids:
        cs = [c for c in kandidaten(netz, q) if concept_desc(netz, c) is not None]
        if cs and concept_desc(netz, q) is not None:
            kand_map[q] = cs
            brauchen.add(q)
            brauchen.update(cs)
    brauchen = sorted(brauchen)
    print(f"[VERW] {len(kand_map)} Ziele mit Nachbarn, {len(brauchen)} Beschreibungen zu embedden",
          flush=True)

    # 2. ALLE Beschreibungen GEBÜNDELT embedden (fastembed batcht intern) + normalisieren (cos = dot)
    import numpy as np
    from fastembed import TextEmbedding
    emb = TextEmbedding(model_name=MODEL)
    vecs = {}
    for q, v in zip(brauchen, emb.embed([concept_desc(netz, q) for q in brauchen])):
        v = np.asarray(v, dtype=np.float32)
        n = np.linalg.norm(v)
        vecs[q] = v / n if n else v
    print(f"[VERW] {len(vecs)} Konzepte embeddet -- wiege und schreibe blockweise ...", flush=True)

    # 3. Pro Ziel: Cosinus (reines numpy) -> engste -> Kanten, INKREMENTELL geschrieben
    edges, total, beruehrt, geschrieben = [], 0, 0, 0
    for q in kand_map:
        qv = vecs.get(q)
        if qv is None:
            continue
        sims = sorted(((c, float(qv.dot(vecs[c]))) for c in kand_map[q] if c in vecs),
                      key=lambda p: p[1], reverse=True)
        n = 0
        for other, sim in sims[:TOP_K]:
            if sim < MIN_SIM:
                break
            if DRYRUN:
                print(f"[VERW] {netz['label'].get(q, q)} ~{sim:.2f}~ {netz['label'].get(other, other)}")
            else:
                edges.append({"subject": q, "predicate": "verwandt", "object": other,
                              "source": "model:embedder", "derivation": f"cos={sim:.4f}"})
            n += 1
        total += n
        beruehrt += 1 if n else 0
        if len(edges) >= SCHREIB_BLOCK:
            _schreibe_gebuendelt(edges)
            geschrieben += len(edges)
            print(f"[VERW] ... {geschrieben} Kanten geschrieben", flush=True)
            edges = []
    if edges and not DRYRUN:
        _schreibe_gebuendelt(edges)
        geschrieben += len(edges)
    print(f"[VERW] {total} verwandt-Kante(n) über {beruehrt} Konzept(e) "
          f"({'dry-run' if DRYRUN else f'{geschrieben} geschrieben als model:embedder, gewichtet'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
