# ADR-0006 — Golden Ledger and Independent Replay Oracle

> **Status:** accepted · **Datum:** 2026-08-09
>
> **Decision Owner:** Ronny · **Umsetzung:** erster A0-Schritt, noch nicht begonnen
>
> **Quelle:** D-A0.2 im [A0 Decision Packet](../reports/2026-08-09-a0-decision-packet.md)

## Kontext

CI und Standardtests beginnen heute mit frischen temporären Datenbanken.
Verteilte Tests prüfen einzelne Legacy-, Seal-, Replay- und Lifecycle-Fälle,
aber kein gemeinsames historisches Ledger mit nichtleerem Legacy-Präfix,
versiegeltem Tail und unabhängig festgeschriebenen Projektionserwartungen. Ein
Oracle, das ausschließlich vom aktuellen Projektorcode erzeugt wird, könnte mit
demselben Fehler driften wie die Implementierung.

## Entscheidung

GENUS erhält einen datenschutzfreien, handgeprüften Golden-Ledger-Corpus mit
unabhängigem, versioniertem Replay-Oracle.

Die angenommene Repräsentation präzisiert Option C aus dem Decision Packet:

1. **Kanonische Eventdarstellung:** menschenlesbares, diffbares JSONL mit festen
   IDs, Zeitstempeln, Payloads und Seal-Feldern.
2. **Statisches Oracle-Manifest:** bindet Fixture-Version, Provenienz,
   Eventfolge, Präfix/Genesis, Epoche, Head, Seal-/Integrity-Erwartung sowie
   normalisierte Projektionen und Digests.
3. **Temporäre Replay-DB:** wird deterministisch aus JSONL und dem festgelegten
   aktuellen Fixture-Schema erzeugt; jeder Test arbeitet auf einer Kopie.
4. **Historische SQLite-Altfixture:** ergänzt den Corpus für echte
   Schema-Migrationstests, weil JSONL allein Tabellen, Trigger, Indizes und
   historische Schemaform nicht beweist.
5. Fixture und Oracle dürfen nicht ausschließlich durch den aktuell geprüften
   Runtime-/Projektorcode erzeugt oder aktualisiert werden.

Das Manifest bindet mit SHA-256 mindestens die kanonische JSONL-Datei, seine
eigene Formatversion sowie Digest und erwarteten Schema-Fingerprint jeder
statischen historischen SQLite-Altfixture. Ein read-only kanonisierter Export
des Eventstroms aus der Altfixture muss denselben Eventdigest wie die
zugeordnete JSONL-Historie ergeben. Temporäre Current-Schema-SQLite-Dateien sind
nur deterministische Derivate; ihr Import-Receipt bindet JSONL-Digest,
Fixture-Schemaversion und resultierenden Eventdigest. So bleiben Eventwahrheit,
historische Schemaform und Oracle getrennt prüfbar, ohne als ungebundene
Parallelquellen zu driften.

## Pflicht-Coverage

Der erste Corpus deckt mindestens ab:

- mehrere unversiegelte Legacy-/Prä-Epochen-Events und einen nichtleeren
  Legacy-Präfix;
- ein korrektes `ledger_epoch_opened` mit Genesis-Digest über den Präfix;
- einen versiegelten Tail;
- projizierte und bewusst rohe Eventtypen;
- `supported`, `contested` und `superseded` Beliefs;
- Relation, Inquiry, Experience, Proposal und Governance;
- mindestens einen terminalen Lebenszyklus;
- einen prüfbaren historischen Anchor;
- ausschließlich synthetische, nicht persönliche und nicht produktive Daten.

Das Oracle bindet mindestens:

- normalisierte erwartete Daten und stabilen Digest jeder Projektion;
- einen Gesamtdigest;
- Eventzahl, IDs und Reihenfolge;
- Präfix-, Genesis-, Epoch-, Head- und Seal-Status;
- erwartete Integrity- und Anchor-Ergebnisse;
- zweimaligen Replay mit identischem Ergebnis und null neuen Events;
- negative Tamper-Fälle für Präfix, Tail, Payload, Seal und Oracle.

Kanonisierung definiert Tabellen-/Spaltenreihenfolge, SQLite-Typen, `NULL`,
Text, Zeit, JSON, Floatdarstellung und Digestalgorithmus. Eine legitime
Erwartungsänderung ist eine eigene menschengeprüfte Oracle-Änderung; ein
Runtime-Patch darf sie nicht beiläufig ersetzen.

## Erwogene Alternativen

- **Nur frische CI-Datenbanken:** als Komponentenbeleg erhalten, aber nicht als
  Golden-Nachweis ausreichend.
- **Fixture und Erwartungen vollständig aus aktueller Runtime:** abgelehnt,
  weil Eingabe und Erwartung gemeinsam driften können.
- **Nur fertige SQLite-Datei:** nicht als alleinige kanonische Darstellung;
  für historische Migrationen bleibt eine kleine statische Altfixture nötig.
- **Signiertes Manifest sofort:** zurückgestellt, bis ADR-0008 Signatur und Key
  Custody implementierbar spezifiziert. Digest- und Reviewbindung genügt für den
  ersten Corpus.

## Ownership und Änderung

Corpus Owner, Datenschutzprüfung und Oracle-Review sind menschliche Rollen.
Sie werden vor Erzeugung des ersten Artefakts namentlich dokumentiert; der
Runtime-Patch unter Test darf keine dieser Freigaben erteilen. Vor der ersten
Fixture werden außerdem Kanonisierungsregeln, Digestalgorithmus,
Coverage-Matrix und Änderungsfreigabe als menschengeprüfter Vertrag
festgeschrieben. Alte Fixture-Versionen bleiben erhalten. Neue Event-/Schema-
Ären werden additiv versioniert; ein grüner Runtime-Test darf die
Oracle-Freigabe nicht ersetzen.

## Konsequenzen

- ADR-0006 ist der erste aktive A0-Implementierungsschritt.
- ADR-0007 wird gegen dieselbe Fixture und alle Projektionen gemessen.
- ADR-0005-Migrationen sind erst abnahmefähig, wenn
  Altfixture → Migration → Replay ×2 → Oracle grün ist.
- Die Fixture darf keine Produktdatenbank, Chatdaten oder echten Schlüssel
  enthalten.
- Die Implementierung bleibt human-owned critical scope nach ADR-0009.

## Noch nicht umgesetzt

Dieser ADR erzeugt noch kein JSONL, Manifest, SQLite-Artefakt, Importwerkzeug,
CI-Gate oder Signatur. Namen der menschlichen Rollen, konkrete
Kanonisierungswerte und initiale Erwartungen werden in einem gesondert
geprüften Eingangskontrakt vor Artefakterzeugung festgehalten; die
Implementierung unter Test darf diesen Vertrag nicht selbst genehmigen.
