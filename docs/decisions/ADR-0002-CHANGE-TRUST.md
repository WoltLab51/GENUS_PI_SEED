# ADR-0002 — Eine Änderung ist noch kein Vertrauen

> **Status:** accepted · **Datum:** 2026-06-18 · **Zuletzt verifiziert:** 2026-07-12

## Entscheidung

Merge oder Deploy machen eine Änderung verfügbar, aber nicht automatisch vertrauenswürdig.
Vertrauen entsteht stufenweise:

1. nachvollziehbarer Entwurf und begrenzter Scope,
2. statische Constraints und Tests,
3. Replay-, Integritäts- und Seal-Prüfung,
4. menschliche Freigabe für wirkungsvolle Änderungen,
5. beobachtete Laufzeitwirkung,
6. Rücknahme oder Nachschärfung bei Abweichung.

## Harte Asymmetrie

Ein Generator darf vorschlagen. Er darf seine eigene Abnahme nicht definieren, den Merge
nicht durchführen und Root-/Außenwirkung nicht freischalten. Besonders wirkungsvolle
Werkzeuge bleiben dauerhaft pro Ausführung gegatet.

## Konsequenzen

- Proposal, Review, Activation und Operation sind getrennte Ereignisse.
- Selbst-Codieren bleibt `propose → test → human merge`.
- Der Pi-Deploy prüft denselben Ledger vor und nach Replay.
- Laufzeitevidenz gehört zur Definition of Done.

Siehe [Quality](../QUALITY.md) und [Security-Modell](../SECURITY_MODEL.md).
