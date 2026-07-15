# GENUS · Antwortqualität und Alltagsprobe

> **Status:** lebendes Design · dem kanonischen [Qualitätsvertrag](../QUALITY.md) nachgeordnet
>
> **Stand:** 13. Juli 2026
>
> **Besitzt:** hermetische Antwortabnahme, harte Dimensionen, menschliche Reviews und
> Hash-Gültigkeit

## Das Ergebnis zuerst

GENUS besitzt jetzt eine wiederholbare Abnahmefläche für alltägliche Antworten:

- **17 synthetische Dialogfälle**,
- **85/85 bestandene harte Verträge**,
- **2/17 menschlich akzeptierte Antworten**.

Diese Zahlen gehören zusammen. Die automatische Seite beweist bereits viel über Treue und
Ehrlichkeit. Sie kann aber nicht beweisen, dass eine Antwort natürlich klingt, genügend
Tiefe besitzt oder im Alltag wirklich hilft. Darum bleibt die Suite offen, bis Ronny den
exakten Wortlaut geprüft hat.

```text
synthetischer Fall
      ↓
echter GENUS-Antwortpfad ──→ harte Verträge: 85/85
      ↓ exakter Wortlaut
menschliche Prüfung von Ton + Nutzen: 2/17
      ↓ nur mit passenden Fall- und Antwort-Hashes
akzeptiert · nacharbeiten · bei Änderung automatisch veraltet
```

## Was „hermetisch“ bedeutet

Jeder Fall beginnt in einer frischen SQLite-In-Memory-Datenbank. Die Suite sät nur die
Relationen, die der jeweilige synthetische Dialog braucht, und reicht modellartige Lesarten
als feste Testdaten ein. Danach läuft der wirkliche Antwortpfad mit `AnswerDraft`,
`DialogueFrame` und Renderer.

Die Probe verwendet ausdrücklich:

- **keine Live-Datenbank und keine Kopie des Pi-Ledgers**,
- **keinen Telegram- oder Chattext**,
- **kein Netzwerk**,
- **kein Deuter-, Stimmen- oder Judge-LLM**,
- **kein Feedback als Belohnung oder Strategiegewicht**.

Damit sind die Ergebnisse lokal und auf dem Pi reproduzierbar, ohne private Gespräche zur
Testware zu machen. Die sichtbaren Fragen und Antworten stammen vollständig aus der Suite.

## Die zwei Schlüssel

### 1. Harte Verträge

Automatisch prüfbar ist, ob GENUS seinen epistemischen und dialogischen Vertrag einhält:

| Dimension | Verträge | Was sie festhalten |
|---|---:|---|
| Fakten- und Richtungstreue | 17 | Claims, gerichtete Beziehungen, Reihenfolge und unveränderte Kerne |
| Nichtwissen und Unsicherheit | 21 | Enthaltung, Fallback, fehlende Slots und offene Welt statt erfundenem Nein |
| Herkunft und Nachvollziehbarkeit | 5 | Quellen und belegte Herleitungen |
| Modelltransparenz | 5 | Herkunft einer simulierten Modell-Lesart und dosierte Offenlegung |
| Dialoganschluss | 11 | Anker, Rückfragen, Rückbezüge, Korrektur und Anschlussangebote |
| Mehrteilige Antworten | 3 | ruhige Komposition und konservatives Gesamt-Outcome |
| Bekannte Alltagsreibungen | 6 | keine internen IDs, CLI-Tipps oder ungefragten Auditvorträge |
| Datensparsamkeit | 17 | pro Fall gelangt kein synthetischer Dialogrohtext ins Ereignis-Ledger |
| **Gesamt** | **85** | **derzeit vollständig grün** |

Ein grüner Vertrag bedeutet nicht automatisch „gute Antwort“. Er bedeutet genau das, was
seine Beschreibung behauptet – nicht mehr.

### 2. Menschliche Abnahme

Ton und Nutzen werden je Fall getrennt bewertet:

| Wert | Bedeutung |
|---|---|
| `traegt` | funktioniert im Alltag in dieser Form |
| `holprig` | Substanz stimmt, Form oder Nutzen brauchen Schärfung |
| `unbrauchbar` | trägt als Antwort nicht |

Ein Fall ist nur `accepted`, wenn **beide** Werte `traegt` sind und beide Hashes passen.
`holprig` oder `unbrauchbar` ergibt `needs_work`. Ohne Review bleibt er `review_pending`;
nach einer Änderung mit alten Hashes wird er `review_stale`.

Es gibt bewusst keine gewichtete Summe und keinen Gesamtscore. Eine schöne Begrüßung darf
keine falsche Tatsachenbehauptung ausgleichen, und 85 grüne Verträge dürfen keine holprige
Gesprächsform schönrechnen.

## Die 17 Situationen

| Fälle | Geprüfte Alltagsspanne |
|---|---|
| 01–04 | natürlicher Gruß; belegte, schwache und unabhängig bestätigte Definition |
| 05–07 | direkte, transitive und in offener Welt unbekannte Beziehung |
| 08–11 | Nichtverstehen, fehlender Pflichtslot, freie graphgeprüfte Deutung, noch fehlende Fähigkeit |
| 12–14 | Warum-Rückbezug, Einlösen eines Anschlussangebots, Rückgriff „von vorhin“ |
| 15–16 | mehrere Sprechhandlungen und ein Mehrsegment-Zug mit ungelöstem Teil |
| 17 | enge Intent-Korrektur ohne gespeicherten Rohtext |

