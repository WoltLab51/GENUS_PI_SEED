# GENUS · Jetzt

> **Status:** aktueller Arbeitsstand
>
> **Stand:** 14. August 2026
>
> **Verifizierte Entscheidungsbasis:** `0d9ea06` (A0.1b vollständig promoviert)
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
Der einzige aktive Produktpfad ist jetzt A0.3, das topologiegegatede Experiment
für bounded Replay und Integrity.

## Das Bild in einem Satz

> A0 ist der einzige mergefähige Produktpfad; A0.1b schützt normale Starts
> fail-closed, A0.3 entscheidet nun messbar zwischen bounded Option B und dem
> verbindlichen Shadow-Fallback C.

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

### A0.3 · Bounded Replay und Integrity

A0 bleibt nach [ADR-0009](decisions/ADR-0009-HUMAN-OWNED-CRITICAL-LANE.md) die
human-owned Critical Lane und der einzige mergefähige Produktänderungspfad.
A0.1b schützt jetzt alle normalen Startpfade mit der angenommenen
Schemaerkennung. A0.3 ersetzt als nächster Schritt vollständiges `fetchall()`
durch einen fixed-head, deterministisch geordneten und speicherbegrenzten
Eventstrom. Option B darf nur nach den vorab festgelegten Pi-, Reader-, Writer-,
WAL-, Kill- und Recovery-Gates gewählt werden; andernfalls gilt Option C mit
Shadow-Projektionen und atomarem Wechsel.

**Fertig, wenn:** Replay und Integrity arbeiten mit festem Head und begrenzten
Batches, Golden Oracle und zweiter Replay bleiben driftfrei, und die gewählte
Topologie besteht die vereinbarten Pi-Budgets sowie Reader-, Writer-, Kill- und
Recovery-Faults. Event-Log, Genesis, Epoche, Seal und Anchor bleiben unverändert;
Migration und Produkt-Cutover bleiben ausgeschlossen.

**Heute belastbar:** A0.1b ist menschlich angenommen, als PR #10 unter Python
3.11 und 3.12 grün gemergt und per Safe-Updater auf dem Pi promoviert. Der Lauf
erzeugte ein verifiziertes Backup, bestand 1.554 Tests und startete Learner und
Telegram kontrolliert neu; Doctor, Integrity und Seal blieben grün. Die echte
Produkt-DB passiert als `current`; historische und unbekannte Kopien stoppen vor
Wirkung und bleiben einschließlich Hash, mtime und Sidecars unverändert. A0.1a
und A0.2 bleiben eingefrorene Prüfinfrastruktur; A0.1b führt keine Migration aus.

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

- keine Migration und kein Produkt-Cutover in A0.3; der aktive Schritt
  entscheidet ausschließlich Replay-/Integrity-Mechanik und Topologie
- keine produktive Replay-/Integrity-Aktivierung und keine endgültige
  Topologiewahl vor unabhängiger Semantik- und Pi-Abnahme; isolierte Prototypen
  gegen Fixtures und Kopien sind Teil dieses Gates
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

**Nächster Blick:** A0.3 führt das experimentelle ADR-0007-Gate zwischen Option
B und dem verbindlichen Fallback C aus. Erst nach seiner menschlichen Abnahme
beginnt der Migration Runner ausschließlich gegen Kopien. Read-only Messungen
dürfen parallel laufen, öffnen aber keinen zweiten verändernden Produktpfad.
