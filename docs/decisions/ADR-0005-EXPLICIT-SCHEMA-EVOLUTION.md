# ADR-0005 — Explicit Schema Evolution and Migration Boundary

> **Status:** accepted · **Datum:** 2026-08-09
>
> **Decision Owner:** Ronny · **Umsetzung:** noch nicht begonnen
>
> **Quelle:** D-A0.1 im [A0 Decision Packet](../reports/2026-08-09-a0-decision-packet.md)

## Kontext

Der normale Datei-Connect ruft heute `init_schema()` auf, führt das aktuelle
`schema.sql` aus, ergänzt fehlende Spalten über `_ensure_column()` und committet.
Eine persistierte Schema-Version, nummerierte Migrationen, ein read-only Status,
ein expliziter Runner und ein Recovery-Vertrag fehlen. Der
[A0 Foundation Audit](../reports/2026-08-09-a0-foundation-audit.md) belegt damit
eine fehlende Trennung zwischen Öffnen, Prüfen und Verändern; er belegt keine
konkret beschädigte Produktdatenbank.

## Entscheidung

GENUS führt eine explizite, versionierte und fail-closed Schema-Evolution ein.

1. Ein normaler Connect- oder Startup-Pfad verändert das Schema einer
   bestehenden Datenbank nicht.
2. Jede unterstützte Datenbank besitzt eine explizite monotone Schema-Version
   und einen kanonischen Schema-Fingerprint.
3. `genus db status` liest Version, Fingerprint und Kompatibilität strikt
   read-only.
4. Eine alte, neue, unbekannte oder teilweise migrierte Version führt zur
   verständlichen Startverweigerung. Ein Dienst migriert nicht nebenbei.
5. Nur ein ausdrücklich menschlich aufgerufener `genus db migrate`-Runner darf
   nummerierte, deterministische und idempotente Forward-Migrationen ausführen.
6. Migrationen werden zunächst ausschließlich gegen konsistente
   Datenbankkopien entwickelt und abgenommen.
7. Destruktive, Ledger-/Seal-nahe oder nicht nachweislich atomare Schritte
   verwenden Copy → Transform → Verify → Cutover. Rückkehr erfolgt über ein
   verifiziertes Backup, nicht durch ein riskantes historisches `down`.
8. Eine Schema-Migration darf fachliche Events, Eventreihenfolge oder Seals
   nicht umschreiben. Eine notwendige Ledger-Reparatur fällt ausschließlich
   unter ADR-0008.

## Migrationsjournal und Gates

Der spätere Vertrag muss mindestens Migrations-ID, From-/To-Version,
Migrationsdigest, Codebezug, Vor-/Nachbedingungen, Start, Ende und Ergebnis
nachvollziehbar binden. Die genaue Tabellenform wird erst in der
human-owned Implementierung festgelegt.

Vor einer späteren Produktmigration sind erforderlich:

- Writer-Stopp;
- konsistentes DB/WAL/SHM-Backup mit Digest;
- erfolgreiche Restore-Probe;
- letzter gültiger externer Anchor;
- Integrity-/Seal-Baseline;
- freier Speicher, Operator und ausdrückliche menschliche Freigabe.

Nach der Migration auf einer Kopie sind erforderlich:

- Schema-Version, Fingerprint und alle Nachbedingungen;
- das unabhängige ADR-0006-Orakel;
- zweimaliger Replay ohne neue oder geänderte Events;
- Digests aller Projektionen;
- Integrity-, Seal- und Anchor-Verifikation;
- definierter Abbruch-/Recovery-Nachweis.

Das grüne Kopien-Receipt erteilt noch keine Produktfreigabe. Vor Cutover braucht
es ein zweites, ausdrücklich an dieses Receipt, Backup und Zielversion
gebundenes Human-Go. Nach Cutover werden Schema, Oracle, Integrity, Seal und
Anchor erneut read-only geprüft; erst das grüne Post-Cutover-Receipt erlaubt den
Dienststart. Diese Produktphase bleibt bis zu einem späteren ausdrücklichen
Auftrag gesperrt.

## Erwogene Alternativen

- **Heutigen `_ensure_column()`-/Startup-Pfad beibehalten:** abgelehnt, weil
  Autorität, Version und Recovery unsichtbar bleiben.
- **Nummerierte Migration automatisch beim Startup:** abgelehnt, weil jeder
  Dienststart weiterhin eine verändernde kritische Operation wäre.
- **Expliziter manueller Runner:** angenommen.

## Konsequenzen

- Deploy und Migration werden zwei getrennte, geordnete Betriebsphasen.
- Fail-Closed kann Verfügbarkeit kosten; das ist gegenüber stiller DDL die
  gewählte sichere Fehlerart.
- Unbekannte historische Schemas werden nicht geraten, sondern separat
  analysiert.
- ADR-0006 ist zwingendes fachliches Orakel; ADR-0007 muss Replay/Integrity auf
  realistischer Größe begrenzen.
- Die spätere Implementierung ist human-owned critical scope nach ADR-0009.

## Noch nicht entschieden oder umgesetzt

Basisschemaversion, unterstützte Altversionen und ihre erwarteten Fingerprints
werden vor Beginn der read-only A0.1-Schemaerkennung festgelegt. Genaue
Journal-DDL, Copy/Cutover-Schwelle, numerische Downtime-/Platzbudgets und
SQLite-Fault-Injection-Ergebnisse folgen vor dem ersten Produktlauf. Dieser ADR
erzeugt keine Tabelle, keinen CLI-Befehl und autorisiert keine Migration.
