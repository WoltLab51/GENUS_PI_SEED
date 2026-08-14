# GENUS · Jetzt

> **Status:** aktueller Arbeitsstand
>
> **Stand:** 14. August 2026
>
> **Verifizierte Entscheidungsbasis:** `21fb237` (A0.2 vollständig promoviert)
>
> **Letzter hier belegter Laufzeit-Snapshot:** 13. Juli 2026 auf `068f0ca`
>
> **Zweck:** in zwei Minuten verstehen, wo GENUS steht und worauf der nächste
> saubere Schritt zielt

Der zuletzt hier belegte Pi-Snapshot zeigt einen gehärteten, replaybaren Kern im
Dauerbetrieb. Seit dem 9. August besitzt GENUS außerdem angenommene A0-Verträge
für Schema, Golden Ledger, Replay, externe Anchors und kritische
Änderungsautorität. A0.2 ist seit dem 14. August vollständig abgeschlossen:
Golden JSONL, unabhängiges Replay-Oracle und eine echte historische
SQLite-Fixture sind menschlich angenommen, auf GitHub gemergt und auf dem Pi
geprüft. Der einzige aktive Produktpfad ist jetzt A0.1a, die ausschließlich
read-only arbeitende Schemaerkennung.

## Das Bild in einem Satz

> A0 ist der einzige mergefähige Produktpfad; A0.1a erkennt bekannte, aktuelle
> und unbekannte Schemafassungen fail-closed, ohne die Datenbank zu verändern.

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

### A0.1a · Read-only Schemaerkennung

A0 bleibt nach [ADR-0009](decisions/ADR-0009-HUMAN-OWNED-CRITICAL-LANE.md) die
human-owned Critical Lane und der einzige mergefähige Produktänderungspfad.
A0.2 liefert dafür jetzt die unabhängige Beweisbasis: Golden Corpus,
Replay-Oracle und eine aus dem echten Commit `2bf67e6` konservierte historische
SQLite-Speicherform. A0.1a darf diese Materialien nur lesen und klassifizieren.

**Fertig, wenn:** `genus db status` bekannte historische, aktuelle, unbekannte
und unvollständige Schemaformen reproduzierbar unterscheidet; Statusabfrage und
normaler Dienststart dabei weder Datei, Schema noch Ledger verändern; unbekannte
oder migrationspflichtige Zustände verständlich und fail-closed stoppen; und
Tests die Byteidentität vor und nach jeder Erkennung beweisen.

**Heute belastbar:** A0.2 ist vollständig grün. Golden Corpus und Oracle sind
hashgebunden und menschlich angenommen; die historische SQLite-Fixture bindet
Commit, Schemahash, Binärhash, Inventar und read-only Eventstromgleichheit. Der
[Golden-Annahmebeleg](reviews/2026-08-13-a0-2-golden-ledger-acceptance.md) und
der [SQLite-Annahmebeleg](../tests/fixtures/historical_sqlite_v1/HUMAN_REVIEW.md)
dokumentieren die beiden Human Gates. GitHub-CI bestand unter Python 3.11 und
3.12; auf dem Pi bestanden beide A0.2-Gates gemeinsam mit 29 Tests.

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

- keine Migration in A0.1a; Schemaerkennung bleibt strikt read-only
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

**Nächster Blick:** A0.1a baut ausschließlich die read-only Schemaerkennung und
die fail-closed Startgrenze. Danach folgt das experimentelle ADR-0007-Gate
zwischen Option B und dem verbindlichen Fallback C; erst anschließend beginnt
der Migration Runner nur gegen Kopien. Read-only Messungen dürfen parallel
laufen, öffnen aber keinen zweiten verändernden Produktpfad.
