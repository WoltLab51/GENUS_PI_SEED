# GENUS · Jetzt

> **Status:** aktueller Arbeitsstand
>
> **Stand:** 18. August 2026
>
> **Verifizierte Entscheidungsbasis:** `123ab6b` (A0.3a vollständig promoviert;
> A0.3b-Baseline)
>
> **Letzter hier belegter Laufzeit-Snapshot:** 14. August 2026 auf `0d9ea06`
>
> **Zweck:** in zwei Minuten verstehen, wo GENUS steht und worauf der nächste
> saubere Schritt zielt

Der zuletzt hier belegte Pi-Snapshot zeigt einen gehärteten, replaybaren Kern im
Dauerbetrieb. Seit dem 9. August besitzt GENUS außerdem angenommene A0-Verträge
für Schema, Golden Ledger, Replay, externe Anchors und kritische
Änderungsautorität. A0.2 ist seit dem 14. August vollständig abgeschlossen:
Golden JSONL, unabhängiges Replay-Oracle und eine echte historische
SQLite-Fixture sind menschlich angenommen, auf GitHub gemergt und auf dem Pi
geprüft. A0.1a ist seit dem 14. August ebenfalls abgeschlossen: GENUS erkennt
seine aktuelle Produkt-DB, die historische v1.1-Fixture und fremde SQLite-
Strukturen ausschließlich read-only. A0.1b ist nun ebenfalls vollständig
promoviert: Normale Starts lassen ausschließlich das aktuelle Schema auf genau
der zuvor geprüften Connection bis zur schreibfähigen Initialisierung passieren.
A0.3b ist nun als isolierter Prototyp menschlich angenommen: Option C mit
Final-Sync Mode A und Batchgröße 3072 bestand lokal und auf einer
Pi-Produktdatenbankkopie alle angenommenen Gates. Diese Annahme ist kein
Live-Go. Der einzige aktive Produktpfad ist jetzt A0.3c: Die tatsächlich von
GENUS verwendete Python-SQLite-Runtime und drei konsekutive Pi-Kopienläufe
müssen Live-Readiness beweisen.

## Das Bild in einem Satz

> A0 ist der einzige mergefähige Produktpfad; A0.3b beweist Option C und Mode A
> als Prototyp, während A0.3c die unsichere Python-SQLite-Runtime und die noch
> fehlende Wiederholbarkeit vor jedem Live-Go fail-closed auflöst.

## Was heute belastbar ist

Die folgende Tabelle ist der datierte Abnahme-Snapshot vom 13. Juli 2026, keine
Behauptung über ungeprüfte Veränderungen danach.

| Bereich | Letzter hier belegter Stand |
|---|---|
| Kern | gehärtet; Herkunft, Projektionen, Replay und Unsicherheit bleiben getrennt |
| Linux-Nachweis | 1.318 Tests auf dem Pi bestanden |
| Produkt-Ledger | 938.614 Ereignisse bei der Deploy-Abnahme; Integrität und Siegelkette intakt |
| Betrieb | Learner, Telegram und Watchdog aktiv; Root-/User-Grenze gehärtet |
| Streudaten | historisches Root-Ledger read-only geprüft und quarantänisiert |
| Graph | Hierarchiezyklen abgewehrt; deterministische Relationen idempotent |
| Selbstbild | Identität, Mission und Habitat werden aus Code, Zielgraph und aktiven Zuständen gelesen |
| Gesprächsgrenze | spezifische Absichten fallen nicht mehr auf semantisch andere Elternantworten zurück |
| Datenschutz | Owner-Direktchat; neue Logs/Tagespuffer rohtextfrei; Nachtrotation atomar; Chat-Wortlernen opt-in |
| Telegram-Abnahme | fünf reale Fehlgriffklassen read-only mit Live-Ledgerkopie und echtem Pi-Deuter bestanden |

**Am 13. Juli privilegierte Runtime abgenommen:** Die root-eigene Watchdog-Kopie unter
`/usr/local/libexec/genus` ist bytegleich mit dem geprüften Repository-Skript, der Timer ist aktiv
und die Unit führt ausschließlich diese root-eigene Kopie aus. Damit ist auch das Pause-Gate auf
dem produktiven Pi angekommen.

Die Zahlen sind ein **Abnahme-Snapshot**, keine automatisch gepflegten
Live-Metriken. Aktuelle Repository-Strukturzahlen stehen in
[generated/ATLAS_FACTS.md](generated/ATLAS_FACTS.md); die lange Baugeschichte
liegt im [history/BUILD_JOURNAL.md](history/BUILD_JOURNAL.md).

## Der aktive Fokus

### A0.3c · Runtime Prerequisite & Live Readiness

