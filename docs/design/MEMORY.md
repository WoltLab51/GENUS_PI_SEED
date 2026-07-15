# GENUS · Gedächtnis und Gesprächsdatenschutz

> **Status:** lebendes Design
>
> **Stand:** 13. Juli 2026
>
> **Besitzt:** Speicherarten, Abrufregeln, Tagesrhythmus, Datenschutzgrenzen und offene Löschung

## Worum es geht

GENUS soll sich an das Richtige erinnern, ohne aus jedem Gespräch eine dauerhafte Akte zu
machen. Dafür werden drei Dinge strikt getrennt:

1. **Arbeitsgedächtnis** — was für die nächsten Gesprächszüge gebraucht wird,
2. **Tagesmuster** — welche bereits erkannten Strukturen heute wiederkehrten,
3. **persönliche Episoden** — was ausdrücklich oder vorsichtig als Erinnerung bewahrt wird.

Die wichtigste Regel lautet:

> Semantische Nähe erlaubt Abruf. Sie erlaubt nicht automatisch, eine Erinnerung ungefragt
> einzublenden, eine Wiederholung als Interesse zu deuten oder Rohtext dauerhaft zu speichern.

## Die vier Leitplanken

- **Ledger ≠ Arbeitsgedächtnis.** Gesprächskontext gehört nicht automatisch in das
  unveränderliche Ereignis-Ledger.
- **Herkunft ≠ Bestätigung ≠ Oberflächenfreigabe.** Eine modellseitig bemerkte Episode darf
  auffindbar sein und trotzdem nicht ungefragt ausgesprochen werden.
- **Häufigkeit ≠ Interesse.** Ein Thema kann häufig vorkommen, weil der Mensch sich darüber
  beschwert. Die Nacht meldet Wiederkehr, aber konstruiert daraus keine Vorliebe.
- **Datenminimierung vor Retention.** Was als Struktur genügt, wird nicht zusätzlich als Frage,
  Antwort oder Telegram-Kennung gespeichert.

## Die Speicher

| Speicher | Ort | Inhalt | Lebensdauer |
|---|---|---|---|
| Arbeitsgedächtnis | Telegram-Prozess | bis zu sechs letzte Züge je Chat | bis Prozessneustart |
| Tagesstruktur | `~/.genus/chat_tag.jsonl` | Zeit, Konzept-IDs, Lesarten, Warum-Folge | bis atomare Nachtrotation |
| Korrekturbeispiele | `~/.genus/korrekturen.jsonl` | Rohtext der ausdrücklich korrigierten vorherigen Frage + Lesarten | jüngste 50; kein Alters-TTL |
| optionale Chat-Lernqueue | `~/.genus/lernwunsch.txt` | unbekannter Einzelbegriff einer ausdrücklichen Definitionsfrage | höchstens 200, bis Verarbeitung/Löschung |
| Antwortwirkungen | `response_outcome_log` aus dem Ledger | Kanal, Outcome, Lesarten, Antwortmodus, Feedback-Fähigkeit | dauerhaft / append-only, vollständig replaybar |
| explizites Antwortfeedback | `response_feedback_log` aus dem Ledger | Response-ID, Signal, optional korrigierter Intent, Quelle | dauerhaft / append-only, vollständig replaybar |
| Episodisches Gedächtnis | Relationsgraph im Ledger | Inhalt, Quelle, Zeit, erwähnte Konzepte | dauerhaft / append-only |
| bestätigte Erinnerungsaufträge | Hand-Ereignisse im Ledger | freier Erinnerungstext, Fälligkeit, Status | dauerhaft / append-only |

Der Tagespuffer enthält seit v1.17.0 **keinen Gesprächsrohtext**. Ein Eintrag sieht
schematisch so aus:

```json
{
  "ts": "…",
  "konzepte": ["Q144"],
  "warum_folge": false,
  "gelesen": ["definition"]
}
```

Frage, Antwort, Absender- und Chat-ID fehlen absichtlich. Ein bekanntes Lexem ohne echte
`expresses`-Kante wird dabei ausgelassen; seine Wortform wird nicht ersatzweise als Konzept-ID
gespeichert. Das systemd-Journal protokolliert ebenfalls nur Betriebsmetadaten wie
Nachrichtenlänge und Fehlerklasse.

