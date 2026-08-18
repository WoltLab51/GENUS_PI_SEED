# ADR-0007 — Bounded Replay and Integrity Verification

> **Status:** accepted · **Datum:** 2026-08-09
>
> **Decision Owner:** Ronny · **Umsetzung:** A0.3a und A0.3b-Prototyp
> angenommen; A0.3c aktiv; Live-Aktivierung gesperrt
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

## A0.3b — angenommener Prototyp, kein Live-Go

Ronny hat am 18. August 2026 den unveränderten
[A0.3b-Prototypreport](../reports/2026-08-15-a0-3b-shadow-cutover-prototype.md)
und den getrennten
[menschlichen Annahmebeleg](../reviews/2026-08-18-a0-3b-prototype-acceptance.md)
angenommen.

Der angenommene Prototyp verwendet Option C mit drei versionierten Generationen
in derselben SQLite-Datei, Final-Sync Mode A und Batchgröße 3072. Auf der
Pi-Produktdatenbankkopie lagen G2-Build bei `169.746161856 s`, Peak RSS bei
`42303488 B`, WAL bei `19994392 B`, die längste Schreibtransaktion bei
`1.656518293 s`, der finale Fence bei `0.008216829 s` und Recovery bei
`0.460784818 s`. Zwölf Projektionen und neun Sequenzen stimmten; das Ledger
blieb unverändert, und Mode A benötigte keinen Fallback.

Der vorausgehende rote 4096er Pi-Lauf mit einer `2.167361215 s` langen
Schreibtransaktion bleibt dauerhaft erhalten. Die Annahme bestätigt den Beweis
gegen Fixtures, synthetische Ledger und read-only erworbene Produktkopien. Sie
behauptet weder literal power loss noch einen generation-aware Produktpfad und
autorisiert keinen Live-Lauf.

Die derzeit für GENUS verwendete Pi-Python-Runtime meldet SQLite 3.46.1. Diese
Version enthält nicht den bestätigten WAL-reset-Fix. Maßgeblich ist die von der
GENUS-Python-Runtime tatsächlich geladene Bibliothek über
`sqlite3.sqlite_version`, nicht die Version eines separat installierten
`sqlite3`-CLI.

### Verbindliches A0.3c-Gate

**A0.3c — Runtime Prerequisite & Live Readiness** ist der einzige aktive
Produktentwicklungsschritt. Vor einem weiteren Human-Go gelten kumulativ:

1. Exakter Python-Executable- und Environment-Pfad der betroffenen
   GENUS-Prozesse sowie `sys.executable`, `sqlite3.sqlite_version` und
   `sqlite3.sqlite_version_info` werden gebunden.
2. Ein reproduzierbarer Installations-, Pinning-, Verifikations- und
   Rollbackpfad liefert nachweislich eine WAL-reset-sichere Runtime. Ziel ist
   eine aktuelle 3.53.x-Linie; die normale fail-closed Mindestgrenze ist
   `sqlite3.sqlite_version_info >= (3, 51, 3)`.
3. Vollständige GENUS-Suite und A0.2-Golden-/SQLite-Gates sind unter genau
   dieser Runtime grün.
4. Mindestens drei aufeinanderfolgende frische Pi-Produktkopienläufe verwenden
   denselben Kandidaten, dieselbe Runtime, dieselben Gates und Batchgröße 3072,
   ohne Code-, Konfigurations- oder Tuningänderung zwischen den Läufen.
5. Jeder Lauf hält einzeln höchstens 2,0 s je Schreibtransaktion und finalem
   Fence, null Writer-Timeouts, keine Starvation, höchstens 256 MiB RSS/WAL,
   höchstens 180 s Build und 10 s Recovery, 12/12 Projektionen, 9/9 Sequenzen,
   unverändertes Ledger, ausschließlich vollständig alt oder vollständig neu
   sowie Mode A ohne Fallback.
6. Ein roter Lauf setzt die konsekutive Serie zurück. Retuning eröffnet einen
   neuen Messkandidaten; es ist kein automatischer Fallback.

Der vorgeschlagene zusätzliche Main-DB-Rahmen von 512 MiB ist noch nicht
menschlich angenommen. Shadow-/Scratch-Platz, vollständige Backup-Kopie und
Betriebsreserve bleiben ein getrenntes A0.3c-Gate. Auch nach vollständig grünem
A0.3c bleibt ein weiteres ausdrücklich gebundenes Human-Go vor jeder
Produktintegration oder Live-Aktivierung Pflicht.

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

## Aufgelöste experimentgegatede Topologie

Die ursprüngliche Entscheidung legte vor dem Betriebsbeweis noch keine
SQLite-Topologie fest. A0.3a und A0.3b haben dieses Gate jetzt aufgelöst:

1. **Option B** ist nach ihrem Writer-Timeout als konkurrierende Live-Topologie
   verworfen. Sie bleibt für Wartung bei gestoppten Writern, Kopien,
   Migrationstests und forensische/offline Prüfungen zulässig.
2. **Option C**, versionierte Shadow-Projektionen mit geprüftem atomarem
   Wechsel, ist als Prototyp angenommen.
3. **Mode A**, bounded Rest-Tail und Pointer-CAS in derselben kurzen
   Transaktion, ist der angenommene Final-Sync-Prototyp. Mode B bleibt ein
   expliziter Fault-/Recovery-Pfad; es gibt keinen stillen Fallback.
4. **Option D**, eine separate temporäre Datenbank/Kopie, bleibt der bevorzugte
   Validierungsweg für Migrationen und forensische Prüfungen; sie ist nicht
   automatisch der Live-Cutover.
5. Committete In-place-Teilbatches sind kein Normalpfad, weil sie ohne lückenloses
   Fence-/Recovery-Protokoll eine partielle Gegenwart sichtbar machen könnten.
6. Keine dieser Auflösungen autorisiert Produktintegration oder Live-Cutover.

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
- **Option B — Ein-Transaktions-Batch:** als konkurrierender Livepfad verworfen;
  für bewusst gestoppte Writer und Kopien weiter zulässig.
- **Option C — Shadow-Projektionen:** als Prototyp angenommen; Live bleibt bis
  A0.3c und einem weiteren Human-Go gesperrt.
- **Option D — separate DB/Kopie:** Prüfpfad, nicht automatisch Live-Cutover.

## Konsequenzen

- Das ADR-0006-Orakel ist Vorbedingung für die semantische Messung.
- Read-only Schemaerkennung aus ADR-0005 läuft vor Replay einer fremden DB.
- Fortschritt und Performance werden Teil der Abnahme, nicht Optimismus im
  Kommentar.
- Batchgröße 3072, Mode A und die numerischen Pi-Budgets sind für den
  A0.3b-Prototyp angenommen. Live-Readiness verlangt die separate konsekutive
  A0.3c-Messreihe.
- Die spätere Implementierung bleibt human-owned critical scope nach ADR-0009.

## Produktiv noch nicht umgesetzt

Der heutige produktive Replay-/Integrity-Code erfüllt diesen Vertrag noch
nicht. A0.3a lieferte Messung und Topologieentscheidung; A0.3b lieferte den
angenommenen isolierten Prototyp. A0.3c härtet ausschließlich Runtime und
Live-Readiness auf Kopien. Dieser ADR autorisiert weder generation-aware
Produktintegration noch produktiven Replay-Umbau oder Cutover. Dafür bleibt ein
weiteres ausdrückliches Human-Go erforderlich.
