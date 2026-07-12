# GENUS · Jetzt

> **Status:** aktueller Arbeitsstand
>
> **Stand:** 12. Juli 2026
>
> **Verifizierte Funktionsbasis:** `8f8c577`
>
> **Zweck:** in zwei Minuten verstehen, wo GENUS steht und worauf der nächste
> saubere Schritt zielt

GENUS hat heute einen gehärteten, replaybaren Kern und läuft dauerhaft auf dem
Pi. Jetzt geht es nicht darum, möglichst viel anzubauen. Es geht darum, aus dem
stabilen Organismus einen hilfreichen Begleiter zu machen, der neue Fähigkeiten
kontrolliert **verdient**.

## Das Bild in einem Satz

> Der Boden trägt. Als Nächstes beweisen wir sein Wachstum im Dauerbetrieb,
> sichern seinen Wahrheitszeugen außerhalb des Pi und geben dem Begleiter mehr
> Zusammenhang, Stimme und generalisierendes Können.

## Was heute belastbar ist

| Bereich | Stand |
|---|---|
| Kern | gehärtet; Herkunft, Projektionen, Replay und Unsicherheit bleiben getrennt |
| Linux-Nachweis | 1.284 Tests auf dem Pi bestanden |
| Produkt-Ledger | 935.122 Ereignisse im Abnahme-Snapshot; Integrität und Siegelkette intakt |
| Betrieb | Learner, Telegram und Watchdog aktiv; Root-/User-Grenze gehärtet |
| Streudaten | historisches Root-Ledger read-only geprüft und quarantänisiert |
| Graph | Hierarchiezyklen abgewehrt; deterministische Relationen idempotent |
| Selbstbild | Identität, Mission und Habitat werden aus Code, Zielgraph und aktiven Zuständen gelesen |
| Gesprächsgrenze | spezifische Absichten fallen nicht mehr auf semantisch andere Elternantworten zurück |
| Datenschutz | Owner-Direktchat; neue Logs/Tagespuffer rohtextfrei; Nachtrotation atomar; Chat-Wortlernen opt-in |
| Telegram-Abnahme | fünf reale Fehlgriffklassen read-only mit Live-Ledgerkopie und echtem Pi-Deuter bestanden |

**Noch ausstehender privilegierter Handgriff:** Der Watchdog-Pause-Fix ist in Repository,
Tests und normalem Pi-Kern live. Seine root-eigene Laufzeitkopie unter
`/usr/local/libexec/genus` kann jedoch nur nach einer interaktiven `sudo`-Bestätigung durch den
Host-Eigentümer aktualisiert werden; der Installer ist vorbereitet und idempotent. Der atomare
Replay-Fix verhindert den beobachteten Abnahme-Wettlauf bereits unabhängig davon.

Die Zahlen sind ein **Abnahme-Snapshot**, keine automatisch gepflegten
Live-Metriken. Aktuelle Strukturzahlen stehen in
[generated/ATLAS_FACTS.md](generated/ATLAS_FACTS.md); die lange Baugeschichte
liegt im [history/BUILD_JOURNAL.md](history/BUILD_JOURNAL.md).

## Der aktive Fokus

### 1. Wachstum sichtbar machen

Ein 24/48/72-Stunden-Profil soll zeigen, welche Ereignistypen das Ledger wachsen
lassen, ob die behobene Relationsflut wirklich aus dem Messfenster fällt und
welches tägliche Budget im Normalbetrieb realistisch ist.

**Fertig, wenn:** drei vergleichbare Messpunkte, Verursacher je Ereignistyp,
WAL-Kontext und ein begründetes Betriebsbudget dokumentiert sind.

### 2. Den Wahrheitszeugen nach außen bringen

Der aktuelle Offline-Anker darf nicht nur auf demselben Pi leben wie Ledger und
Siegel. Eine getrennte, prüfbare Kopie macht Manipulation oder Verlust sichtbar.

**Fertig, wenn:** der jüngste Anker extern verwahrt, sein Abruf getestet und die
Wiederherstellungsprüfung als kurzer Ablauf dokumentiert ist.

### 3. `system.load` verstehen

Dieser Belief ist weiterhin umstritten. GENUS soll den Konflikt nicht wegmitteln,
sondern Quellen, Zeitfenster, Schwellen und Gegenbelege so aufschlüsseln, dass
eine fachliche Entscheidung möglich wird.

**Fertig, wenn:** Ursache und Semantik geklärt, der passende Fix oder die
begründete Enthaltung getestet und Replay-stabil sind.

## Danach: die fühlbare Wachstumsachse

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

**Nächster Blick:** zuerst das 24-Stunden-Wachstumsprofil. Es liefert die erste
neue Evidenz, ohne den Kern zu verändern.
