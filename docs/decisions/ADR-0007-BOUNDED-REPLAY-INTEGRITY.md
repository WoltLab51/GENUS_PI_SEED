# ADR-0007 — Bounded Replay and Integrity Verification

> **Status:** accepted · **Datum:** 2026-08-09
>
> **Decision Owner:** Ronny · **Umsetzung:** noch nicht begonnen
>
> **Quelle:** D-A0.3 im [A0 Decision Packet](../reports/2026-08-09-a0-decision-packet.md)

## Kontext

Replay und Integrity laden heute den vollständigen Ledger per `fetchall()` in
den RAM. Der CLI-Replay läuft in einer langen `BEGIN IMMEDIATE`-Transaktion;
Writer-Blockade ist belegt, Concurrent-Reader-, Kill-, WAL-, Peak-RAM- und
Pi-Budgets sind nicht experimentell bewiesen. Ein Ledger mit mehr als einer
Million Events darf nicht von unbegrenztem residentem Speicher oder unklarer
Abbruchsemantik abhängen.

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

Der heutige Replay-/Integrity-Code erfüllt diesen Vertrag noch nicht. Dieser ADR
ändert keine Transaktion, Tabelle, CLI, Deploysequenz oder Benchmark und
autorisiert keinen produktiven Replay-Umbau.
