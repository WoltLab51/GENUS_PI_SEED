# A0.3a Measurement und Topologie · menschlicher Entscheidungsbeleg

> **Status:** accepted human decision
>
> **Reviewer:** Ronny
>
> **Decision date:** 2026-08-14
>
> **Entscheidung:** A0.3a accepted · Option C selected

## Gebundene Evidenz

Ronny nimmt den A0.3a Measurement-Harness- und Pi-Baseline-Kandidaten an. Die
fachliche Grundlage ist der unveränderte
[A0.3a Measurement-Harness- und Pi-Baseline-Report](../reports/2026-08-14-a0-3a-measurement-harness-baseline.md).

| Bindung | Wert |
|---|---|
| Ausgangscommit | `3ccf5b5329a8297d4f548d36b27267af74e6326c` |
| Report SHA-256 | `c6ea78846da9df8e324815567d0b71c03029f9548bb4b69cb2d7afcb84d817a4` |
| gemessene Harnessrevision | `c52ae92fc3ac0eca7f563d21f5105d3485d9a13cb7fa5885803fafd51af0ec15` |
| gemessene CLI-Revision | `c59c258f7b563add79b13b4b3c0fa1128153ecdd05e78dcd3ab61d4b89ff6956` |

Der nach dem Pi-Lauf erfolgte Codeaudit härtete ausschließlich
Receipt-/Telemetrieaussagen; SQL, Batchloop, Transaktionsgrenze, Projektoren,
Prüfer und Sampler blieben unverändert. Der Report dokumentiert beide
Revisionen und ihre Grenze. Eine zusätzliche fail-closed Einschränkung des
experimentellen Runners auf markierte disposable Datenbanken ist
Promotionshärtung; sie verändert weder Messalgorithmus noch Messwerte und
autorisiert keinen Produktlauf.

## Architekturfossilien

Die Topologieentscheidung beruht insbesondere auf diesen gegen Kopien
ermittelten Pi-Werten:

| Messung | Dauer | Peak RSS | WAL High-Water |
|---|---:|---:|---:|
| heutiges unbounded Replay | 46,149562 s | 978.894.848 B | 151.636.632 B |
| bounded Option B | 106,775489 s | 38.387.712 B | 151.636.632 B |
| heutige unbounded Integrity | 71,851944 s | 3.128.098.816 B | 0 B im Prüflauf |

Der reale konkurrierende Pi-Writer timeoutete nach **5,003508 Sekunden**,
während Option B seine einzelne `BEGIN IMMEDIATE`-Transaktion ungefähr 107
Sekunden hielt. Option B löst damit das Speicherproblem, aber nicht das
Availability-Problem.

## Verbindlich angenommene Budgets

| Gate | Angenommene Grenze |
|---|---:|
| Peak RSS | höchstens 256 MiB / 268.435.456 B |
| 1M-Rebuild-Dauer | höchstens 180 s |
| WAL High-Water | höchstens 256 MiB / 268.435.456 B |
| einzelne Writer-Blockade | höchstens 2,0 s |
| Writer-Timeout | keiner |
| Writer-Starvation | keine |
| Recovery | höchstens 10 s |
| Zustand nach Recovery | ausschließlich vollständig alt oder vollständig neu |

Die 180 Sekunden erlauben die gesamte Hintergrunddauer eines vollständigen
Shadow-Rebuilds. Sie erlauben **keine** 180-sekündige Writer-Sperre. Ein eigenes
Shadow-/Scratch-Speicherplatzbudget wird erst aus dem A0.3b-Prototyp abgeleitet
und blockiert diese Topologieentscheidung nicht.

## Topologieentscheidung

```text
[x] Accept A0.3a measurement candidate

Live-Topologie:
[x] Option C — versionierte Shadow-Projektionen
[ ] Option B — Livebetrieb

Option B bleibt zulässig für:
[x] Wartung bei bewusst gestoppten Writern
[x] Datenbankkopien
[x] Migrationstests
[x] forensische/offline Prüfungen
```

Option B verfehlt mit der gemessenen Writer-Blockade ein verbindliches Budget.
Nach [ADR-0007](../decisions/ADR-0007-BOUNDED-REPLAY-INTEGRITY.md) ist damit
Option C der verbindliche Live-Kandidat. Der bounded Eventstrom, die
Streaming-Digests und die fixed-head-Prüfung aus Option B bleiben für Option C
wertvolle Bausteine.

Diese Entscheidung erlaubt Option-B-Läufe nur auf ausdrücklich markierten
disposable Datenbanken oder in einem menschlich begonnenen Wartungsfenster mit
bewusst gestoppten Writern. Sie autorisiert keinen direkten Aufruf des
experimentellen Harness gegen die Produktdatenbank.

## Nächster aktiver Schritt: A0.3b

**A0.3b — Shadow Generation & Atomic Cutover Prototype** ist der einzige aktive
Produktentwicklungspfad. Er bleibt ein isolierter Prototyp gegen Golden Ledger,
synthetische Daten und eine Produkt-DB-Kopie.

A0.3b muss mindestens beweisen:

1. versionierte aktive Generation G1 und Shadow-Generation G2 gleichzeitig;
2. fixed head H0 und bounded Aufbau von G2 bis H0;
3. weiterlaufende normale Writer ohne Timeout oder Starvation;
4. Reader sehen bis zum Cutover ausschließlich die vollständige aktive G1;
5. Catch-up der G2 für Events nach H0 bis nahe an den Live-Head;
6. eine finale Writer-Grenze von höchstens 2,0 Sekunden;
7. finalen Head H* erfassen und den letzten Tail vollständig nachziehen;
8. Golden Oracle und alle zwölf Projektionsdigests stimmen;
9. Ledger, Eventzahl, Genesis, Epoche, Seal und Anchor bleiben unverändert;
10. atomarer Wechsel G1 → G2 ohne halbe Generation;
11. Crash vor Cutover ergibt vollständig alt, Crash nach Cutover vollständig neu;
12. Reopen und Retry sind deterministisch;
13. Peak RSS, Gesamtbuild, WAL und Recovery halten die angenommenen Budgets ein.

Catch-up mit kurzer finaler Fence, eine begrenzte Dual-Write-Phase oder eine
andere Generationstechnik werden experimentell verglichen. Diese Entscheidung
nimmt Dual-Write nicht vorweg.

Die noch offenen Pflichtexperimente aus ADR-0007 — unter anderem ungültiges
Event, Long-Reader/WAL-Pinning, ENOSPC, produktgroßer Kill/Recovery und zweiter
Replay — bleiben vor Abschluss von A0.3 nachzuweisen.

## Nicht autorisiert

- kein Ersatz des bestehenden produktiven Replay-/Integrity-Pfads;
- kein produktiver Shadow-Aufbau oder Cutover auf dem Pi;
- keine Migration;
- kein Reseal, keine neue Epoche und kein neuer Anchor;
- keine Änderung an A0.2, A0.1a oder A0.1b;
- keine Live-Aktivierung ohne ein zweites ausdrückliches Human-Go nach A0.3b.

A0.2, A0.1a und A0.1b bleiben eingefroren. Codex setzt diese Entscheidung
ausschließlich als technischer, nicht autoritativer Operator um.
