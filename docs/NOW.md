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
Der einzige aktive Produktpfad ist jetzt A0.3b: versionierte
Shadow-Projektionen, Catch-up und atomarer Cutover werden zunächst ausschließlich
als isolierter Prototyp gegen Fixtures und Datenbankkopien bewiesen.

## Das Bild in einem Satz

> A0 ist der einzige mergefähige Produktpfad; A0.3a hat Option B als
> Live-Topologie am Writer-Gate verworfen, und A0.3b muss nun Option C innerhalb
> der angenommenen Pi-Budgets beweisen.

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

### A0.3b · Shadow Generation & Atomic Cutover Prototype

A0 bleibt nach [ADR-0009](decisions/ADR-0009-HUMAN-OWNED-CRITICAL-LANE.md) die
human-owned Critical Lane und der einzige mergefähige Produktänderungspfad.
A0.1b schützt alle normalen Startpfade mit der angenommenen Schemaerkennung.
A0.3a ist menschlich angenommen: Der bounded Eventstrom senkte auf der Pi-Kopie
den Peak RSS auf 38.387.712 B, doch die einzelne Option-B-Transaktion dauerte
106,775489 s und ließ den realen Writer nach 5,003508 s timeouten. Die
verbindliche Writer-Grenze beträgt 2,0 s ohne Timeout oder Starvation. Option B
ist deshalb für den konkurrierenden Livebetrieb verworfen und bleibt nur für
Wartung mit gestoppten Writern, Kopien, Migrationstests und Offline-Prüfungen
zulässig.

**Fertig, wenn:** Eine aktive Generation G1 und eine versionierte Shadow-
Generation G2 bestehen gleichzeitig; G2 wird bounded bis zu einem festen Head
aufgebaut, holt neue Events ohne Writer-Starvation nach und wechselt nach einer
höchstens 2,0 s langen finalen Writer-Grenze atomar. Golden Oracle und alle zwölf
Projektionsdigests stimmen, Crash/Reopen ergibt ausschließlich vollständig alt
oder vollständig neu, und die angenommenen Grenzen von 256 MiB Peak RSS,
180 s Gesamtbuild, 256 MiB WAL und 10 s Recovery werden eingehalten. Event-Log,
Genesis, Epoche, Seal und Anchor bleiben unverändert.

**Heute belastbar:** A0.3a Measurement Harness und Pi-Baseline sind menschlich
angenommen; [Entscheidungsbeleg](reviews/2026-08-14-a0-3a-topology-decision.md)
und [Messreport](reports/2026-08-14-a0-3a-measurement-harness-baseline.md)
binden Budgets und die Auswahl von Option C. Der bestehende produktive Replay-/
Integrity-Pfad bleibt unverändert. A0.1b ist menschlich angenommen, als PR #10 unter Python
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
- keine produktive Shadow-, Replay- oder Integrity-Aktivierung vor dem
  vollständigen A0.3b-Prototyp und einem zweiten ausdrücklichen Human-Go;
  Option C ist ausgewählter Kandidat, noch keine Live-Implementierung
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

**Nächster Blick:** A0.3b vergleicht Catch-up mit kurzer finaler Fence,
begrenztes Dual-Write oder eine andere Generationstechnik, ohne eine davon
vorwegzunehmen. Erst der innerhalb aller Budgets grüne Shadow-/Cutover-Prototyp
und ein zweites Human-Go dürfen einen späteren Produkt-Cutover vorbereiten. Der
Migration Runner bleibt bis zum vollständigen A0.3-Abschluss aufgeschoben.
Read-only Messungen dürfen parallel laufen, öffnen aber keinen zweiten
verändernden Produktpfad.
