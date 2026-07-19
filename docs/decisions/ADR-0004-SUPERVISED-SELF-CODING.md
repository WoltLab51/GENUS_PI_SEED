# ADR-0004 — Selbst-Codieren beginnt als beaufsichtigter Entwurf

> **Status:** accepted · **Datum:** 2026-07-15 · **Zuletzt verifiziert:** 2026-07-19

## Entscheidung

GENUS darf seinen Aufbau lesen, Symptome evidenzgebunden lokalisieren, eine begrenzte
Änderungsspezifikation erzeugen und nach menschlicher Freigabe einen Codeentwurf in einem
isolierten Git-Worktree anfordern und prüfen. Daraus entstehen ausdrücklich **keine** Rechte
für Commit, Merge, Push, Deploy oder privilegierte Ausführung.

```text
Selbstkarte → Diagnose → ChangeSpec → menschliche Draft-Freigabe
           → isolierter Entwurf → deterministische Gates → menschliches Diff-Review
           → menschlicher Merge/Deploy → Laufzeitbeobachtung → bestätigtes Ergebnis
```

Der deterministische Kern unter `genus/` startet weder Prozesse noch Modelle. Git und ein
optionaler externer Coding-Provider leben ausschließlich in `deploy/entwickler_worker.py`.
Der Provider sieht nur die im ChangeSpec erlaubten Dateien und nur nach einem separaten
Repository-Source-Opt-in.

## Monotone Autorität

Angenommene Entwürfe erweitern GENUS' Rechte nicht automatisch. Ein abgelehnter Entwurf oder
eine Laufzeitregression darf spätere Spezifikationen ausschließlich verschärfen: höhere
Risikostufe, kleineres Budget oder zusätzliche manuelle Gates. So kann Lernen die Aufsicht nie
wegoptimieren.

## Warum

Ein Modell kann Code plausibel erzeugen, aber weder seine eigene Abnahme definieren noch seine
Wirkung zuverlässig beurteilen. GENUS' Vorsprung liegt deshalb nicht in einem möglichst großen
Coder, sondern in einem kleinen, nachvollziehbaren Vertrag: Basiscommit, Scope, Budget,
unabhängige Tests, sichtbare Restfragen und menschliche Entscheidung sind getrennte Artefakte.

## Konsequenzen

- Jede Freigabe ist an den Hash genau einer Spezifikation und eines Basiscommits gebunden.
- Kritische Pfade werden in v1 niemals an ein externes Coding-Modell übergeben.
- Unified Diffs dürfen keine Secrets, Binärdateien, Löschungen, Umbenennungen oder Scope-Flucht
  enthalten.
- Die Werkbank führt ausschließlich registrierte argv-Gates aus, keinen Shelltext aus dem Plan.
- Ein grünes Reviewpaket bedeutet „bereit für menschliches Review“, niemals „merge-bereit“.
- Rollback vor dem Merge ist das Verwerfen des isolierten Worktrees; nach dem Deploy gilt weiter
  der normale Change-Trust- und Laufzeitvertrag.

Siehe [Selbst-Codieren](../design/SELF_CODING.md),
[Change Trust](ADR-0002-CHANGE-TRUST.md) und
[Wachstumskreislauf](ADR-0003-GROWTH-LOOP.md).
