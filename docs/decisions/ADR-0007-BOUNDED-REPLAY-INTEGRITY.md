# ADR-0007 — Bounded Replay and Integrity Verification

> **Status:** accepted · **Datum:** 2026-08-09
>
> **Decision Owner:** Ronny · **Umsetzung:** A0.3a angenommen; A0.3b aktiv;
> Produktpfade unverändert
>
> **Quelle:** D-A0.3 im [A0 Decision Packet](../reports/2026-08-09-a0-decision-packet.md)

## Kontext

Replay und Integrity laden heute den vollständigen Ledger per `fetchall()` in
den RAM. Der CLI-Replay läuft in einer langen `BEGIN IMMEDIATE`-Transaktion;
Writer-Blockade ist belegt, Concurrent-Reader-, Kill-, WAL-, Peak-RAM- und
Pi-Budgets sind nicht experimentell bewiesen. Ein Ledger mit mehr als einer
Million Events darf nicht von unbegrenztem residentem Speicher oder unklarer
Abbruchsemantik abhängen.

## A0.3a — aufgelöstes Experimentgate

Ronny hat am 14. August 2026 den
[A0.3a-Messreport](../reports/2026-08-14-a0-3a-measurement-harness-baseline.md)
und den getrennten
[menschlichen Entscheidungsbeleg](../reviews/2026-08-14-a0-3a-topology-decision.md)
angenommen.

Option B reduzierte auf der Produktkopie den Peak RSS von 978.894.848 B beim
heutigen Replay auf 38.387.712 B und blieb mit 106,775489 s Laufzeit sowie
151.636.632 B WAL innerhalb der angenommenen Zeit-/Speicherbudgets. Die einzelne
`BEGIN IMMEDIATE`-Transaktion blockierte den realen Writer jedoch bis zu dessen
Timeout nach 5,003508 s und verfehlte damit die verbindliche Grenze von 2,0 s
ohne Timeout oder Starvation.

Damit ist Option B als konkurrierende Live-Topologie verworfen. Sie bleibt für
Wartung bei bewusst gestoppten Writern, Datenbankkopien, Migrationstests und
forensische/offline Prüfungen zulässig. Option C mit versionierten
Shadow-Projektionen, bounded Aufbau, Catch-up und geprüftem atomarem Cutover ist
der verbindliche Live-Kandidat für A0.3b.

Angenommen sind höchstens 256 MiB Peak RSS, 180 s für den vollständigen
1M-Shadow-Rebuild, 256 MiB WAL, 2,0 s einzelne Writer-Blockade ohne Timeout oder
Starvation sowie höchstens 10 s Recovery mit ausschließlich vollständig altem
oder vollständig neuem Zustand. Die 180 s sind kein Writer-Blockadebudget. Das
Shadow-Speicherplatzbudget folgt erst aus A0.3b.

Diese Auflösung wählt eine experimentell weiter zu beweisende Topologie. Sie
aktiviert weder Option C noch einen neuen Replay-/Integrity-Produktpfad. Vor
jedem Live-Cutover bleibt ein weiteres ausdrückliches Human-Go erforderlich.

## Entscheidung

Replay und Integrity werden bounded, fixed-head, ledger-write-free und
wiederholbar. Ein Live-Rebuild schreibt notwendigerweise Projektionen; „no
write“ bedeutet hier ausschließlich: keine neuen, geänderten oder gelöschten
Ledger-Events.

Unabhängig von der späteren Sichtbarkeitstopologie gelten folgende Invarianten:

1. Zu Beginn wird unter einer expliziten Writer-/Snapshot-Grenze ein fester
   `head_id` erfasst.
2. Events werden bis zu diesem Head per Cursor, Keyset oder `fetchmany` mit
   konfigurierbarer begrenzter Batch-Größe gelesen; kein vollständiges
   Ledger-`fetchall()`.
3. Replay und Integrity verwenden denselben kanonischen Event- und
   Projektionsvertrag.
4. Kein Verify- oder Replay-Pfad erzeugt, ändert oder löscht Ledger-Events.
5. Alle Projektionen und das ADR-0006-Orakel werden verglichen; eine
   unvollständige Teilaufnahme genügt nicht.
6. API und CLI besitzen einen eindeutigen Owner für Begin, Commit, Rollback,
   Abbruch und Retry.
7. Fortschritt nennt Phase, Head, letzte ID, verarbeitet/gesamt, Rate,
   Laufzeit und Batch — niemals Payloads.