## Wie eine Episode entsteht

### Bestätigt

Ein ausdrückliches „Merke dir: …“ erzeugt eine Episode mit menschlicher Herkunft. Diese
Erinnerung darf bei passendem Thema beiläufig erwähnt werden, sofern der Antwort-Würfel
Beiwerk zulässt.

### Unbestätigt

Die `tatsache`-Zelle kann eine beiläufige persönliche Aussage als modellgedeckelte Episode
festhalten. Sie bleibt bei einer ausdrücklichen Erinnerungsfrage sichtbar, wird aber niemals
ungefragt in eine Sachantwort eingewoben.

### Kein persönliches Gedächtnis

Nächtliche Themenhäufigkeit erzeugt keine Episode mehr. Historische `model:nacht`-Episoden
bleiben als alte Ledgerereignisse auditierbar, werden aber weder als vermutete persönliche
Erinnerung ausgegeben noch beiläufig eingewoben.

## Abruf

Episoden besitzen `erwaehnt`-Kanten zu bekannten Konzepten. Der Abruf läuft deterministisch:

```text
Frage → bekannte Konzepte → rückwärts verbundene Episoden → neueste passende Treffer
```

Es gibt zwei verschiedene Oberflächenverträge:

- **Expliziter Abruf:** „Was weißt du über mich?“ zeigt bestätigte und als unbestätigt
  markierte Deuter-Episoden getrennt.
- **Beiläufiges Beiwerk:** `_notiz_bezug` wählt ausschließlich eine menschlich bestätigte
  Episode. Ohne bestätigten Treffer bleibt die Antwort frei von Erinnerungseinwürfen.

Das ist bewusst strenger als der reine Graphabruf. Technische Auffindbarkeit ist keine
soziale Erlaubnis.

## Antwortwirkung ohne Gesprächsprotokoll

Der erste H1-Pilot trennt das Verstehen einer Nachricht von der Wirkung der tatsächlich
zugestellten Antwort:

```text
Antwort vorbereiten → Telegram-Send/Edit → gültiger Zustellbeleg
                                          ├─ ResponseOutcome + stabile Response-ID
                                          └─ vorbereiteten Dialogzug in RAM bestätigen

reine 👍-/👎-Nachricht, enge eindeutige Textkritik oder enger Korrektur-Cue
        → letzte feedbackfähige Response-ID → explizites Feedback-Event
```

Ohne gültigen Zustellbeleg entsteht kein Outcome und kein bestätigter Dialogzug. Die
Response-ID ist direkt die Event-ID von `response_outcome_recorded`; eine zweite zufällige
Kennung ist nicht nötig. Gespeichert werden ausschließlich typisierte Strukturfelder:

- Outcomes: `answered`, `invalid_slots`, `understood_unknown` oder `fallback`,
- Lesarten als begrenzte Intent-Tokens,
- Antwortmodus und boolesche Feedback-Fähigkeit,
- beim Feedback: `positive`, `negative` oder `intent_correction` mit Response-ID.

Frage, Antwort, Slots, Chat-/Nutzer-ID und Telegram-`message_id` gelangen weder in Outcome-
noch Feedback-Payload. Positiv bedeutet: Die Nachricht besteht, abgesehen von Leerraum und
Emoji-Varianten, vollständig aus 👍. Negativ entsteht durch reines 👎 oder eine kleine exakte
Menge deutungsfreier Textkritik wie „das passt nicht“. Eine benannte Warum-Frage gilt nur bei
exakter Übereinstimmung mit dem strukturierten Anschlussangebot. Allgemeines, nur vom Modell
gedeutetes Lob oder Kritik gilt nicht als explizites Feedback. Beim engen Korrektur-Cue
wird nur eine bekannte Raster-Absicht als `corrected_intent` übernommen; ein freier Token
bleibt aus dem Ledger. Ebenso wichtig: Ein gespeichertes Signal bewertet noch keine allgemeine
Strategie und verändert keine Gewichte. Nur der eng begrenzte Korrekturpfad beeinflusst eine
spätere Intentwahl: lokal mit gedeckelten Beispielen, remote ausschließlich mit maximal vier
bekannten Intent-Paaren ohne Beispieltext.

