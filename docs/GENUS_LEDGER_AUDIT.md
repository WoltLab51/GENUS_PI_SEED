# GENUS Ledger Audit

Stand: v1.1

## Ergebnis

GENUS hat ein append-only Ledger fuer normale Schreibpfade, einen
deterministischen Replay-Vertrag und seit v1.1 eine lokale Seal-Kette ab einem
expliziten `ledger_epoch_opened`-Event. Das schuetzt gegen versehentliche
Updates, Deletes, Projektiondrift und nicht nachversiegelte Manipulation. Es ist
aber noch nicht manipulations-evident gegen einen adaptiven Angreifer mit vollem
lokalen SQLite-Dateizugriff.

Die ehrliche Kurzform:

- Heute: tamper-resistant fuer App-Zugriffe, contract-detecting fuer malformed
  events und seal-detecting fuer nicht nachversiegelte Aenderungen.
- Noch nicht: tamper-evident gegen adaptive lokale Re-Sealing-Angriffe.
- Erst mit externem Anchor: belastbare Tamper-Evidence gegen einen Angreifer,
  der die lokale DB kontrolliert.

## Was Bewiesen Ist

| Eigenschaft | Mechanismus | Status |
| --- | --- | --- |
| `event_log` ist append-only im normalen Pfad | SQLite-Trigger gegen `UPDATE` und `DELETE` | gebaut und getestet |
| Projektionen sind rebuildbar | `event_router.replay()` leert Projektionen und spielt Events neu ab | gebaut und getestet |
| `event_log` bleibt bei Replay unveraendert | `integrity.check()` replayt auf In-Memory-Kopie | gebaut und getestet |
| Confidence wird nicht gespeichert | Schema- und Integrity-Checks verbieten `confidence`-Spalten | gebaut und getestet |
| Kaputte Events fallen auf | Event-Contract prueft Pflichtfelder und JSON | gebaut und getestet |
| Lokale Seal-Kette | `prev_seal` + `seal` ab `ledger_epoch_opened` | gebaut und getestet |
| Legacy-Prefix ist gepinnt | Genesis-Digest im Epoch-Event | gebaut und getestet |

## Was Nicht Bewiesen Ist

Ein lokaler Angreifer mit Schreibzugriff auf die SQLite-Datei kann Trigger
droppen, wohlgeformte Events aendern, die lokale Seal-Kette neu berechnen und
Projektionen neu aufbauen. Ohne extern verankerten Head kann GENUS nicht
beweisen, dass die lokale Historie unveraendert ist. Tail-Truncation ist lokal
ebenfalls nicht beweisbar, wenn kein externer Head existiert.

Das ist kein aktueller Funktionsbug. Es ist die wichtigste Integritaetsgrenze
fuer spaetere Sync-, Foederations- und Anchor-Schritte.

## Bedrohungsmodell

| Mechanismus | Erkennt versehentliche Korruption | Erkennt faulen lokalen Angreifer | Erkennt adaptiven lokalen Angreifer | Benoetigt externen Anchor |
| --- | --- | --- | --- | --- |
| Append-only Trigger | ja | teilweise | nein | nein |
| Event-Contract | ja, wenn malformed | teilweise | nein, wenn wohlgeformt | nein |
| Lokale Hash-Chain ohne Anchor | ja | ja, wenn nicht neu gesealed | nein | nein |
| Hash-Chain mit externem Anchor | ja | ja | ja, ab Anchor-Zeitpunkt | ja |

## Umsetzung In v1.1

Ledger-Sealing liegt in `event_log`, nicht in einer Sidecar-Tabelle. Ein Seal
ist eine historische Festlegung zum Append-Zeitpunkt und gehoert zum Event.
Eine Sidecar-Tabelle wuerde eine zweite Wahrheit schaffen, die selbst wieder
append-only, geordnet und konsistent gehalten werden muesste.

Der gebaute Pfad:

1. `ALTER TABLE event_log ADD COLUMN prev_seal TEXT`
2. `ALTER TABLE event_log ADD COLUMN seal TEXT`
3. Bestehende Events bleiben unveraendert und behalten `NULL` in beiden Spalten.
4. Ein neues `ledger_epoch_opened`-Event schreibt einen Genesis-Digest ueber
   den Legacy-Prefix.
5. Ab diesem Event schreibt `ledger.append()` `prev_seal` und `seal` in
   demselben `INSERT`.
6. `integrity.check()` prueft Prefix-Digest, Chain-Kontinuitaet und Seal.
7. `genus ledger head` gibt den aktuellen Seal fuer spaetere externe Anchors
   aus.

Wichtig: Bestehende Events werden nicht per `UPDATE` nachversiegelt. Das wuerde
die append-only-Regel brechen. Der Genesis-Digest ist die ehrliche Grenze
zwischen Legacy-Prefix und gesealter Epoche.

## CI-Haertung In v1.0.1

Der CI-Workflow prueft:

- `python -m pytest`
- `genus replay`
- `genus integrity check`
- keine LLM-Imports
- keine HTTP-/Netzwerk-Imports
- seit v1.1: `genus ledger seal-init`, `genus ledger head`,
  `genus ledger verify` und `integrity check` nach Sealing

Zusaetzlich gibt es einen Negativtest: ein bekannt kaputtes
`observation_created`-Event muss `integrity.check()` fehlschlagen lassen. Damit
ist die Contract-Erkennung nicht nur ein manueller Audit-Fund, sondern Teil der
regulaeren Qualitaetssicherung.