A0 bleibt nach [ADR-0009](decisions/ADR-0009-HUMAN-OWNED-CRITICAL-LANE.md) die
human-owned Critical Lane und der einzige mergefähige Produktänderungspfad.
A0.3b ist als Prototyp abgeschlossen. Der akzeptierte Pi-Kopienlauf baute G2 in
`169.746161856 s`, begrenzte die längste Schreibtransaktion auf
`1.656518293 s`, den finalen Fence auf `0.008216829 s`, Peak RSS auf
`42303488 B`, WAL auf `19994392 B` und Recovery auf `0.460784818 s`.
Alle zwölf Projektionen und neun Sequenzen stimmten; das Ledger blieb
unverändert, und Mode A benötigte keinen Fallback. Der vorausgehende rote
4096er Lauf mit `2.167361215 s` bleibt Teil der Evidenz.

Der erste A0.3c-Vollkopienlauf kombinierte erstmals die produktgroße Kopie mit
dem Concurrency-Probe und blieb ausschließlich am WAL-Budget rot: Ein bereits
vor dem Bulk-Replay geöffneter Langzeit-Reader pinnte den WAL bis auf
`3483072752 B`. Das
[technische Korrektur-Addendum](reports/2026-08-21-a0-3c-full-copy-wal-pinning-correction.md)
trennt diesen neuen Kandidaten von der unveränderten historischen A0.3b-Annahme.
Der Reader wird nun erst am `cutover_pre_commit`-Fence gebunden; das Receipt
weist diesen Scope sowie den ungepinnten Bulk-Replay fail-closed nach. Der rote
Lauf bleibt erhalten und erzwingt eine vollständig neue Drei-Lauf-Serie.

Der erste Lauf dieses WAL-korrigierten Stands bestätigte mit `156345792 B`,
dass der WAL nun unter dem `256 MiB`-Budget bleibt, stoppte aber nach einem
vollständig committeten Replay-Batch am separaten festen `0.5 s`-Writer-
Handoff-Timeout. Eine frische Diagnosekopie reproduzierte exakt
`cooperative writer admission slot timed out before a real commit`. Dieses
Subgate war unbegründet strenger als der unveränderte angenommene
`2.0 s`-Writer-Vertrag. Der nächste Kandidat verwendet daher eine Quelle der
Wahrheit für SQLite-Busy-Timeout, kooperatives Handoff und Receipt-Bindung:
exakt `2.0 s`. Der zweite rote Lauf bleibt ebenfalls erhalten; seine Folgen 2
und 3 wurden nicht gestartet und die Runtime nicht aktiviert.

Live bleibt gesperrt: Die GENUS-Python-Runtime auf dem Pi meldet SQLite 3.46.1
und damit keine bestätigte WAL-reset-sichere Version. Außerdem existiert noch
kein generation-aware Produktpfad. Ein aktualisiertes `sqlite3`-CLI allein
beweist nichts; entscheidend ist `sqlite3.sqlite_version` aus demselben
Python-Executable und Environment wie der betroffene GENUS-Prozess.

**Fertig, wenn:** Der konkrete Runtimepfad ist reproduzierbar auf eine
WAL-reset-sichere SQLite-Version gebracht und durch `sys.executable`,
`sqlite3.sqlite_version` und `sqlite3.sqlite_version_info` gebunden; die volle
GENUS-Suite und die A0.2-Golden-/SQLite-Gates sind dort grün. Danach bestehen
mindestens drei aufeinanderfolgende frische Pi-Kopienläufe mit unverändertem
Kandidaten, unveränderter Runtime und Batchgröße 3072 jedes Gate einzeln:
höchstens 2,0 s je Schreibtransaktion und finalem Fence, null Writer-Timeouts,
keine Starvation, höchstens 256 MiB RSS/WAL, höchstens 180 s Build und 10 s
Recovery, 12/12 Projektionen, 9/9 Sequenzen, unverändertes Ledger,
ausschließlich vollständig alt oder neu sowie Mode A ohne Fallback. Jeder rote
Lauf setzt die konsekutive Serie zurück. Das offene Shadow-/Scratch-
Speicherbudget wird getrennt menschlich entschieden. Erst danach darf ein
weiteres ausdrückliches Human-Go über Live-Aktivierung entscheiden.

**Heute belastbar:** Der unveränderte
[A0.3b-Prototypreport](reports/2026-08-15-a0-3b-shadow-cutover-prototype.md)
und der getrennte
[menschliche Annahmebeleg](reviews/2026-08-18-a0-3b-prototype-acceptance.md)
binden den damaligen Prototyp, seine grünen und roten Receipts sowie die
Live-Sperre. Das Korrektur-Addendum bindet beide getrennten A0.3c-Befunde; die
neue Pi-Serie des Reader-/Handoff-korrigierten Kandidaten ist noch zu
erbringen. Der bestehende produktive Replay-/
Integrity-Pfad und die Produktdatenbank bleiben unverändert. A0.2, A0.1a und
A0.1b bleiben eingefrorene Prüfinfrastruktur.

### Parallel erlaubt: read-only Beweise, kein zweiter Produktpfad