Feedback-Antworten sind selbst nicht feedbackfähig und werden bei einem unmittelbar
folgenden Daumen übersprungen. Eine zugestellte Ritual- oder Fehlerantwort bildet dagegen
eine Barriere: Feedback danach greift nicht durch sie hindurch auf eine ältere Sachantwort.

Die Zuordnung zur letzten zugestellten Antwort lebt derzeit nur in der sechs Züge großen
RAM-Session. Nach einem Bot-Neustart kann neues Feedback deshalb keine Antwort von davor
referenzieren. Ein späterer Randindex muss löschbar und transportnah bleiben; Telegram-
Kennungen gehören weiterhin nicht in den Kernvertrag.

## Tagesrhythmus

```text
Telegram-Zug
  ├─ Arbeitsgedächtnis im Prozess aktualisieren
  ├─ Konzepte + Lesarten + Warum-Folge sofort destillieren
  └─ nur diese Struktur in chat_tag.jsonl anhängen

Nacht
  ├─ Puffer unter gemeinsamem Lock atomar nach .nacht rotieren
  ├─ neuen leeren Puffer für gleichzeitig eintreffende Züge öffnen
  ├─ Themen und Kennzahlen rein lesend verdichten
  ├─ Morgenbericht atomar ersetzen
  └─ verarbeitete .nacht-Datei entfernen

Morgen
  └─ Wiederkehr als Tagesmuster benennen — nicht als Interesse oder Erinnerung
```

Die Nachtkonsolidierung ist seit v1.17.0 idempotent: Sie schreibt aus Themenhäufigkeit nichts
ins Ledger. Bleibt nach einem Absturz eine `.nacht`-Datei liegen, kann sie gefahrlos erneut
verarbeitet werden. Der neue Tagespuffer bleibt dabei unangetastet.

## Datenschutz: was jetzt gilt

- Neue Telegram-Journalzeilen enthalten weder Nachrichtentext noch Nutzerkennung.
- Der Tagespuffer enthält nur Struktur und wird mit Modus `0600` geschrieben.
- Die Nachtrotation und der Bot-Schreiber verwenden denselben Advisory-Lock.
- Antworten werden nicht mehr im Tagespuffer dupliziert.
- Korrekturbeispiele speichern nur ausdrücklich korrigierte Fälle, gedeckelt auf 50.
- Antwort-Outcomes und explizites Feedback speichern nur Struktur und Response-ID, keinen
  Gesprächs- oder Transporttext.
- Token und Allowlist bleiben getrennte, zugriffsgeschützte Betriebskonfiguration.
- Der selektive Remote-Deuter darf nach ausdrücklicher `0600`-Freigabe nur den aktuellen,
  höchstens 1.000 Zeichen langen Zug zusammen mit einem statischen Strukturvertrag an GitHub
  Models übertragen. Er erhält weder Verlauf noch Telegram-ID, Ledger, Antworten oder
  Korrekturbeispiele und persistiert selbst keinen Rohtext; das Journal führt nur technische
  Nutzungszahlen. Widerruf löscht die Freigabedatei, nicht erst ein Modellprofil.

Zwei begrenzte Rohtext-Ausnahmen bleiben in der Membran:

- `korrekturen.jsonl` hält die vollständige vorherige Frage eines **ausdrücklich korrigierten**
  Falls. Die Datei ist `0600`, auf 50 Einträge gedeckelt und löschbar, besitzt aber noch kein
  Alters-TTL oder eigenes Löschkommando.
- Chat-Wortlernen ist standardmäßig **aus**. Bei bewusstem
  `GENUS_CHAT_WORD_LEARNING=1` oder dem exakten, eigentümergebundenen `0600`-Marker
  `~/.genus/chat_word_learning.enabled` wird ausschließlich der unbekannte Einzelbegriff einer
  ausdrücklichen Definitionsfrage in einer `0600`-Queue gehalten und anschließend an externe
  Lexikonquellen übermittelt; erworbenes Wortwissen landet im Ledger. Freier Chat, Namen in
  Aussagen und beiläufige Großschreibung werden nicht eingereiht. Der Learner loggt
  dabei nur den Vorgang, nie die Wortform.

