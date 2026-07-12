# Die GENUS-Dokumentation

> **Status:** kanonischer Index
> **Zuletzt verifiziert:** 2026-07-12
> **Regel:** Jede Aussage hat genau einen autoritativen Wohnort.

Willkommen in der Werkstatt. Diese Bibliothek trennt bewusst zwischen dem, was GENUS
**ist**, dem, was **als Nächstes** gebaut wird, den **Entscheidungen dahinter** und der
wertvollen **Entstehungsgeschichte**.

## Wähle deinen Weg

| Wenn du … | Starte hier | Danach |
|---|---|---|
| GENUS zum ersten Mal siehst | [Charter](CHARTER.md) | [NOW](NOW.md) |
| heute weiterbauen willst | [NOW](NOW.md) | [Roadmap](ROADMAP.md) · [Quality](QUALITY.md) |
| einen Kernvertrag änderst | [Architektur](ARCHITECTURE.md) | [Event-Vertrag](EVENT_CONTRACT.md) · [Security](SECURITY_MODEL.md) |
| eine frühere Entscheidung verstehen willst | [Decisions](decisions/README.md) | [Baujournal](history/BUILD_JOURNAL.md) |
| den Pi betreibst | [Operations](operations/README.md) | [Deploy-Runbook](../deploy/README.md) |
| nach Ideen und Tiefe suchst | [Research](#research--offene-denkräume) | [Visual Atlas](visual/ATLAS.html) |

## Was darf was bestimmen?

| Stufe | Bedeutung | Darf Builds steuern? |
|---|---|---:|
| **canonical** | aktueller verbindlicher Vertrag | ja |
| **current** | abgeleiteter Ist- oder Planungsstand | ja, innerhalb des Vertrags |
| **accepted decision** | begründete, angenommene Entscheidung | ja |
| **design** | aktive Ausgestaltung eines Teilbereichs | nur über kanonische Verträge |
| **research** | Untersuchung, Hypothese oder Zukunftsraum | nein |
| **report** | datierter Befund | nein |
| **generated** | aus Code erzeugte Projektion | nur der Generator ist Quelle |
| **history / archived** | frühere Wahrheit oder Baugeschichte | nein |
| **parked** | bewusst nicht entschieden | nein |

## Kanon – die fünf Verträge

| Dokument | Besitzt |
|---|---|
| [CHARTER.md](CHARTER.md) | Nordstern, Wesensziele und unverhandelbare Grenzen |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Systemgrenzen, Schichten, Abhängigkeiten und Invarianten |
| [EVENT_CONTRACT.md](EVENT_CONTRACT.md) | Ereignistypen, Pflichtfelder und Replay-Regeln |
| [SECURITY_MODEL.md](SECURITY_MODEL.md) | Bedrohungsmodell und Trust Boundaries |
| [QUALITY.md](QUALITY.md) | Plan-, Bau-, Abnahme- und Laufzeitgates |

## Gegenwart und Zukunft

- [NOW.md](NOW.md) — der kurze, überprüfbare Ist-Stand und genau die nächsten Prioritäten.
- [ROADMAP.md](ROADMAP.md) — nur Zukunft, Abhängigkeiten und Definition of Done.
- [generated/ATLAS_FACTS.md](generated/ATLAS_FACTS.md) — maschinell erzeugte aktuelle Fakten.

Live-Zahlen gehören in `NOW` nur als datierter Beleg oder in eine generierte Projektion.
Sie gehören nicht in zeitlose Verträge.

## Entscheidungen

- [ADR-0001 — Kern und Membranen](decisions/ADR-0001-CORE-AND-MEMBRANES.md)
- [ADR-0002 — Change Trust](decisions/ADR-0002-CHANGE-TRUST.md)
- [ADR-0003 — Wachstum als Kreislauf](decisions/ADR-0003-GROWTH-LOOP.md)

Neue ADRs werden nur für Entscheidungen angelegt, die mehrere Module oder spätere
Builds binden. Kleine lokale Entscheidungen bleiben bei Code und Tests.

## Design – Teilmodelle und Entwürfe

- [Gedächtnis](design/MEMORY.md)
- [Persönlichkeit](design/PERSONALITY.md)
- [Sensor-Prinzip](design/SENSOR_PRINCIPLE.md)
- [Grundausbildung / Materialwahl (datierter Design-Snapshot)](design/BASIC_TRAINING.md)

Der Banner jedes Dokuments sagt, ob es aktiv oder ein datierter Design-Snapshot ist. Bei
Widerspruch gewinnt der Kanon.

## Research – offene Denkräume

- [Intelligenz](research/INTELLIGENCE.md)
- [Material](research/MATERIAL.md)
- [Abitur als Prüfstein](research/ABITUR.md)
- [Antizipation](research/ANTICIPATION.md)
- [Epistemische Physik](research/EPISTEMIC_PHYSICS.md)
- [Visuelles Denken](research/VISUAL_THINKING.md)
- [Strategische Studie vom 2026-07-01](research/STUDY_2026-07-01.md)

Research darf inspirieren, ist aber kein stiller Implementierungsauftrag.

## Reports – datierte Befunde

- [Wachstums-Audit vom 2026-07-03](reports/2026-07-03-growth-audit.md)
- [Kern-/Pi-Härtungs-Audit vom 2026-07-12](reports/2026-07-12-hardening-audit.md)
- [Systemaudit, Morphologie und SWOT vom 2026-07-12](reports/2026-07-12-system-audit.md)

Ein Report wird nicht „aktuell gehalten“. Er bekommt einen Nachfolger und verweist darauf.

## Geschichte, Visuals und Ablage

- [Baujournal](history/BUILD_JOURNAL.md) — die vollständige ausgelieferte Geschichte.
- [Frühere Gesamtansicht](history/GESAMTBILD_2026-06-28.md)
- [Zielarchitektur-Snapshot v2](history/TARGET_ARCHITECTURE_2026-07-04.md)
- [Ledger-Audit v1.5](history/LEDGER_AUDIT_v1.5.md)
- [Core Map](visual/CORE_MAP.html) · [Visual Atlas](visual/ATLAS.html)
- [Parked](parked/README.md) — sichtbar, aber nicht entschieden.
- [Archive](archive/README.md) — superseded Specs und Prompts.

Visualisierungen erklären Verträge; sie sind selbst keine Build-Autorität.

## Operations und Security Reporting

- [Operations-Lotse](operations/README.md)
- [Pi-Deploy und Runbook](../deploy/README.md)
- [Security-Meldungen](../SECURITY.md)

## Pflegevertrag

1. **Invariant geändert?** `ARCHITECTURE`, `EVENT_CONTRACT` oder `SECURITY_MODEL`.
2. **Priorität geändert?** `NOW` und gegebenenfalls `ROADMAP`.
3. **Warum entschieden?** ein ADR.
4. **Teilbereich ausgestaltet?** `design/`.
5. **Noch offen?** `research/` oder `parked/`.
6. **Datierter Befund?** `reports/`.
7. **Abgelöst?** Banner setzen, Nachfolger verlinken, nach `history/` oder `archive/`.

Jedes neue Dokument erhält oben mindestens `Status`, `Owner/Quelle` und
`Zuletzt verifiziert` oder ein festes Snapshot-Datum. Interne Verweise sind klickbare,
relative Markdown-Links.
