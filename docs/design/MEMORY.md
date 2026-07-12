# GENUS · Gedächtnis und Gesprächsdatenschutz

> **Status:** lebendes Design
>
> **Stand:** 12. Juli 2026
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
| optionale Chat-Lernqueue | `~/.genus/lernwunsch.txt` | unbekannte einzelne Wortformen aus Chattext | höchstens 200, bis Verarbeitung/Löschung |
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
- Token und Allowlist bleiben getrennte, zugriffsgeschützte Betriebskonfiguration.

Zwei begrenzte Rohtext-Ausnahmen bleiben in der Membran:

- `korrekturen.jsonl` hält die vollständige vorherige Frage eines **ausdrücklich korrigierten**
  Falls. Die Datei ist `0600`, auf 50 Einträge gedeckelt und löschbar, besitzt aber noch kein
  Alters-TTL oder eigenes Löschkommando.
- Chat-Wortlernen ist standardmäßig **aus**. Bei bewusstem
  `GENUS_CHAT_WORD_LEARNING=1` werden unbekannte einzelne Wortformen in einer `0600`-Queue
  gehalten und anschließend an externe Lexikonquellen übermittelt; erworbenes Wortwissen
  landet im Ledger. Namen, Diagnosen oder andere sensible Wörter dürfen deshalb nicht ohne
  diese ausdrückliche Datenschutzentscheidung automatisch gelernt werden. Der Learner loggt
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
- Nachtrotation nutzt Lock + atomaren Rename und kein nachträgliches Truncate,
- wiederholte Konsolidierung erzeugt keine Dauererinnerung.

## Nächste Reifestufe

1. Löschbaren persönlichen Memory-Vault entwerfen und migrieren.
2. `vergiss`, Export und Retention mit überprüfbarer Bestätigung bauen.
3. Antwort-Outcomes (`answered`, `invalid_slots`, `understood_unknown`, `fallback`) getrennt
   messen, damit eine gelesene Absicht nicht fälschlich als gelöste Fähigkeit gilt.
4. Relevanz aus Zeit, Beziehung, Quelle und Gesprächsziel gewichten — nicht aus bloßer
   Wortwiederholung.

Verwandte Verträge: [ARCHITECTURE.md](../ARCHITECTURE.md),
[SECURITY_MODEL.md](../SECURITY_MODEL.md) und [ROADMAP.md](../ROADMAP.md).