Daneben gibt es zwei **ausdrücklich beauftragte** dauerhafte Rohtextpfade im Kern: „Merke dir …“
legt eine persönliche Episode an; „Erinnere mich …“ legt den freien Erinnerungstext samt
Fälligkeit als bestätigten Hand-Auftrag an. Beide liegen im append-only Ledger. Das ist bewusst
enger als beiläufiger Chattext, aber noch nicht physisch löschbar.

### Historische Daten

Das Upgrade löscht nichts rückwirkend. Ältere Journale oder Legacy-Logs können noch
Gesprächsrohtext enthalten. Dazu kommen die heutigen, bewusst begrenzten Membran-Dateien für
Korrekturen und optionales Wortlernen. Eine Bestandsaufnahme darf Metadaten lesen; Löschen,
Kürzen, Aktivieren oder Archivieren ist eine bewusste Betriebsentscheidung und geschieht nicht
still bei einem Deploy.

### Ehrliche Löschgrenze

Persönliche Episoden liegen heute als Volltext in `relation_asserted`-Ereignissen;
Erinnerungsaufträge tragen ihren freien Text in Hand-Ereignissen. Eine Retraktion oder
Statusänderung entfernt die aktive Graphsicht beziehungsweise erledigt den Auftrag, aber nicht
das historische Payload aus dem append-only Ledger oder aus Backups. GENUS besitzt deshalb noch
kein ehrliches „Vergiss mich physisch“.

Die Zielarchitektur dafür ist ein isolierter, verschlüsselbarer und tatsächlich löschbarer
Memory-Vault pro persönlichem Kern. Das Ledger soll dann höchstens eine inhaltsfreie Auditspur
tragen. Migration, Export, Retention und Löschbestätigung gehören gemeinsam in diesen Schritt;
ein bloßes Verstecken in der Projektion reicht nicht.

## Prüfverträge

Die Tests pinnen insbesondere:

- modell- und nachtseitige Episoden erscheinen nicht ungefragt,
- bestätigte menschliche Episoden dürfen weiter beiläufig helfen,
- neue Tagesdateien enthalten keine Frage und keine Antwort,
- Journalmeldungen enthalten weder Rohtext noch Absender-ID,
- nur belegte Zustellungen erzeugen ein Outcome und bestätigen einen vorbereiteten
  RAM-Dialogzug,
- Outcome- und Feedback-Payloads akzeptieren exakt ihre datensparsamen Felder,
- Feedback verweist nur auf eine vorhandene, feedbackfähige Response-ID,
- Feedback-Acks werden übersprungen; Ritual- und Fehlerantworten stoppen den Rückbezug,
- Replay rekonstruiert Outcome- und Feedback-Projektionen ohne Drift,
- Nachtrotation nutzt Lock + atomaren Rename und kein nachträgliches Truncate,
- wiederholte Konsolidierung erzeugt keine Dauererinnerung.

## Nächste Reifestufe

1. Löschbaren persönlichen Memory-Vault entwerfen und migrieren.
2. `vergiss`, Export und Retention mit überprüfbarer Bestätigung bauen.
3. Die vorhandenen Antwort-Outcomes und expliziten Feedbacklinks über ein kuratiertes
   Alltagstestset auswerten; noch keine automatische Strategiegewichtung.
4. Eine löschbare Edge-Outbox samt Randindex entwerfen: Sie soll nach bereits belegter
   Zustellung eine fehlgeschlagene Outcome-Persistenz wiederholen und Feedbackbezug über
   Bot-Neustarts erhalten, ohne Telegram-Kennungen oder Gesprächsinhalt in den Kern zu ziehen.
5. Relevanz aus Zeit, Beziehung, Quelle und Gesprächsziel gewichten — nicht aus bloßer
   Wortwiederholung.

Verwandte Verträge: [ARCHITECTURE.md](../ARCHITECTURE.md),
[SECURITY_MODEL.md](../SECURITY_MODEL.md) und [ROADMAP.md](../ROADMAP.md).
