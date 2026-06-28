# GENUS — Qualitäts-Charta

> Wie wir an GENUS arbeiten, damit *jede* Änderung den Kern **runder** macht —
> strukturell, nicht heroisch. Wachsamkeit vergisst; Gates halten. Das ist unser
> QMS für die Arbeit: wir haken es an *jeder* Scheibe ab.

Qualität heißt hier **nicht** „schnell Features", sondern: der Kern bleibt *sound,
gläsern, geerdet, ehrlich*. Daran wird jede Scheibe gemessen.

---

## 0 · Die Invarianten — woran „Qualität" sich misst

Nicht verhandelbar. Jede Änderung muss diese wahr lassen:

- **Gläsern** — jede Behauptung nachprüfbar; *nichts berechnet-aber-nicht-gespeichert*;
  Confidence / Trust / Halbwertszeit sind **read-time**.
- **Geerdet** — **keine Presets**; Magnituden self-kalibriert aus gelebten Daten
  (hartcodierte Werte nur als Seed-Fallback).
- **Replay-stabil** — Projektionen aus dem Event-Log neu baubar; Snapshot vorher == nachher.
- **Membran-rein** — `genus/` importiert nie HTTP / LLM / socket / subprocess; das
  Außen lebt in `deploy/`.
- **Ehrlich** — kein Overclaiming; Maße, die die *Wahrheit* sagen (Skill, nicht
  „improving"); fehlgeschlagen heißt fehlgeschlagen.
- **Fix the class** — den Fehler*typ* schließen, nicht die Instanz; strukturell vor Konvention.

---

## 1 · Beim Planen (vor dem Code)

- [ ] **Framing zuerst angreifen** — die eigene Annahme adversariell prüfen: stimmt die
  *Architektur*, nicht nur das Feature?
- [ ] **Die unumkehrbaren Entscheidungen benennen** (das Skelett) und *nur dort* tief investieren.
- [ ] **Was der Pi uns lehren wird, offen markieren** — es zu erraten wäre ein Preset.
- [ ] **Falsifizierbare Definition of Done** schreiben, *bevor* Code entsteht.
- [ ] **Design-Pre-Mortem:** „Wie könnte diese Scheibe eine Invariante (§0) verraten?"

---

## 2 · Beim Bauen — die Gates

**Mechanisch (CI macht rot — hängt nicht von Erinnern ab):**

- [ ] **Tests grün** · **Integrity grün** (`integrity.check`)
- [ ] **Replay-stabil** — `integrity.snapshot_projections` vorher == nachher
  (z. B. `test_forecast_events_pass_integrity_and_are_replay_stable`)
- [ ] **Membran-rein** — `tests/test_membrane_purity.py`
- [ ] **Docs-Currency-Anker** grün (Versions-Stempel, atlas-facts)

**Review-Fragen (per Scheibe von Hand — Kandidaten, später zu Gates zu härten):**

- [ ] Kein neuer hartcodierter Schwellwert (self-kalibriert oder nur Seed-Fallback)?
- [ ] Nichts berechnet-aber-gespeichert (read-time, wo immer ableitbar)?
- [ ] **Die Eigenschaft getestet, nicht das Beispiel** (die Mathematik festgenagelt,
  keine Magic Number)?
- [ ] **Jeder gefundene Bug** mit Regressionstest versiegelt?
- [ ] Kleinste solide Scheibe, *vertikal* (Event → Projektion → Read → CLI → Test),
  nicht halb-verdrahtet?

---

## 3 · Der ehrliche End-Check

- [ ] **Auf den Pi deployt** und mit *echten* Daten beobachtet — der lebende Pi ist der
  eigentliche Reviewer (*jeder* echte Bug kam von dort, nicht aus Tests).
- [ ] **Unsere Maße lügen nicht** — sagt die Zahl die Wahrheit? Wir kalibrieren uns
  selbst, wie GENUS sich kalibriert.
- [ ] **Alle Docs + kuratierte Visuals auf Stand** — Teil von „fertig", immer.

---

## 4 · Der Takt — eine Scheibe = eine PDCA-Schleife

```
PLAN  die Scheibe + falsifizierbare DoD
 DO   ein vertikaler Schnitt, end-to-end, grün
CHECK auf den Pi → echte Daten ansehen
 ACT  die gelebte Lücke = PLAN der nächsten Scheibe
```

Kein großer Vorab-Plan. Das **Skelett einmal richtig** (die tragenden Verträge),
dann **Scheibe für Scheibe** — und der Pi zeigt jede nächste Lücke.

---

*Workflow: bauen auf X1 → push to `main`, wenn grün → Ronny deployt, wenn es passt.*
