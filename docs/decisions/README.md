# Architecture Decision Records

> **Status:** current index
> **Zweck:** wenige, stabile Entscheidungen mit langfristiger Wirkung

| ADR | Entscheidung | Status |
|---|---|---|
| [0001](ADR-0001-CORE-AND-MEMBRANES.md) | Deterministischer Kern, begrenzte Membranen | accepted |
| [0002](ADR-0002-CHANGE-TRUST.md) | Änderungen verdienen Vertrauen erst durch Gates und Laufzeitevidenz | accepted |
| [0003](ADR-0003-GROWTH-LOOP.md) | Wachstum ist ein gemessener Kreislauf, keine Spezialfall-Sammlung | accepted |
| [0004](ADR-0004-SUPERVISED-SELF-CODING.md) | Selbst-Codieren beginnt als hashgebundener, beaufsichtigter Entwurf | accepted |
| [0005](ADR-0005-EXPLICIT-SCHEMA-EVOLUTION.md) | Schemaänderungen sind versioniert, explizit und fail-closed | accepted |
| [0006](ADR-0006-GOLDEN-LEDGER-ORACLE.md) | Golden Ledger und unabhängiges Oracle gehen Migration und Replay-Umbau voraus | accepted |
| [0007](ADR-0007-BOUNDED-REPLAY-INTEGRITY.md) | Bounded Replay und Integrity werden durch Golden- und Pi-Evidenz topologiegegated | accepted |
| [0008](ADR-0008-EXTERNAL-ANCHOR-TRUST.md) | Externe Anchor-Trust-, Key-Custody- und Ledger-Repair-Grenzen | accepted |
| [0009](ADR-0009-HUMAN-OWNED-CRITICAL-LANE.md) | A0 bleibt human-owned critical lane; Lernen bleibt nichtproduktiv isoliert | accepted |
| [0010](ADR-0010-HUMAN-SUPERVISED-MODEL-ASSISTANCE-A0.md) | Ronny darf Codex für A0.2 eng begrenzt read-only und test-only assistieren lassen | accepted |

Ein ADR erklärt **warum** eine Entscheidung gilt. Der aktuelle technische Vertrag lebt
weiterhin in [ARCHITECTURE.md](../ARCHITECTURE.md).