Die Fallquelle ist `genus.alltagsprobe.ALLTAGSFAELLE`. Eine Änderung an Frage, Fixture,
Gate, Zweck oder menschlicher Prüffrage ändert den Fall-Fingerprint.

Die Fälle 03 und 04 prüfen ausschließlich, wie eine **bereits vorhandene** schwache oder
unabhängig bestätigte Bedeutung ausgesprochen wird. Sie prüfen nicht den asynchronen
Telegram-Lernlauf. Dessen eigener Vertrag lautet: auffindbar ist noch nicht erklärbar;
`learned` gilt erst, wenn der normale Definitionspfad eine Bedeutung oder eine verständlich
benannte Einordnung ausgeben kann. `queued` und `learning` werden vor dem Deuter-Lauf
beantwortet, damit ein gleichzeitig arbeitender Learner keinen veralteten Antwortentwurf
erzeugen kann.

## Benutzen

```bash
# Der schnelle, harte CI-Vertrag
genus alltagsprobe --contracts-only

# Wortlaut, Prüffrage und kurze Hashes pro Fall
genus alltagsprobe --details

# Vollständiger Reviewbericht samt ausfüllbaren Hash-Vorlagen
genus alltagsprobe --markdown

# Vollständiges maschinenlesbares Ergebnis
genus alltagsprobe --json-output
```

Die angenehmste Arbeitsansicht ist der
[generierte Bericht](../generated/ANTWORTQUALITAET.md). Er zeigt jeden synthetischen Dialog,
seine Verträge, die menschliche Prüffrage und eine kopierbare Reviewvorlage mit vollständigen
Hashes.

Der aktuelle Lauf zeigt:

```text
[ALLTAG] 17 Fälle · harte Verträge 85/85 · menschlich akzeptiert 2/17
```

| Exitcode | Vertrag |
|---:|---|
| `0` | harte Verträge grün und alle Fälle menschlich akzeptiert; mit `--contracts-only` genügt die harte Seite |
| `1` | mindestens ein harter Vertrag verletzt |
| `2` | harte Seite grün, menschliche Abnahme aber noch offen, veraltet oder nicht tragend |

Darum endet `genus alltagsprobe` aktuell mit 2 und
`genus alltagsprobe --contracts-only` mit 0. Das ist die sichtbare Grenze zwischen
messbarer Korrektheit und menschlicher Wirkung.

## Einen Fall bewerten

1. Den [generierten Bericht](../generated/ANTWORTQUALITAET.md) öffnen oder
   `genus alltagsprobe --details` ausführen.
2. Frage, Antwort und menschliche Prüffrage lesen.
3. Ton und Nutzen unabhängig bewerten.
4. Die vollständige Vorlage aus dem Markdownbericht in
   [`ALLTAGSPROBE_V1.json`](../reviews/ALLTAGSPROBE_V1.json) übernehmen und beide Werte
   bewusst setzen. Alternativ liefert `--json-output` die vollständigen Hashes.
5. Den Standardaufruf erneut ausführen. Er prüft Review-Schema und Hashbindung.

Eine Reviewzeile besitzt exakt diese acht Felder:

```json
{
  "case_id": "05-beziehung-direkt",
  "case_fingerprint": "<vollständiger SHA-256 des Falls>",
  "response_sha256": "<vollständiger SHA-256 der Antwort>",
  "ton": "traegt",
  "nutzen": "traegt",
  "reviewer": "ronny",
  "reviewed_at": "2026-07-13T12:00:00+02:00",
  "note": "Direkt und verständlich."
}
```

Notizen beschreiben nur den synthetischen Wortlaut. Private Gesprächsinhalte gehören weder
in die Suite noch in die Reviewdatei. Für einen Probe- oder Arbeitsstand kann mit
`--reviews PFAD` eine andere Datei gelesen werden.

## Wann die Suite wachsen darf

Ein neuer Fall braucht eine beobachtete Antwortklasse oder eine klar benannte
Vertragslücke – nicht nur eine weitere Formulierung desselben Beispiels. Er bringt mit:

- eine synthetische, minimale Fixture,
- eine lesbare Alltagssituation,
- harte Gates mit präziser Aussage,
- eine menschliche Prüffrage,
- einen Gegenfall, falls eine Richtung oder Trust Boundary kippen kann.

Nach jeder Antwortänderung gilt: harte Probe laufen lassen, veraltete Reviews ansehen,
Wortlaut neu bewerten. Reviews werden niemals in Modellgewichte, Antwortstrategie oder
Wissensgraph zurückgeschrieben. Erst ein eigener, späterer Governance-Vertrag dürfte aus
kuratierter Evaluation eine begrenzte Strategiewahl machen.

## Verwandte Verträge

- [Quality](../QUALITY.md) — kanonische Bau- und Abnahmegates
- [H1-Roadmap](../ROADMAP.md#h1--der-alltagstaugliche-begleiter) — Definition of Done
- [H1-Response-Loop-Bericht](../reports/2026-07-13-h1-response-loop.md) — Stand des Piloten
- [Gedächtnis und Gesprächsdatenschutz](MEMORY.md) — Grenze zum persönlichen Kontext
- [Alltagsprobe-Reviews](../reviews/ALLTAGSPROBE_V1.json) — hashgebundene menschliche Wertungen
