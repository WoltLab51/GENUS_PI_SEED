# ADR-0009 — Human-Owned Critical Lane and Isolated Learning Lane

> **Status:** accepted · **Datum:** 2026-08-09
>
> **Decision Owner:** Ronny · **Geltung:** sofortige Prozessgrenze
>
> **Quelle:** D-A0.8 im [A0 Decision Packet](../reports/2026-08-09-a0-decision-packet.md)

## Kontext

ADR-0004 erlaubt beaufsichtigte, hashgebundene Modellentwürfe, schließt
kritische Pfade aus dem Modellscope aus und behält Commit, Merge, Push und Deploy
beim Menschen. A0 betrifft zugleich Schema, Ledger, Replay, Integrity, Sealing,
Anchors, Key Custody, Repair und kritische Governance. Zusätzlich zur
Autonomiegrenze braucht diese Arbeit eine eindeutige Produktspur, damit ihre
Evidenz nicht durch konkurrierende Kernmerges driftet.

Diese Entscheidung ergänzt ADR-0004; sie schreibt dessen angenommene Historie
nicht rückwirkend um.

## Entscheidung

### Human-owned critical lane

A0 ist der einzige mergefähige aktive Produktänderungspfad im kritischen
`GENUS_PI_SEED`-Kern, solange die A0-Roadmap aktiv ist.

Für Schema, Ledger, Replay, Integrity, Sealing, Anchors, Key Custody, Repair,
kritische Governance und kritische Publish-/Deploypfade gilt:

- kein GENUS-generierter oder durch die Coding-Membran erzeugter Modellpatch;
- keine kritischen Dateien im Modellscope;
- keine selbstdefinierte Abnahme;
- kein automatischer Commit, Merge, Push oder Deploy;
- der Mensch besitzt Implementierungsautorenschaft, Patchhoheit, Review,
  Freigabe, Merge, Betriebszeremonie und Laufzeitabnahme.

KI darf bei Audit-Auswertung, Threat Modeling, Testfalldesign, Gegenbeispielen
und Dokumentation unterstützen. Kritischer Quelltext und kritische
Implementierungsdiffs bleiben außerhalb des Modellscopes; deren Review und
Freigabe führt der Mensch durch. KI ist weder verantwortlicher Autor noch
Freigeber der kritischen Implementierung.

### Isolated non-production learning lane

Der Entwickler-Loop darf parallel ausschließlich auf unkritischem,
nichtproduktivem Terrain lernen:

- synthetische Repositories;
- isolierte Worktrees;
- `GENUS_EGG`;
- `GENUS_CORE`;
- nicht produktiv gemergte unkritische Übungsaufgaben.

Harte Grenzen sind:

- kein konkurrierender `GENUS_PI_SEED`-Produktmerge;
- keine Produktdaten;
- keine kritischen Dateien oder Secrets;
- keine Rechteausweitung;
- keine automatische Aktivierung, Übernahme oder Beförderung in die
  Produktlinie.

## Konsequenzen

- `docs/NOW.md` nennt genau einen aktiven Produktentwicklungsschritt: den ersten
  A0-Schritt Golden Ledger + unabhängiges Oracle.
- `docs/ROADMAP.md` hält die A0-Abhängigkeiten; frühere Produktarbeit bleibt
  sichtbar, aber pausiert als Mergepfad.
- Read-only Messung und Sicherung dürfen parallel laufen, wenn sie keine zweite
  verändernde Produktspur öffnen.
- Lernen in der isolierten Lane erweitert Autorität niemals automatisch; jede
  spätere Produktnutzung beginnt wieder am menschlichen Critical-Lane-Gate.
- Ein neuer aktiver Produktpfad erfordert eine ausdrückliche Änderung von NOW
  und ROADMAP nach A0-Abnahme.

## Erwogene Alternative

Parallele `GENUS_PI_SEED`-Produktmerges mit getrennten Integrationsfenstern
wurden verworfen. Sie würden Basiscommit, Golden-Orakel, Migration,
Replaymessung und Laufzeitabnahme während einer Fundamentänderung vermischen.

## Nicht autorisiert

Dieser ADR autorisiert keinen Runtime-Patch, keine Modellfreigabe für kritische
Dateien, keinen Commit/Push/Deploy durch GENUS und keine Produktdaten in der
Lernlinie.