Die am 13. Juli aufgenommene H0.1-Baseline und ihre damaligen Folgetermine
bleiben im
[datierten Baseline-Report](reports/2026-07-13-h0-1-baseline/report.html)
erhalten. Dieses Dokument behauptet weder den Abschluss der Messreihe noch
aktuelle Live-Werte. Rein read-only Messungen, Sicherungen und die Untersuchung
des umstrittenen `system.load`-Beliefs dürfen fortgesetzt werden, sofern sie
keinen Produktzustand verändern und keine zweite Merge-Linie öffnen.

Der Entwickler-Loop darf daneben ausschließlich in der isolierten,
nichtproduktiven Lernlinie aus ADR-0009 üben. Ergebnisse daraus werden nicht
automatisch in `GENUS_PI_SEED` übernommen.

## Danach: die fühlbare Wachstumsachse

H1.2 bleibt sichtbar als Produktziel, ist während A0 aber als mergefähiger
Produktpfad pausiert.

### Begleiter und „Seele der Antworten“

GENUS soll Kontext nicht nur finden, sondern passend gewichten: Was weiß er?
Was ist unsicher? Was ist für Ronny **jetzt** wichtig? Die Stimme darf warm und
persönlich sein, ohne Herkunft zu erfinden oder das Modell zum Orakel zu machen.

Die erste Reifung aus echten Telegram-Zügen ist umgesetzt: unbestätigte und nächtlich
abgeleitete Episoden drängen sich nicht mehr in Sachantworten; Themenhäufigkeit wird nicht als
Interesse gespeichert; Selbst- und Habitatfragen besitzen eine datengetriebene Heimat.

Offen bleibt die größere Gedächtnisgrenze: bereits als Volltext im append-only Ledger liegende
persönliche Episoden sind durch Retraktion ausblendbar, aber nicht physisch löschbar. Ein
getrennter Memory-Vault mit Export, Retention und überprüfbarem `vergiss` gehört deshalb zu H1.

### Generalisierender Fähigkeitsloop

Eine echte Fähigkeit folgt dem ganzen Weg:

```text
Lücke erkennen → Plan entwerfen → Fähigkeit vorschlagen → Sandbox + Tests
      → menschliche Freigabe → live messen → lernen oder zurückrollen
```

Der Maßstab ist Übertragbarkeit auf verschiedenartige Aufgaben – nicht die Zahl
neuer Regexe, Sonderfälle oder Handler.

## Gerade ausdrücklich nicht

- keine Migration, Shadow-Tabellen oder Generationenmetadaten in der
  Produktdatenbank; A0.3c arbeitet ausschließlich mit Runtimebeweisen,
  Fixtures und read-only erworbenen Kopien
- keine produktive Shadow-, Catch-up-, Cutover-, Replay- oder
  Integrity-Aktivierung vor vollständig grünem A0.3c und einem weiteren
  ausdrücklichen Human-Go
- kein SQLite-Versionsnachweis nur über das CLI; maßgeblich ist die vom
  GENUS-Pythonprozess tatsächlich verwendete Bibliothek
- kein Anchor v2, keine Signatur und kein privater Signaturschlüssel auf dem Pi
- kein Production-Reseal; die angenommene Notfallausnahme ist technisch noch
  nicht erfüllbar
- keine automatische Ausführung von Vorschlägen oder Codeänderungen
- kein ungeprüftes Verschieben von quarantänisierten Ereignissen ins Produkt-Ledger
- kein stilles Löschen historischer Telegram-Logs ohne ausdrückliche Retention-Entscheidung
- kein LLM als Wahrheitsquelle
- keine neuen Produzenten ohne Eventbudget und Beobachtbarkeit
- keine Föderation oder Marktaktion vor geklärter Isolation, Löschung und Governance

## Wo eine Frage hingehört

| Frage | Dokument |
|---|---|
| Was darf der Kern? | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Welche Ereignisse gibt es? | [EVENT_CONTRACT.md](EVENT_CONTRACT.md) |
| Wie wird gebaut und geprüft? | [QUALITY.md](QUALITY.md) |
| Was kommt in welcher Abhängigkeit? | [ROADMAP.md](ROADMAP.md) |
| Warum wurde etwas so gebaut? | [history/BUILD_JOURNAL.md](history/BUILD_JOURNAL.md) |

---

**Nächster Blick:** A0.3c bestimmt und härtet die tatsächliche Python-SQLite-
Runtime, führt die vollständigen Golden-/SQLite-Gates dort aus und verlangt drei
konsekutive grüne Pi-Kopienläufe ohne Zwischentuning. Bis zu einem danach erneut
ausdrücklich gebundenen Human-Go bleibt jede Live-Aktivierung gesperrt. Der
Migration Runner bleibt bis zum vollständigen A0.3-Abschluss aufgeschoben;
read-only Messungen öffnen keinen zweiten verändernden Produktpfad.
