# Die GENUS-Dokumentation

> **Status:** kanonischer Index
> **Zuletzt verifiziert:** 2026-08-10
> **Regel:** Jede Aussage hat genau einen autoritativen Wohnort.

Willkommen in der Werkstatt. Diese Bibliothek trennt bewusst zwischen dem, was GENUS
**ist**, dem, was **als Nächstes** gebaut wird, den **Entscheidungen dahinter** und der
wertvollen **Entstehungsgeschichte**.

## Wähle deinen Weg

| Wenn du … | Starte hier | Danach |
|---|---|---|
| GENUS zum ersten Mal siehst | [Charter](CHARTER.md) | [NOW](NOW.md) |
| heute weiterbauen willst | [NOW](NOW.md) | [Roadmap](ROADMAP.md) · [Quality](QUALITY.md) |
| GENUS' Antworten prüfen willst | [Antwortqualität](design/ANSWER_QUALITY.md) | [generierte Alltagsprobe](generated/ANTWORTQUALITAET.md) · [Reviews](reviews/ALLTAGSPROBE_V1.json) |
| GENUS beim Selbst-Codieren begleiten willst | [Selbst-Codieren](design/SELF_CODING.md) | [ADR-0004](decisions/ADR-0004-SUPERVISED-SELF-CODING.md) · [Change Trust](decisions/ADR-0002-CHANGE-TRUST.md) |
| einen Kernvertrag änderst | [Architektur](ARCHITECTURE.md) | [GENUS-Kartografie](visual/GENUS_KARTOGRAFIE.html) · [Event-Vertrag](EVENT_CONTRACT.md) |
| eine frühere Entscheidung verstehen willst | [Decisions](decisions/README.md) | [Baujournal](history/BUILD_JOURNAL.md) |
| den Pi betreibst | [Operations](operations/README.md) | [Deploy-Runbook](../deploy/README.md) |
| nach Ideen und Tiefe suchst | [Research](#research--offene-denkräume) | [historischer Visual Atlas](visual/ATLAS.html) |

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
- [generated/GENUS_KARTOGRAFIE.md](generated/GENUS_KARTOGRAFIE.md) — Modul-, Event-,
  Lernwirkungs- und Pi-Abhängigkeiten, mit Quellen und Drift-Gate.
- [visual/GENUS_KARTOGRAFIE.html](visual/GENUS_KARTOGRAFIE.html) — dieselbe Karte
  interaktiv nach Wirkung, Events, Lernen, Modulen und Betrieb erkunden.

Live-Zahlen gehören in `NOW` nur als datierter Beleg oder in eine generierte Projektion.
Sie gehören nicht in zeitlose Verträge.

## Entscheidungen

- [ADR-0001 — Kern und Membranen](decisions/ADR-0001-CORE-AND-MEMBRANES.md)
- [ADR-0002 — Change Trust](decisions/ADR-0002-CHANGE-TRUST.md)
- [ADR-0003 — Wachstum als Kreislauf](decisions/ADR-0003-GROWTH-LOOP.md)
- [ADR-0004 — Beaufsichtigtes Selbst-Codieren](decisions/ADR-0004-SUPERVISED-SELF-CODING.md)
- [ADR-0005 — Explizite Schema-Evolution](decisions/ADR-0005-EXPLICIT-SCHEMA-EVOLUTION.md)
- [ADR-0006 — Golden Ledger und unabhängiges Replay-Oracle](decisions/ADR-0006-GOLDEN-LEDGER-ORACLE.md)
- [ADR-0007 — Bounded Replay und Integrity](decisions/ADR-0007-BOUNDED-REPLAY-INTEGRITY.md)
- [ADR-0008 — Externes Anchor-Vertrauen und Ledger-Reparatur](decisions/ADR-0008-EXTERNAL-ANCHOR-TRUST.md)
- [ADR-0009 — Human-owned Critical Lane](decisions/ADR-0009-HUMAN-OWNED-CRITICAL-LANE.md)
- [ADR-0010 — Menschlich geführte Modellassistenz ausschließlich in A0.2](decisions/ADR-0010-HUMAN-SUPERVISED-MODEL-ASSISTANCE-A0.md)
- [ADR-0011 — Golden-Ledger-Kanonisierung und Belief-Coverage](decisions/ADR-0011-GOLDEN-LEDGER-CANONICALIZATION-AND-BELIEF-COVERAGE.md)

Neue ADRs werden nur für Entscheidungen angelegt, die mehrere Module oder spätere
Builds binden. Kleine lokale Entscheidungen bleiben bei Code und Tests.

## Design – Teilmodelle und Entwürfe

- [Antwortqualität und Alltagsprobe](design/ANSWER_QUALITY.md)
- [Gedächtnis](design/MEMORY.md)
- [Persönlichkeit](design/PERSONALITY.md)
- [Sensor-Prinzip](design/SENSOR_PRINCIPLE.md)
- [Beaufsichtigtes Selbst-Codieren](design/SELF_CODING.md)
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
- [H0.1-Vorabprofil und Messdesign vom 2026-07-13](reports/2026-07-13-h0-1-baseline/report.html)
- [Runtime-Kartografie und Pi-Audit vom 2026-07-13](reports/2026-07-13-cartography-runtime-audit.md)
- [H1-Pilot und erster geschlossener Antwortkreis vom 2026-07-13](reports/2026-07-13-h1-response-loop.md)
- [A0-Wahrheitsfundament-Audit vom 2026-08-09](reports/2026-08-09-a0-foundation-audit.md)
- [A0-Entscheidungspaket vom 2026-08-09](reports/2026-08-09-a0-decision-packet.md)
- [A0.3a Measurement Harness und Pi-Baseline vom 2026-08-14](reports/2026-08-14-a0-3a-measurement-harness-baseline.md)
- [A0.3b Shadow Generation & Atomic Cutover Prototype vom 2026-08-18](reports/2026-08-15-a0-3b-shadow-cutover-prototype.md)

Ein Report wird nicht „aktuell gehalten“. Er bekommt einen Nachfolger und verweist darauf.

## Reviews – menschliche Abnahme

- [Alltagsprobe v1](reviews/ALLTAGSPROBE_V1.json) — hashgebundene Einzelwertungen für Ton
  und Nutzen; ein leerer Reviewbestand ist ein ehrlicher offener Status, kein Fehler im
  Dokument.
- [A0.2 Golden Ledger Entry Contract](reviews/A0_2_GOLDEN_LEDGER_ENTRY_CONTRACT.md) —
  angenommene Rollen, Corpus-, Kanonisierungs-, Digest- und Stop-Grenzen vor dem
  ersten Golden-Artefakt; die spätere Oracle-Checkliste bleibt bis Ronnys
  getrenntem Review offen.
- [A0.2 Golden Ledger Artifact Schema Contract](reviews/A0_2_GOLDEN_LEDGER_ARTIFACT_SCHEMA.md) —
  angenommene mechanische Supporting Specification für exakte Artefaktnamen,
  JSON-Feldmengen, Dateibytes und Digestbindungen des A0.2-Kandidaten.
- [A0.2 Golden Ledger V2 · menschlicher Annahmebeleg](reviews/2026-08-13-a0-2-golden-ledger-acceptance.md) —
  Ronnys hashgebundene Annahme des byteidentischen Golden-JSONL-/Replay-Oracle-
  Kandidaten als versioniertes Testfundament; das historische SQLite-Gate bleibt offen.
- [A0.3a Measurement und Topologie · menschlicher Entscheidungsbeleg](reviews/2026-08-14-a0-3a-topology-decision.md) —
  angenommene Pi-Budgets, verworfene Option B für den Livebetrieb und Auswahl
  von Option C als ausschließlich experimentell weiter zu beweisender Live-Kandidat.
- [A0.3b Shadow Generation & Atomic Cutover · menschlicher Annahmebeleg](reviews/2026-08-18-a0-3b-prototype-acceptance.md) —
  angenommener Option-C-/Mode-A-Prototyp mit Batchgröße 3072; Live-Aktivierung
  bleibt bis zu A0.3c und einem weiteren Human-Go gesperrt.

Reviews sind keine neue Wissensquelle und kein Trainingssignal. Sie bestätigen nur den
exakten synthetischen Wortlaut, dessen Fall- und Antwort-Hash in derselben Zeile steht.

## Geschichte, Visuals und Ablage

- [Baujournal](history/BUILD_JOURNAL.md) — die vollständige ausgelieferte Geschichte.
- [Frühere Gesamtansicht](history/GESAMTBILD_2026-06-28.md)
- [Zielarchitektur-Snapshot v2](history/TARGET_ARCHITECTURE_2026-07-04.md)
- [Ledger-Audit v1.5](history/LEDGER_AUDIT_v1.5.md)
- [Aktuelle GENUS-Kartografie](visual/GENUS_KARTOGRAFIE.html)
- [Historischer Core Map](visual/CORE_MAP.html) · [historischer Visual Atlas](visual/ATLAS.html)
- [Parked](parked/README.md) — sichtbar, aber nicht entschieden.
- [Archive](archive/README.md) — superseded Specs und Prompts.

Historische Visualisierungen erklären frühere Verträge; sie sind selbst keine
Build-Autorität. Die aktuelle GENUS-Kartografie ist eine generierte Projektion und wird
über `genus kartografie check` gegen Code, Eventregister und Quellenfundstellen geprüft.

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