8. Alle semantischen Postchecks laufen vor Commit oder Cutover. Projector-,
   Oracle- oder Validierungsfehler rollen auf den kanonisch identischen alten
   Projektionsstand zurück; ein als fehlgeschlagen gemeldeter Lauf darf keinen
   neuen Stand committen.
9. Bei Prozess-/Stromausfall an der atomaren Commit-/Cutover-Grenze ergibt
   Reopen eindeutig entweder den vollständigen alten oder den bereits vollständig
   geprüften neuen Stand; nie eine als gültig behandelte Teilprojektion.

## Experimentgegatede Topologie

Die menschliche Entscheidung legt bewusst noch keine SQLite-Topologie ohne
Betriebsbeweis fest:

1. **Option B**, bounded Cursor-/Batch-Replay innerhalb einer einzigen
   expliziten SQLite-Transaktion, wird zuerst gegen Golden Ledger sowie 10k,
   100k und 1M synthetische Events prototypisch gemessen.
2. Option B wird nur gewählt, wenn Peak RAM, WAL,
   Laufzeit, Writer-Blockade, Concurrent Reader, Kill/Reopen und Recovery die
   vorher festgelegten Pi-Budgets erfüllen.
3. Verfehlt sie ein verbindliches Budget, ist **Option C**, versionierte
   Shadow-Projektionen mit geprüftem atomarem Wechsel, der festgelegte Fallback.
4. **Option D**, eine separate temporäre Datenbank/Kopie, bleibt der bevorzugte
   Validierungsweg für Migrationen und forensische Prüfungen; sie ist nicht
   automatisch der Live-Cutover.
5. Committete In-place-Teilbatches sind kein Normalpfad, weil sie ohne lückenloses
   Fence-/Recovery-Protokoll eine partielle Gegenwart sichtbar machen könnten.

## Pflicht-Experimente

- Golden-Fälle 0, 1, Legacy-Präfix/Epoche/Tail und gemischte Eventtypen;
- Batchgrenzen einschließlich 1 sowie Werte direkt unter/auf/über dem Default;
- 10k, 100k und 1M Events mit realistischen Payload-Größen;
- Zeit, extern gemessenes Peak RSS, CPU/I/O, DB-/Scratch-/Shadow-Platz und
  WAL-Hochwasser;
- paralleler read-only Leser über alle Projektionen;
- konkurrierender Writer und Long-Reader/WAL-Pinning;
- Projector-Exception, ungültiges Event, `SIGKILL`/Stromverlust und ENOSPC in
  jeder kritischen Phase;
- Reopen, Retry und zweiter Replay ohne Drift;
- unveränderte Eventzahl, IDs, Payloads, Genesis, Seal und Anchor;
- dieselben Grenzen für Integrity und die tatsächliche Deploysequenz;
- Ziel-Pi-Abnahme gegen vorher menschlich beschlossene Budgets.

## Erwogene Alternativen

- **Option A — heutiges `fetchall()`:** abgelehnt als unbeschränkter
  Dauervertrag.
- **Option B — Ein-Transaktions-Batch:** erster Kandidat, nur nach bestandenen
  Gates.
- **Option C — Shadow-Projektionen:** verbindlicher Fallback bei Budget-/Availability-
  Verfehlung.
- **Option D — separate DB/Kopie:** Prüfpfad, nicht automatisch Live-Cutover.

## Konsequenzen

- Das ADR-0006-Orakel ist Vorbedingung für die semantische Messung.
- Read-only Schemaerkennung aus ADR-0005 läuft vor Replay einer fremden DB.
- Fortschritt und Performance werden Teil der Abnahme, nicht Optimismus im
  Kommentar.
- Die konkrete Batch-Größe und numerischen Pi-Budgets werden vor Auswahl der
  Topologie menschlich festgelegt; sie werden nicht aus diesem ADR geraten.
- Die spätere Implementierung bleibt human-owned critical scope nach ADR-0009.

## Noch nicht umgesetzt

Der heutige produktive Replay-/Integrity-Code erfüllt diesen Vertrag noch
nicht. A0.3a lieferte ausschließlich Harness, Evidenz und Topologieentscheidung;
A0.3b muss Shadow-Generation, Catch-up, atomaren Cutover, Faults und Budgets
zunächst auf Fixtures und Kopien beweisen. Dieser ADR autorisiert keinen
produktiven Replay-Umbau oder Cutover.
