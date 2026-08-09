# A0 Foundation Audit

## 1. Status / Snapshot / geprüfter Commit

**Status:** datierter, nicht normativer Befund; keine Implementierung und keine
Priorisierungsentscheidung.

**Auditdatum:** 2026-08-09 (Europe/Berlin)

**Primärer Prüfgegenstand:** der lokale, zu Beginn saubere Worktree bei
`cadcda834a5d8e61be357f90b0db11c284ea9a9a` (`cadcda8 add safe Pi update and
remote access runbook`). Die read-only abgefragten GitHub-Heads waren zu diesem
Zeitpunkt davon getrennte Momentaufnahmen: `GENUS_PI_SEED/main` bei
`1a73db0db72ebf57f1611b42b97a3e7bef9ec404` und `GENUS_PI_STATUS/main` bei
`f6ee537a7e2dcf97b5a358851573ac3ad5bd9a61`.

**Scope-Garantie:** Es wurde keine produktive Datenbank geöffnet. Es wurde keine
Migration und kein Reseal ausgeführt, keine Seal-Epoche geöffnet, kein Anchor
erzeugt oder ersetzt, kein Schlüssel gelesen oder erzeugt und keine GitHub-
Einstellung verändert. Tests liefen ausschließlich mit ihren temporären bzw.
synthetischen Datenbanken.

## 2. Executive Summary

Das heutige Fundament besitzt brauchbare lokale Schutzmechanismen: append-only
Trigger, eine deterministische Seal-Kette, Replay-/Integrity-Prüfungen und externe
Anchor-Dateien. Der Audit fand **keinen Beleg für eine aktuell beschädigte
produktive Datenbank**. Er bestätigt aber vier voneinander abhängige Lücken:

| Punkt | Kurzbefund | Einordnung |
|---|---|---|
| A0.1 | Normales `connect()` führt DDL und ad-hoc `ALTER TABLE` aus; explizite Schema-Version, nummerierte Migrationen, Dry-Run und Recovery-Vertrag fehlen. | **CONFIRMED · Kontrolllücke/Architekturgrenze/Betriebsrisiko** |
| A0.2 | CI und Replay-Tests besitzen kein einzelnes, historisch repräsentatives Golden Ledger mit unabhängig festgeschriebenen Projektionsdigests. | **CONFIRMED · fehlender Nachweis** |
| A0.3 | Reseal hebt Trigger auf und schreibt Seals neu, ohne technisches Zeremonie-Gate; Anchors sind ausdrücklich unsigniert; Status-`main` ist ungeschützt und ein Deploy Key hat Schreibrecht. | **CONFIRMED · Kontrolllücke/Architekturgrenze/Betriebsrisiko** |
| A0.4 | Replay und Integrity materialisieren den Ledger unbeschränkt im RAM; Batch-, Fortschritts-, Crash- und Pi-Budget-Nachweise fehlen. | **CONFIRMED · Architekturgrenze/fehlender Nachweis/Betriebsrisiko** |

Die wichtigste technische Abhängigkeit ist nicht frei wählbar: Ein
menschengeprüftes Golden-Ledger-/Projektionsorakel muss **vor oder gemeinsam mit**
einem Migrationssystem entstehen. Andernfalls würde dieselbe neue Implementierung
sowohl Transformation als auch erwartetes Ergebnis definieren. Vor einem
produktiven Migrations- oder Reseal-Lauf sind außerdem begrenzter Replay,
Recovery-Nachweise und ein unabhängiger Anchor-/Signaturpfad erforderlich.

Dieser Report setzt keine Priorität. Verbindlich werden Reihenfolge und Arbeit
erst durch angenommene ADRs sowie `docs/ROADMAP.md` und `docs/NOW.md`.

## 3. Methodik und Grenzen

Geprüft wurden die kanonischen Dokumente, einschlägiger Runtime-/Deploy-Code,
Schema, CI, Tests und Git-Historie. GitHub wurde ausschließlich mit GET-Abfragen
für Repository-, Branch-, Ruleset-, Deploy-Key- und Statusartefakt-Metadaten
gelesen. Schlüsselwerte und Secrets wurden weder angefordert noch ausgegeben.

Die Kennzeichnungen bedeuten:

- **CONFIRMED:** unmittelbar durch Code, Test, Dokument, Commit, ausgeführten
  Befehl oder GitHub-GET belegt.
- **INFERRED:** technisch gut begründete Folgerung, aber nicht durch den
  verlangten Betriebs-/Fehlertest bewiesen.
- **UNKNOWN:** im erlaubten Scope nicht verifizierbar; es wird nicht geraten.

Zusätzliche Typen:

- **Bug/Kontrolllücke:** beobachtbares Verhalten verletzt eine notwendige
  Sicherheits- oder Trennungsbedingung.
- **fehlender Nachweis:** Implementierung kann korrekt sein, doch das verlangte
  beweiskräftige Test-/Betriebsartefakt fehlt.
- **Architekturgrenze:** bewusst oder faktisch nicht unterstützter Fall.
- **Betriebsrisiko:** ein heute ausführbarer Pfad kann bei Fehler oder
  Kompromittierung erheblichen Schaden erzeugen.
- **Zukunftsverbesserung:** vorgeschlagene Zielmechanik, noch kein akzeptierter
  Vertrag.

Grenzen des Audits:

- **UNKNOWN:** Der Produkt-Ledger und sein Dateisystemzustand wurden absichtlich
  nicht geöffnet; sein aktueller innerer Zustand ist damit nicht attestiert.
- **UNKNOWN:** Stromausfall-/Kill-Recovery, reale Pi-Laufzeit, Peak RSS,
  WAL-Wachstum und Writer-Lock-Dauer wurden nicht praktisch gemessen.
- **UNKNOWN:** Der physische Speicherort und Dateimodus des privaten
  Status-Deploy-Keys wurden nicht auf einem Host geprüft.
- **UNKNOWN:** Organisationsweite GitHub-Regeln, unabhängige Mirrors oder
  WORM-/Transparency-Log-Verwahrung außerhalb der abgefragten Repositories.
- **UNKNOWN:** Im Repository wurde kein als GENUS-Handbuch v1.0 identifizierbares
  Artefakt gefunden; dessen Existenz und Datum wurden nicht extern verifiziert.

## 4. Baseline

| Merkmal | Reproduzierter Wert | Evidenz |
|---|---|---|
| Arbeitsverzeichnis | `C:\Users\ronny\dev\GENUS_PI_SEED` | `Get-Location` |
| Anfangsstatus | sauber; `git status --short` ohne Ausgabe | read-only Git-Befehl vor Analyse |
| lokaler Branch | `codex/safe-pi-remote-update` | `git branch --show-current` |
| lokaler HEAD | `cadcda834a5d8e61be357f90b0db11c284ea9a9a` | `git rev-parse HEAD` |
| letzter lokaler Commit | `cadcda8 add safe Pi update and remote access runbook` | `git log -1 --oneline` |
| Python | `3.12.13` | `.venv\Scripts\python.exe --version` |
| Paket | `genus-pi-seed 1.17.0` | `pyproject.toml:5-9`; `genus/__init__.py:1` |
| Testsammlung | `1499 tests collected` | `pytest --collect-only -q -p no:cacheprovider` |
| fokussierte A0-Tests | `141 passed in 30.12s` | Abschnitt 19 |
| öffentliches SEED-Repo | `main`, Head `1a73db0...`, aktives Ruleset, keine Deploy Keys | GitHub-GET, 2026-08-09 |
| öffentliches STATUS-Repo | `main`, Head `f6ee537...`, ungeschützt, ein schreibender Deploy Key | GitHub-GET, 2026-08-09 |

`docs/NOW.md:23-35` nennt für seinen älteren datierten Betriebsstand noch 1.318
Tests und 938.614 Events. Das ist kein Widerspruch zur aktuellen Sammlung,
sondern bestätigt die Dokumentenregel: `NOW.md` ist ein eigener Snapshot und
dieser Report darf ihn nicht still aktualisieren.

## 5. Confirmed / Inferred / Unknown

| Aussage | Status | Typ |
|---|---|---|
| Der normale Datei-DB-Connect kann Schema-DDL ausführen und committen. | **CONFIRMED** | Kontrolllücke/Architekturgrenze |
| Ein reiner Status-Export kann über `db.connect()` denselben Schema-Init-Pfad erreichen. | **CONFIRMED** | Kontrolllücke/Betriebsrisiko |
| Eine heutige Produkt-DB sei dadurch bereits beschädigt. | **UNKNOWN** | nicht geprüft, keine Tatsachenbehauptung |
| Die CI beweist den nichtleeren Legacy-Präfix gemeinsam mit versiegeltem Tail und Replay-Orakel. | **CONFIRMED: nein** | fehlender Nachweis |
| Ein erzwungener Reseal einer intakten Kette berechnet wegen deterministischer Eingaben dieselben Seal-Werte. | **INFERRED**, durch Algorithmus und bestehende Tests gestützt | Architekturverhalten |
| Ein Reseal nach Inhaltsänderung vor einem Anchor-Head invalidiert diesen Anchor; spätere Änderungen nicht. | **CONFIRMED** | Sicherheitsgrenze |
| WAL-Leser sehen während der CLI-Replay-Transaktion voraussichtlich den letzten konsistenten Commit. | **INFERRED** | fehlender Concurrent-Reader-Test |
| Kill vor Commit wird von SQLite sauber zurückgerollt. | **UNKNOWN** | fehlender Crash-/Reopen-Test |
| `GENUS_PI_STATUS/main` besitzt verpflichtende Reviews oder Checks. | **CONFIRMED: nein** | Betriebsrisiko |
| GitHub erlaubt die direkte Löschung des aktuellen Default-Branches. | **UNKNOWN** | nicht mutation-getestete Plattformgrenze |
| Der private Status-Key liegt heute tatsächlich auf dem Pi. | **UNKNOWN** | Setup-Absicht, keine Live-Custody-Prüfung |

## 6. A0.1 Schema Migration

### Istzustand

- **CONFIRMED · Kontrolllücke:** `genus/db.py:16-29` öffnet eine Datei-DB und
  ruft immer `init_schema()` auf. `init_schema()` setzt Pragmas, aktiviert WAL,
  führt das vollständige `schema.sql` aus, ruft `_ensure_column()` auf und
  committet (`genus/db.py:141-159`). Ein normaler Startup ist damit kein reiner
  Kompatibilitätscheck.
- **CONFIRMED · Kontrolllücke:** `_ensure_column()` liest `PRAGMA table_info`,
  führt bei Bedarf `ALTER TABLE ... ADD COLUMN` aus und besitzt keine
  Migrations-ID (`genus/db.py:162-170`). Betroffen sind derzeit Proposal-
  Entscheidung/Reviewzeit, Inquiry-Antwort und Event-Seal-Spalten
  (`genus/db.py:151-157`).
- **CONFIRMED · Betriebsrisiko:** CLI-Produktpfade verwenden den mutierenden
  `get_conn()` (`genus/cli.py:72-74`). Selbst der Status-Exporter öffnet mit
  `db.connect()` (`deploy/export_pi_status.py:22-27`), bevor er read-only
  Kennzahlen liest. Ein Dienst mit vermeintlich reinem Leseauftrag kann daher
  DDL ausführen und committen.
- **CONFIRMED · vorhandene gute Grenze:** `connect_readonly()` nutzt SQLite
  `mode=ro` und `PRAGMA query_only=ON`, ohne Schema-Init
  (`genus/db.py:32-57`). `tests/test_db_hardening.py:58-76,99-135` prüft die
  Nichtmigration und verständliche Fehler bei fehlender DB.
- **CONFIRMED · Architekturgrenze:** `schema.sql:1-224` enthält Tabellen,
  Indizes und Append-only-Trigger, aber weder eine explizite Schema-Version noch
  `schema_migrations`. Im geprüften Runtime-Scope existieren keine nummerierten,
  reproduzierbaren DB-Migrationen, kein `genus db status`, kein `genus db
  migrate`, kein Dry-Run und keine versionierte Downgrade-/Recovery-Regel.
- **CONFIRMED · fehlender Nachweis:** `tests/test_ledger.py:25-91` baut nur
  synthetische Altschemata für einzelne Lifecycle-/Seal-Spalten und prüft das
  ad-hoc Ergänzen. Replay beginnt getrennt ab `:123`; ein historisches
  Altschema→Migration→Replay→Oracle-Szenario fehlt.
- **CONFIRMED · fehlender Nachweis:** Kein technisches Gate verlangt vor einer
  Schemaänderung Backup, letzten Anchor, Integrity, freien Speicher,
  Versionskompatibilität oder Wiederherstellungsprobe. Ein Vertrag für Fehler
  zwischen mehreren DDL-Schritten ist nicht implementiert.

Der bestätigte Defekt ist die fehlende Trennung zwischen **Öffnen/Prüfen** und
**Schema verändern**, besonders im lesend gedachten Statuspfad. Nicht bestätigt
ist, dass eine konkrete bestehende DB falsch migriert wurde.

### Kleinste sichere Zielmechanik — noch kein Patch

1. Eine explizite, monotone Schema-Version und eine append-orientierte
   `schema_migrations`-Historie mit ID, Codeversion, Digest, Start/Ende und Status.
2. Nummerierte, deterministische `up`-Migrationen; jeder Schritt besitzt
   Vorbedingung, Nachbedingung, Idempotenz-/Abbruchregel und eigene Tests.
3. `genus db status` arbeitet garantiert read-only und meldet
   Ist-/Zielversion, Kompatibilität und erforderliche Schritte.
4. Normale Produktdienste verweigern den Start bei falscher Version; nur der
   explizite, human-owned `genus db migrate`-Pfad darf DDL ausführen.
5. `--dry-run` erstellt einen Plan gegen Schema-Metadaten bzw. eine
   Arbeitskopie, ohne den Produkt-Ledger zu öffnen oder zu verändern.
6. Vor dem Lauf: Writer-Stopp, DB/WAL/SHM-Backup samt Digest,
   Wiederherstellungsprobe, letzter gültiger externer Anchor, freie
   Speicherprüfung und Integrity-/Seal-Baseline.
7. Nach dem Lauf auf der Arbeitskopie: Schema-Nachbedingung, Golden Replay,
   Integrity, Seal und Anchor-Verifikation; erst dann gesonderte menschliche
   Freigabe für einen produktiven Lauf.
8. DDL-Transaktionsgrenze und Recovery pro Schritt ausdrücklich definieren;
   ein unbekannter/teilweiser Stand führt zur Startverweigerung, nicht zur
   stillen Fortsetzung.

Critical scope sind `schema.sql`, Schema-/Connect-Code, Event-Ledger und Trigger,
Migration Runner und Historie, Replay-/Integrity-Router sowie alle Schritte, die
Seal-, Epoch- oder Anchor-Semantik berühren. Nach
`docs/design/SELF_CODING.md:42-53,118-122,163-172` und
`docs/CHARTER.md:65-95` bleiben diese human-owned.

## 7. A0.2 Golden Ledger und Golden Replay

### Istzustand

- **CONFIRMED · fehlender Nachweis:** CI führt zuerst die Tests aus und danach
  `genus replay` gegen eine neue `${runner.temp}/genus-ci.sqlite3`; vorher wird
  kein historischer Ledger importiert (`.github/workflows/ci.yml:45-56`). Erst
  anschließend öffnet CI die Seal-Epoche und erzeugt/verifiziert einen Anchor
  auf dieser trivialen DB (`:58-88`).
- **CONFIRMED:** `tests/conftest.py:26-44` weist jedem Test einen temporären
  Pfad zu; der Standard-`conn` ist eine frische In-Memory-DB mit aktuellem
  Schema. Im Testbaum wurde keine statische Golden-/Fixture-Datei vom Typ SQL,
  SQLite, JSON oder JSONL gefunden.
- **CONFIRMED · vorhandene portable Evidenz:** Einzeltests decken wesentliche
  Komponenten ab: Legacy-Präfix-Tamper
  (`test_legacy_prefix_tampering_is_detected_by_genesis`), versiegelten Replay
  (`test_replay_is_deterministic_with_sealing`), zweimaligen synthetischen Replay
  (`test_belief_stability_is_replay_stable_and_integrity_passes`), Lifecycle,
  Experience, Governance, rohe Forecast-Events und Router-/Dokumentvertrag. Sie
  bilden aber kein gemeinsames historisches Orakel.
- **CONFIRMED · fehlender Nachweis:** Der versiegelte Replay-Helfer öffnet die
  Epoche vor den fachlichen Events (`tests/test_sealing.py:12-15,209-237`), sein
  Legacy-Präfix ist leer. Die alten Relationstests in
  `tests/test_verwandtschaft.py:280-337` prüfen Semantik, keine
  Schema-Migration.
- **CONFIRMED · fehlender Nachweis:** Erwartete Projektionsfingerabdrücke sind
  nicht unabhängig festgeschrieben. Tests vergleichen einen gerade mit
  derselben Implementierung erzeugten Python-Snapshot mit dem Replay-Ergebnis.
- **CONFIRMED · Kontrolllücke:** Die CLI-Idempotenzaufnahme umfasst Beliefs,
  Proposals, Inquiries, Experiences, States, Governance, Operations und Rules,
  lässt aber `relation_projection`, `value_projection`,
  `response_outcome_log` und `response_feedback_log` aus
  (`genus/cli.py:2079-2156`). Integrity besitzt dagegen den vollständigen Satz
  der zwölf Replay-Tabellen (`genus/integrity.py:733-895`). `genus replay` kann
  daher „State matches“ melden, ohne vier Ziele zu vergleichen.

Eine leere Präfixmenge reduziert den Genesis-Digest auf den Digest eines festen
Startwerts (`genus/sealing.py:184-198`). Der historisch relevante Zweig vergleicht
Anzahl, maximale ID und Digest realer, nichtleerer Legacy-Zeilen
(`genus/sealing.py:96-121`). Eine frisch versiegelte DB beweist daher weder
Serialisierung, Reihenfolge und Zeitstempel eines realen Präfixes noch deren
Zusammenspiel mit einem versiegelten Tail.

### Anforderungen an die spätere datenschutzfreie Fixture

Die Fixture muss statisch und versioniert sein; IDs, Zeitstempel, Payload-Text
und vorhandene Seals dürfen nicht durch die jeweils aktuelle Producer-
Implementierung regeneriert werden. Sie muss ausdrücklich enthalten:

1. mehrere unversiegelte Legacy-/Prä-Epochen-Events;
2. einen nichtleeren Legacy-Präfix;
3. `ledger_epoch_opened` mit korrekt vorab geprüftem Genesis-Digest;
4. einen versiegelten Tail nach der Epoche;
5. projizierte Eventtypen;
6. bewusst rohe Eventtypen;
7. unterstützte/bestätigte, widersprochene/geschwächte und supersedierte Beliefs;
8. Relation, Inquiry, Experience, Proposal und Governance;
9. mindestens einen terminalen Lebenszyklus;
10. grüne Integrity-, Seal- und statische Anchor-Verifikation;
11. unabhängig geprüfte erwartete Projektionsdigests;
12. zweimaligen Replay mit identischem Ergebnis und unverändertem Event-Log;
13. ausschließlich synthetische, datenschutzfreie Inhalte.

Ein Manifest bindet mindestens Fixture-Digest, Schema-Provenienz, erwartete
Eventzahl/IDs, Präfix-Metadaten/Genesis, Epoche, Head, statischen Anchor-Kandidaten,
kanonische SHA-256-Digests jeder der zwölf Projektionstabellen und einen
Gesamtdigest. Erwartungswerte werden separat menschengeprüft und eingecheckt,
nicht zur Laufzeit aus dem Code unter Test erzeugt. Negative Tests manipulieren
Präfix, Tail, Payload, Seal und erwarteten Digest. Sobald Migration existiert,
muss zusätzlich eine Kopie eines alten Schemas über Migration und Replay exakt
dasselbe Orakel erreichen.

## 8. A0.3 Reseal, Anchor, Signatur und Key Custody

### Reseal-Semantik

- **CONFIRMED · Betriebsrisiko:** `sealing.reseal()` liest die erste Epoche,
  entfernt vorübergehend beide UPDATE-/DELETE-Schutztrigger
  (`genus/sealing.py:143-163`), iteriert alle Zeilen nach `prefix_max_id`
  einschließlich des Epoch-Markers und überschreibt ausschließlich `prev_seal`
  und `seal` (`:165-174`). Event-ID, Typ, Payload, Zeit und Reihenfolge werden
  nicht geändert; die Trigger werden im `finally` wieder angelegt (`:175-180`).
- **CONFIRMED · Kontrolllücke:** Weder Funktion noch CLI erzeugen ein
  Maintenance-/Reseal-Event. Der CLI kennt keine Pflichtfelder oder Gates für
  Grund, Operator, Approver, Backup, letzten Anchor oder betroffenen Bereich.
  `--force` erlaubt den Lauf auch bei intakter Kette
  (`genus/cli.py:1976-1990`).
- **CONFIRMED · Kontrolllücke:** Die CLI committet bei
  `genus/cli.py:1994` und führt die abschließende Seal-Prüfung erst bei
  `:1995-1999` aus. Ein negatives Post-Check-Ergebnis wäre bereits dauerhaft
  geschrieben.
- **CONFIRMED · dokumentierte, nicht erzwungene Norm:** Das Security Model
  verlangt Beweissicherung, dokumentierte Entscheidung und Neuverankerung
  (`docs/SECURITY_MODEL.md:244-267`) sowie Writer-Stopp, DB/WAL/SHM-Sicherung,
  letzten externen Anchor und Arbeit auf einer Kopie (`:352-362`).

### Anchor-Gültigkeitsgrenze und Epochen

- **CONFIRMED:** Änderung/Neuversiegelung an oder vor dem Anchor-Head wird
  erkannt (`tests/test_anchor.py::test_adaptive_resealing_before_anchor_is_detected`).
  Änderung oder Kürzung ausschließlich danach lässt den alten Anchor für seinen
  alten Head gültig (`test_adaptive_resealing_after_anchor_remains_valid_for_old_anchor`,
  `test_tail_truncation_after_anchor_remains_valid_for_old_anchor`). Ein Anchor
  bezeugt deshalb nur die Geschichte **bis zu seinem Head**.
- **INFERRED:** Ein `--force`-Reseal einer unveränderten intakten Kette schreibt
  Zeilen erneut, berechnet mit denselben deterministischen Eingaben aber
  dieselben Werte. Nach tatsächlicher Inhaltsänderung werden alle Anchors an/ab
  der ersten geänderten Position ungültig; ältere Heads davor bleiben gültig.
- **CONFIRMED · Architekturgrenze:** `epoch_event()` wählt mit
  `ORDER BY id LIMIT 1` die erste Epoche (`genus/sealing.py:61-71`).
  `open_epoch()` verweigert bei aktiver Epoche eine weitere (`:33-35`),
  Verifier und Anchors interpretieren nur diese Epoche. Das Protokoll unterstützt
  keinen erklärbaren Repair-/Multi-Epoch-Übergang.

### Anchor- und Publish-Pfad

- **CONFIRMED · fehlende Funktion:** `genus/anchor.py:14,40-53` setzt
  `signature = None`; die Validierung weist jeden Nicht-Null-Wert für v1.2 sogar
  zurück (`:154-155`). Signaturprüfung, Key-ID, Rotation und Widerruf existieren
  nicht.
- **CONFIRMED · Betriebsrisiko:** Der Dateiname enthält Core, Head-ID und zwölf
  Hashzeichen (`genus/anchor.py:191-195`), aber weder Ausgabe-ID noch
  Signaturschlüssel/-zeit. `genus/cli.py:2021-2030` schreibt blind; eine erneute
  Ausstellung desselben Heads überschreibt denselben Pfad.
- **CONFIRMED:** Der Pi-Status-Publisher erzeugt den Candidate direkt aus dem
  Live-Ledger, aktualisiert Statusdateien, staged, committet und pusht normal auf
  `main` (`deploy/pi_publish_status.sh:22-73`). Er selbst nutzt keinen
  Force-Push. Das Setup erzeugt den SSH-Key laut Skript auf dem Remote-Host und
  fordert einen schreibenden Deploy Key (`deploy/setup_pi_status_key.ps1:40-45,70-83`).
- **CONFIRMED · Textgrenze:** `deploy/export_pi_status.py:240-246` beschreibt
  die Aussage eines passenden Anchors ohne klare Head-Grenze. Die oben genannten
  Tests zeigen, dass diese Aussage nur bis zum Anchor-Head trägt.

### Kurzfristige Reseal-Zeremonie — Ziel, nicht Implementierung

1. Writer stoppen; DB, WAL und SHM unverändert sichern und hashen.
2. Letzten gültigen externen Anchor samt ursprünglichem Speicherort bewahren.
3. Backup auf zweitem Medium verifizieren und auf einer Arbeitskopie
   wiederherstellen.
4. Incident-/Maintenance-ID, Grund, Operator, unabhängigen Approver,
   Codecommit, alten Head und betroffenen ID-Bereich festhalten.
5. Explizite menschliche Freigabe; `--force` bei intakter Kette nur als separat
   begründete Ausnahme.
6. Reseal transaktional auf der Arbeitskopie; Trigger, Seal, Integrity und
   Golden Replay **vor** Commit/Nutzungsfreigabe prüfen.
7. Alten/neuen Head, betroffene IDs, Backup-Digest, Befehl und Resultate in
   einem externen Wartungsbeleg festhalten.
8. Pi erzeugt nur einen unsigned Candidate; Prüfung und Signatur erfolgen auf
   der separaten Vertrauensstation.
9. Neuen ausstellungs-eindeutigen Anchor append-only veröffentlichen; alle
   alten Anchors erhalten.
10. Bei Fehler pausieren und auf das verifizierte Abbild zurückgehen; keinen
    fehlgeschlagenen Reseal zur neuen Wahrheit erklären.

### Langfristiges Multi-Epoch-Protokoll — Ziel, nicht Implementierung

Eine neue Epoche muss explizit Vorgänger-Epoche, letzten vertrauenswürdigen
Event/Head/Anchor, erste Schadensposition, beobachteten beschädigten Head,
Repair-Manifest-Digest, Algorithmus und zulässige Prüfschlüssel binden. Zustände
`normal → broken → repaired/new epoch` bleiben sichtbar; die gebrochene Epoche
wird nicht kosmetisch überschrieben. Der Verifier liefert je Epoche ein Ergebnis
und erklärt jeden Reparaturübergang. Anchors nennen Epoche, Repair-Manifest,
Key-ID und Signaturalgorithmus; alte Anchors und die gebrochene Epoche bleiben
historisch erhalten.

### Key Custody als eigene Architekturentscheidung

Verbindliche Zielgrenze: Der Signatur-Private-Key liegt niemals auf dem Pi. Der
Pi erzeugt höchstens kanonische unsigned Candidates. Öffentliche Prüfschlüssel
und Key-IDs dürfen verteilt werden; eine separate Vertrauensstation prüft
Candidate, Core, Epoche und Wartungsbeleg vor der Signatur.

| Option | Stärke | Grenze |
|---|---|---|
| Verschlüsselter Software-Key auf separater Workstation | einfache Einführung und Sicherung | Workstation-/Passphrase-Kompromittierung |
| Hardware-Token mit PIN/Touch | Private Key nicht exportierbar, explizite Bedienfreigabe | Geräteverlust, Treiber und Recovery |
| Verschlüsseltes Offline-Recovery-Medium | unabhängiger Notfallpfad | langsam; kein täglicher Signierer |

Benötigt werden ein versioniertes Trust-Manifest, Gültigkeitsintervalle,
Alt→Neu-Rotation, Widerrufsmanifest samt möglichem Kompromittierungsfenster,
Mehrpersonen-/Recovery-Freigabe und ein Notbetrieb: Unsigned Candidates dürfen
als `PENDING/UNTRUSTED` gesammelt, aber nicht als extern bezeugt bezeichnet
werden. Welche Primäroption gilt, ist eine offene menschliche ADR-Entscheidung.

## 9. A0.4 Bounded Replay

### Istzustand

- **CONFIRMED · Architekturgrenze:** `genus/event_router.py:197-226` lädt mit
  `SELECT * ... fetchall()` alle Events in RAM, löscht geordnet alle zwölf
  Projektionstabellen samt ausgewählter Autoincrement-Sequenzen und projiziert
  danach jedes resident gehaltene Event. Batch-Größe, Cursor, Speichergrenze und
  Event-Fortschritt fehlen.
- **CONFIRMED:** Der CLI-Pfad hält `BEGIN IMMEDIATE` über Vorher-Snapshot,
  `replay(commit=False)`, Nachher-Snapshot und Commit
  (`genus/cli.py:1819-1861`).
  `test_replay_command_holds_writer_gate_through_comparison` beweist, dass ein
  konkurrierender Writer bis nach dem Vergleich gesperrt bleibt.
- **CONFIRMED · Kontrolllücke:** Der CLI-Snapshot lässt vier Replay-Ziele aus
  (Abschnitt 7). Außerdem wird bei `genus/cli.py:1842` vor der späteren Meldung
  eines Zustandsunterschieds (`:1852-1855`) committet. Das ist kein Beleg für
  Ledger-Korruption, aber eine unklare Erfolg-/Abbruchsemantik.
- **INFERRED:** Wegen WAL und einer einzigen Transaktion sollten andere Leser
  den letzten vollständig committeten Projektionsstand sehen; ein expliziter
  Concurrent-Reader-Test fehlt.
- **UNKNOWN:** Prozess-Kill/Stromausfall vor Commit, Wiederöffnung und Retry
  wurden nicht getestet.
- **CONFIRMED · API-Grenze:** Die tiefere Funktion `replay(commit=True)` besitzt
  selbst kein explizites `BEGIN`/Rollback. Aktuelle Produktaufrufe sind der
  geschützte CLI-Pfad und ein isolierter In-Memory-Integrity-Pfad; ein künftiger
  direkter Caller könnte Transaktionsownership falsch verwenden.
- **CONFIRMED · Betriebsrisiko:** Integrity kopiert ebenfalls den vollständigen
  Event-Log per `fetchall()` in Python (`genus/integrity.py:713-730`), erstellt
  eine zweite In-Memory-SQLite-DB und fügt alle Events ein (`:293-307`), bevor
  sie replayt. Nur Replay zu begrenzen würde den Diagnosepfad nicht begrenzen.
- **CONFIRMED · fehlender Nachweis:** Es gibt keinen Replay-Benchmark und kein
  Budget für Zeit, Peak RSS, WAL oder Writer-Lock. Öffentliche H0-Artefakte
  belegen als Größenordnung 938.616 Events und eine 515.706.880-Byte-Haupt-DB,
  nicht aber Replay-Sicherheit oder -Leistung auf dem Pi.
- **CONFIRMED:** Der Deploypfad führt zwei Live-Rebuilds und durch Integrity,
  final Integrity sowie Doctor drei weitere In-Memory-Replays aus
  (`deploy/pi_deploy.sh:91-129`; `genus/doctor.py:29-38,67-88`).

### Kleinste sichere Zielmechanik — noch kein Patch

1. Unter explizitem Writer-Gate einen festen `head_id` erfassen.
2. Events per Keyset-Pagination bzw. `fetchmany` mit `id > last_id AND id <=
   head_id ORDER BY id LIMIT batch_size` lesen; ein sicherer Default ist Teil des
   Vertrags. `genus/betriebsprofil.py:945-985` zeigt bereits ein begrenztes
   `fetchmany(1024)`-Muster für einen Präfix-Digest.
3. Transaktionsownership, Commit, Rollback und Retry auf API- und CLI-Ebene
   eindeutig definieren. Kein Replay erzeugt Ledger-Events.
4. Entweder eine vollständige atomare Transaktion beibehalten, wenn Pi-Messungen
   Lock-/WAL-Budgets beweisen, oder versionierte Shadow-Projektionen aufbauen und
   atomar umschalten. Die Wahl ist mess- und ADR-pflichtig.
5. Integrity denselben begrenzten Stream verwenden lassen; keine parallele
   Python-Liste plus vollständige In-Memory-Ledger-Kopie.
6. Fortschritt ausgeben: `processed/total`, Zeit, Rate, letzte ID, Phase; keine
   Payloads.
7. Fehler-/Kill-Injection, Wiederöffnung und idempotenten Retry prüfen.
8. Synthetische Klassen 0, 1, 10k, 100k und ungefähr 1 Mio. Events in CI sowie
   Pi-Abnahme messen; Zeit, Peak RSS, WAL-Hochwasser und Writer-Lock-Dauer gegen
   vorab akzeptierte Budgets prüfen.

## 10. Branch-Protection- und Status-Repo-Befund

Snapshot der sanitierten read-only GitHub-Abfragen vom 2026-08-09:

Repository-IDs: `GENUS_PI_STATUS` `1269276049`, `GENUS_PI_SEED`
`1260709633`. Beide Repositories waren öffentlich und verwendeten `main` als
Default-Branch.

| Prüfung | `GENUS_PI_STATUS` | `GENUS_PI_SEED` |
|---|---|---|
| Default-Branch | `main` | `main` |
| Branch geschützt | **CONFIRMED: nein** (`protected=false`, Protection-GET 404) | **CONFIRMED: ja**, Ruleset `17359029` |
| Rulesets | **CONFIRMED:** `[]` | **CONFIRMED:** `deletion`, `non_fast_forward`, `copilot_code_review` |
| verpflichtende Reviews/Checks | **CONFIRMED:** keine | Copilot-Review-Regel; keine Aussage über klassische PR-Reviewanzahl |
| Force-Push-Regel | **CONFIRMED:** kein Protection-/Ruleset-Verbot | `non_fast_forward` verboten |
| Löschregel | **CONFIRMED:** kein Protection-/Ruleset-Löschschutz; reale Default-Branch-Löschung **UNKNOWN** | `deletion` verboten |
| Deploy Keys | genau einer, verified, Titel `pi-core status publisher`, `read_only=false`, erstellt 2026-06-14 | leer |

**CONFIRMED · Betriebsrisiko:** Ein kompromittierter Host mit diesem Status-Key
kann durch keine Repository-Regel an direktem Push, Non-Fast-Forward-Update oder
Anchor-Umschreiben gehindert werden. Der reguläre Publisher verwendet zwar
keinen Force-Push, aber seine Berechtigung und Branch-Regeln begrenzen einen
Angreifer nicht entsprechend.

Der aktuelle Status-Commit `Update RonGen status` ist laut GitHub
`verified=false`/`unsigned`. Das Repo enthielt 61 Anchor-Dateien (30 `RonGen`, 31
`pi-core`). Der neueste RonGen-Anchor
`genus-anchor-RonGen-1126763-d0d9fa5aeb6e.json` bindet Event 1.126.763, nennt
`epoch_event_id=1` und trägt `signature=null`. Damit belegt selbst der aktuelle
öffentliche RonGen-Anchor nur den leeren Präfixfall vor der Epoche.

**UNKNOWN:** Der Titel und das Setup-Skript deuten auf einen Pi-hosted Private
Key, beweisen die heutige Custody aber nicht. Manueller read-only Prüfpfad: auf
dem vorgesehenen Pi die `Host github-genus-pi-status`-Zuordnung in
`~/.ssh/config`, Dateimodus und ausschließlich den Public-Key-Fingerprint prüfen
und ihn mit der freigegebenen GitHub-Metadaten-ID abgleichen; niemals den privaten
Schlüssel ausgeben. GitHub-seitig sind zusätzlich `Settings → Rules/Branches →
main`, `Rulesets` und `Deploy keys` zu prüfen.

## 11. Abhängigkeiten und empfohlene Reihenfolge

Die folgende Ordnung ist aus dem Code abgeleitet, aber **nicht verbindlich**:

1. **Human-owned Entscheidungen zuerst.** Akzeptierte ADRs müssen
   Schema-/Versionsvertrag, Golden-Corpus-Provenienz, Recovery-/Reseal-Semantik,
   Multi-Epoch-Grenzen und Signatur-/Key-Custody festlegen. Nur
   `docs/ROADMAP.md` und `docs/NOW.md` dürfen daraus Priorität und aktiven Stand
   machen.
2. **Golden Ledger und unabhängiges Orakel zuerst oder gemeinsam mit dem
   Migrationsrahmen.** Es bindet Legacy-Schema, Präfix-Genesis, Tail und alle
   Projektionen, bevor verändernder Code seine eigene Erwartung erzeugen kann.
3. **Nichtmutierende Schema-Erkennung und begrenzte Diagnose.** Read-only
   `db status`, klare Versionsverweigerung und Bounded Replay/Integrity können
   nach feststehendem Orakel teilweise parallel entstehen. Begrenzter Replay
   muss vor einem produktiven Lauf auf einem Ledger dieser Größenordnung
   akzeptierte Pi-Budgets erfüllen.
4. **Nummerierter Migration Runner nur gegen Kopien.** Dry-Run,
   Fehler-Injection, Backup/Restore und Altversion→Migration→Golden-Replay
   schließen den Nachweis. Noch keine produktive Migration.
5. **Unabhängiger Anchor v2 und Status-Härtung vor jeder Reseal-Zeremonie.**
   Candidate/Signer-Trennung, Trust-/Revocation-Manifest, append-only
   Veröffentlichung und Branch-/Key-Minimierung müssen verhindern, dass der
   reparierende Host zugleich alleiniger Zeuge ist.
6. **Kurzfristige Reseal-Zeremonie nur nach explizitem menschlichem Incident-
   Beschluss; langfristig Multi-Epoch statt kosmetischer Umschreibung.** Ein
   konkreter produktiver Reseal bleibt ein eigener, späterer Auftrag.

Begründung: `db.connect()` kann schon heute still mutieren; ohne Orakel ist die
Semantik nach Migration nicht unabhängig prüfbar. Replay/Integrity sind auf
realistischer Größenordnung unbeschränkt; ohne Recovery und Budget ist selbst
eine fachlich korrekte Migration operativ nicht freigabefähig. Ein Reseal ohne
unabhängigen Signierer und geschützten Veröffentlichungsort könnte Beleg und
Geschichte auf demselben kompromittierten Host neu erzeugen.

## 12. Definition of Done je A0-Punkt

### A0.1 Schema Migration

- Persistierte Schema-Version und append-only Migrationsjournal sind definiert.
- Jede unterstützte Version besitzt eine nummerierte, deterministische
  `from → to`-Migration mit Vor-/Nachbedingung und Digest.
- Normales Connect/Startup führt keine DDL aus und verweigert unbekannte, alte
  oder zu neue Versionen verständlich.
- `genus db status` ist nachweislich read-only; `genus db migrate` ist ein
  separater human-owned Pfad mit Dry-Run.
- Backup, Restore-Probe, letzter Anchor, Integrity/Seal, freier Speicher,
  Operator und Freigabe sind vor dem Lauf maschinenlesbar belegt.
- Fehler an jedem kritischen Schritt führt entweder zum atomaren Rollback oder
  zu einem eindeutig erkannten, dokumentierten Recovery-Zustand.
- Jede Altversion erreicht nach Migration, Integrity und zweimaligem Golden
  Replay dasselbe Orakel; das Ledger erhält keine neuen fachlichen Events.
- Produktdienste starten erst nach separat belegtem Abschluss.

### A0.2 Golden Ledger / Golden Replay

- Die 13 Fixture-Anforderungen aus Abschnitt 7 sind erfüllt.
- Fixture und Manifest sind datenschutzfrei, statisch, versioniert und durch
  getrennte menschliche Prüfung freigegeben.
- Alle zwölf Projektionstabellen besitzen kanonische Einzel- und Gesamtdigests.
- Eventzeilen, Anzahl und Head sind vor/nach zwei Replays byte-/kanonisch
  identisch; Replay erzeugt null Events.
- Eventvertrag, Integrity, Seal, Genesis und statischer Anchor sind grün.
- Negative Tamper-Tests für Präfix, Tail, Seal, Payload und Oracle schlagen
  erklärbar fehl.
- Alt- und aktuelle Eventformen sowie mindestens ein altes vollständiges Schema
  werden gemeinsam geprüft.
- Nach Einführung der Migration gilt: Fixture-Kopie alt → Migration → zwei
  Replays → identisches Orakel.

### A0.3 Reseal / Anchor / Signatur / Key Custody

- `--force` ist kein unprotokollierter Normalpfad; Reason, Operator, Approver,
  Incident-ID, Backup, letzter Anchor und Bereich sind Pflichtgates.
- Triggerwiederherstellung, Seal, Integrity und Golden Replay werden vor finaler
  Freigabe bewiesen; Fehler hinterlassen keinen als gesund markierten Commit.
- Ein externer, signierter Wartungsbeleg bindet alten/neuen Head, Backup-Digest,
  Bereich, Codecommit und Resultate; alte Anchors werden nie überschrieben.
- Multi-Epoch-/Repair-Übergänge bewahren die gebrochene Geschichte und liefern
  Verifikation je Epoche statt eines undifferenzierten Booleans.
- Anchor v2 besitzt kanonische Bytes, Ausgabe-ID, Epoche, Algorithmus, Key-ID,
  Public-Key-Verifikation und testsichere Tamper-Erkennung.
- Private Signaturschlüssel liegen nie auf dem Pi; Rotation, Widerruf, Verlust,
  Kompromittierungsfenster, Offline-Recovery und Notbetrieb sind getestet und
  dokumentiert.
- Statusveröffentlichung ist append-only für Belege; Same-Head-Ausgaben
  überschreiben nicht. Branch-Regeln verhindern Löschung/Non-Fast-Forward und
  verlangen geeignete Checks; der Publisher besitzt minimal nötige Rechte.
- Kandidat, Signatur und öffentliche Verifikation werden auf getrennten
  Vertrauensdomänen geprüft.

### A0.4 Bounded Replay

- 0-, 1- und gemischte Golden-Ledger-Fälle bestehen bei allen Batchgrenzen.
- Fester Head und Keyset-/Cursor-Iteration begrenzen RAM; Integrity verwendet
  denselben begrenzten Pfad.
- API/CLI besitzen klaren Owner für Begin, Commit, Rollback, Abort und Retry.
- Injizierter Projector-Fehler stellt byte-/kanonisch identische Projektionen
  wieder her; Kill/Reopen/Retry ist getestet.
- Concurrent Reader sieht nur vollständiges Alt oder vollständig Neues, nie
  Teilzustand; Writer-Verhalten ist explizit getestet.
- Zwei Replays liefern alle zwölf Digests identisch und verändern keine
  Eventzeile.
- Fortschritt meldet Phase, processed/total, Rate und letzte ID ohne Payload.
- 10k-, 100k- und ~1M-Benchmarks protokollieren Zeit, Peak RSS, WAL und
  Lockdauer; akzeptierte CI- und Pi-Grenzen sind harte Abnahmekriterien.
- Der Deploypfad vermeidet redundante Vollkopien oder begründet jede verbleibende
  Prüfung und deren Budget.

## 13. Failure Modes und Rollback-/Recovery-Anforderungen

| Failure Mode | Heutiger Nachweis | Erforderliche sichere Reaktion |
|---|---|---|
| Dienst öffnet alte/abweichende DB | **CONFIRMED:** implizite DDL statt Versionsgate | read-only Status, Startverweigerung, expliziter Migrationsplan |
| Fehler zwischen DDL-Schritten | **UNKNOWN:** keine Fault-Injection/Recovery-Spezifikation | atomare Schritte oder persistierter Zustandsautomat; Restore aus verifiziertem Abbild |
| Migration fachlich driftet | **CONFIRMED:** kein unabhängiges historisches Orakel | Altfixture→Migration→Golden Replay/Integrity/Seal vor Freigabe |
| Replay läuft aus RAM/Zeit | **CONFIRMED:** `fetchall()`; Budget fehlt | bounded stream, Abbruch ohne Ledgerwrite, Retry, gemessene Limits |
| Projector wirft Ausnahme | CLI-Rollback im Ausnahmefall **CONFIRMED**; direkte API-Grenze offen | Owner-sicheres Rollback; byte-identischer Vorzustand; Fehler-Injection |
| Prozess-/Stromabbruch | **UNKNOWN** | Kill/Reopen-Test; eindeutiger alter oder neuer Stand; idempotenter Retry |
| Leser/Writer während Replay | Writer-Gate **CONFIRMED**, Leserbild **INFERRED** | Concurrent-Reader/-Writer-Vertrag und Tests; ggf. Shadow-Switch |
| Reseal-Postcheck scheitert | **CONFIRMED:** Commit liegt davor | Prüfungen vor Freigabe/Commit; Backup-Restore; Incident bleibt offen |
| Reseal ändert Anchor-Bereich | Head-Grenze **CONFIRMED** | alte Anchors erhalten, betroffenen Bereich inventarisieren, Wartungsbeleg + neuer Anchor |
| Signierschlüssel verloren/kompromittiert | **CONFIRMED:** heutiges Protokoll kennt das nicht | Widerruf, Rotation, Kompromittierungsfenster, Recovery-Key/Mehrpersonenfreigabe |
| Status-Key/Host kompromittiert | **CONFIRMED:** Write-Key + ungeschütztes `main` | Rechte minimieren, geschützte append-only Veröffentlichung, unabhängiger Signierer/Mirror |
| Zweite Epoche/Repair erforderlich | **CONFIRMED:** Single-Epoch-Verifier | expliziter Repair-Übergang; gebrochene Epoche sichtbar; Verifikation je Epoche |

Recovery darf nie durch einen neuen fachlichen Ledger-Event, einen stillen
Reseal oder das Löschen alter Belege „grün gerechnet“ werden. Der
Originalzustand bleibt unverändert gesichert; Arbeit und Tests erfolgen auf
Kopien, bis der Mensch die nächste Stufe freigibt.

## 14. Betroffene kanonische Dokumente

Dieser Audit ändert die folgenden Dokumente **nicht**. Nach akzeptierten ADRs
wären voraussichtlich betroffen:

| Dokument | Später zu bindender Vertrag |
|---|---|
| `docs/ARCHITECTURE.md` | Schema-Lifecycle, Transaktionsownership, Bounded-/Shadow-Replay, Multi-Epoch-Komponenten |
| `docs/EVENT_CONTRACT.md` | Golden Corpus, Replay-No-Write, Epoch-/Repair-Events und kanonische Digests |
| `docs/SECURITY_MODEL.md` | Reseal-Zeremonie, Anchor-v2-Aussagegrenze, Signer/Key-Custody, Rotation/Widerruf |
| `docs/QUALITY.md` | Migration-/Golden-/Crash-/Benchmark-Gates und vollständige Projektionsorakel |
| `docs/decisions/` | dauerhafte Gründe und akzeptierte Trade-offs |
| `docs/ROADMAP.md` | erst nach Entscheidung: verbindliche Reihenfolge/Abhängigkeiten |
| `docs/NOW.md` | erst bei aktiver Umsetzung: tatsächlich aktueller Stand |
| `docs/generated/ATLAS_FACTS.md` und Kartografie | nur generatorisch aktualisierte Zahlen/Verträge |

`docs/README.md:24-58` und `docs/CHARTER.md:107-109` trennen aktuellen Stand,
Zukunft, generierte Fakten und datierte Befunde. `docs/QUALITY.md:140-151`
verbietet eine ungeklärte Migration bzw. zweite Wahrheit. ADR-0001 bis ADR-0004
binden Core/Membrane, Change Trust, Growth und supervised Self-Coding; besonders
`docs/decisions/ADR-0004-supervised-self-coding.md:26-50` hält kritische
Änderungen aus dem autonomen Modellpfad heraus.

### Handbuch-Grenze

**UNKNOWN:** Ein konkretes Handbuch-v1.0-Artefakt wurde im Repository nicht
gefunden. Die für eine spätere menschliche Entscheidung vorgeschlagene Regel ist:
Ein Handbuch v1.0 ist ein datierter Referenzsnapshot, keine Build-Autorität.
`NOW.md` bleibt Autorität für den aktiven Stand, `ROADMAP.md` für Reihenfolge und
Abhängigkeiten, ATLAS_FACTS/Kartografie für generierte Zahlen. Eine spätere
Ausgabe erhält nur einen generierten Drift-Banner, keine zweite lebende Roadmap.

Minimales, noch nicht implementiertes Snapshot-Manifest:

- Schema/Edition/Titel und `snapshot_date`;
- `source_commit` und kanonische Pfade samt Inhaltsdigests;
- Generatorname/-version sowie ATLAS-/Kartografie-Digests;
- `generated_at`, `supersedes`, `superseded_by`;
- expliziter Autoritätshinweis auf NOW/ROADMAP/generierte Fakten.

## 15. Kandidaten für spätere ADRs

Alle folgenden Einträge sind **Kandidaten**, nicht angenommen:

1. **Schema-Lifecycle und Migration Authority:** Versionsträger, Runner,
   Startverweigerung, Backup-/Recovery-Gates.
2. **Golden Truth Corpus:** Datenschutz, Provenienz, kanonische Digests,
   menschliche Oracle-Freigabe und Pflegevertrag.
3. **Bounded Replay und Availability:** vollständige Transaktion versus
   Shadow-Projektionen, Head-Capture, Budgets und Concurrent-Reader/-Writer-
   Semantik.
4. **Seal Repair und Multi-Epoch-Protokoll:** Schadensgrenze,
   Repair-Manifest, erhaltene gebrochene Epoche und Verifier-Ergebnis.
5. **Anchor v2, Trust Store und Key Custody:** kanonische Signatur,
   Vertrauensstation, Hardware-/Software-Key, Rotation, Widerruf und Recovery.
6. **Status Evidence Publication:** append-only Namensraum, Branch-/Ruleset-
   Schutz, Publisher-Rechte, unabhängiger Mirror/Transparency-Log.

## 16. A1a Event Economy / A1b Epistemic Yield

Dieser Abschnitt ordnet nur ein; A1 wird nicht implementiert.

### A1a Event Economy

**CONFIRMED · tragfähige Basis:** `genus/betriebsprofil.py:1-7,402-492`
erfasst read-only zunächst ein rollendes 24h-Fenster und danach disjunkte
Head-ID-Intervalle. `_interval_metrics` zählt Eventtypen, normalisierte Tagesrate,
sichere Source-/Producer-Proxies, Stunden, Payload-Bytes und die Klassen
Erkenntnis/Betriebsspur/vermeidbare Wiederholung/unklar (`:556-632`).
Dateigrößen und Fähigkeitsbestände werden getrennt erfasst (`:484-552,904-932`).

Grenzen:

- **CONFIRMED:** Producer ist eine statische Eventtyp-Zuordnung, keine
  beobachtete Prozessidentität (`:352-364,625-626`).
- **CONFIRMED:** Nur ein enger Embedder-Duplikatfall gilt als bewiesene
  vermeidbare Wiederholung (`:672-726`); „Erkenntnis“ beweist nicht automatisch
  epistemische Wirkung.
- **CONFIRMED:** Source families zählen Herkunftsfamilien von Events, nicht
  unabhängige Quellen je Claim (`:729-794`).
- **CONFIRMED · fehlende Funktion:** Backfill/Normalbetrieb ist nicht explizit
  markiert; Tages-, WAL- und Interventionsbudgets sind laut
  `docs/ROADMAP.md:49-67` noch abzuleiten.
- **CONFIRMED · Architekturgrenze:** Append-only-Trigger verbieten Ledger-
  Löschung (`schema.sql:20-30`). Retention/Aggregation darf Historie nicht
  brechen und ist kein heutiger Mechanismus.

Spätere Definition: fester Event-ID-Denominator; echte Producer-/Run-ID, wo
vorhanden; Eventfamilie und explizites Backfill-/Normal-Receipt; neue Evidenz nur
nach überprüfter semantischer Regel, notwendige Spur nach Vertrag, Wiederholung
nur bei bewiesenem No-op, sonst `unknown`. Eventrate, Payload, Hauptdatei-Delta
und WAL-Hochwasser getrennt berichten. Budgets erst aus vergleichbaren
Intervallen ableiten; niemals Ledgerhistorie löschen, um die Kennzahl zu senken.

### A1b Epistemic Yield

**CONFIRMED · vorhandene Metrik:** `genus/learning.py:154-190` definiert
Forecast-Skill gegen naive Mittelwert-Klimatologie als
`1 - model_MAE / naive_MAE`. `test_curve_skill_rewards_beating_naive` und der
Flat-Signal-Test (`tests/test_learning.py:108-125`) binden die Semantik; der
Status-Export veröffentlicht Support, Fehler und Skill
(`deploy/export_pi_status.py:73-99`).

**CONFIRMED · fehlender Nachweis/Zukunftsverbesserung:** Es fehlen allgemeine
Definitionen für unabhängige Quellen je Claim-Familie, epistemisch wirksame
Events, Belief-Transitionen je 10.000 Events und generalisierenden
Fähigkeitsgewinn. Experience-Recharakterisierung und Inquiry-Auflösung sind als
Eventtypen zählbar, aber noch keine geprüften Yield-KPIs.

Spätere Doppelachse:

- unabhängige Source-Familien je kanonischer Claim-Familie;
- Events, die einen definierten epistemischen/Projektionsübergang auslösen;
- Belief created/confirmed/weakened/superseded je 10.000 Events;
- neue gegenüber recharakterisierten Experiences;
- aufgelöste Inquiries und Nettoänderung offen;
- Forecast-Support, Fehler und Skill gegen naive Baseline;
- Delta einer eingefrorenen domänenübergreifenden Fähigkeitssuite;
- immer neben dem Event-Denominator, nie Optimierung auf viele interne Records.

### Öffentliche Verläufe: Bestände und Deltas

| Wert | Art | Befund |
|---|---|---|
| RonGen Head 1.126.763, 9 aktive Beliefs, 14 Experiences | **Bestand** | **CONFIRMED:** `GENUS_PI_STATUS/status/RonGen/latest.json`, 2026-08-09 |
| RonGen Head 1.119.702 → 1.126.763 | **Delta zwischen zwei Tagesständen:** +7.061 Events | **CONFIRMED:** `history.jsonl`, 2026-08-08→09; keine Producer-Kausalität |
| 9 Beliefs und 14 Experiences im jüngsten Vergleich | **Bestände, kein Yield** | **CONFIRMED:** keine daraus ableitbare Qualitätsänderung |
| 160.986 Events | **rollendes 24h-Fenster**, kein Since-Baseline-Delta | **CONFIRMED:** `docs/reports/2026-07-13-h0-1-baseline/live-baseline-receipt.json:21-28` |
| Haupt-DB 515.706.880 Bytes | **Point-in-time-Bestand** | **CONFIRMED:** `filesystem-snapshot.json:12-23`; kein Replay-Budget |
| 155.017 Events/4h und 29.037 von 83.174 Similarity-Kandidaten (34,9 %) | **historisches Präfixfenster vor Fix**, kein aktueller Normalbetrieb | **CONFIRMED:** `pre-fix-comparison.json:15-29` |

`pi-core` ist eine historische zweite Core-Zeitreihe und darf nicht von RonGen
subtrahiert werden. Die öffentlichen Bestände beweisen weder Ursache noch
epistemischen Gewinn; A1 benötigt disjunkte Intervalle und definierte
Transitionszähler.

## 17. Parallel erlaubte Entwickler-Loop-Forschung

Planungsgrenze:

- **human-owned critical lane:** A0 ist der einzige mergefähige Produktpfad im
  kritischen `GENUS_PI_SEED`-Kern. Menschliche Verantwortung umfasst Schema,
  Ledger, Seal, Anchor, Governance, kritische Deploywege, Abnahme und Merge.
- **isolated non-production learning lane:** Parallelversuche sind nur in
  synthetischen Repositories, getrennten Worktrees, `GENUS_EGG`, `GENUS_CORE`
  oder eindeutig unkritischen, nicht produktiv gemergten Aufgaben erlaubt.

Es gibt keinen konkurrierenden Produkt-Merge, keine Rechteausweitung und keine
kritischen Dateien im Modellscope. Das ist kein zweiter aktiver Produktpfad.
Belege: `docs/ROADMAP.md:21-42,264-267`,
`docs/design/SELF_CODING.md:42-53,118-122,163-172`, ADR-0004.

## 18. Nicht-Ziele

- keine Implementierung oder Ausführung einer Migration;
- keine Änderung von `schema.sql`, Runtime-, Deploy-, CI- oder Testcode;
- kein Öffnen oder Verändern des Produkt-Ledgers;
- kein Reseal und keine neue Seal-Epoche;
- kein echter Anchor, keine Signatur, kein Schlüssel und keine Key-Custody-
  Entscheidung;
- keine Änderung von Branch Protection, Rulesets, Deploy Keys oder anderen
  GitHub-Einstellungen;
- keine angenommene ADR, keine Priorisierung, kein Update von `NOW.md` oder
  `ROADMAP.md`;
- keine A1-KPI-/Budgetimplementierung;
- keine Bearbeitung des unbekannten Handbuchartefakts und keine Implementierung
  seines vorgeschlagenen Snapshot-Manifests;
- kein Commit, Push oder Pull Request.

## 19. Evidence Appendix mit Dateien, Zeilen, Tests und Befehlen

### Kanonische Dokumente

- `README.md:3-9,54-69,135-164` — Ledger/Projektionen, Core/Membrane,
  Quality Gate und Dokumentautorität.
- `docs/README.md:24-58,95-104,136-148` — Statushierarchie, kanonische
  Autoritäten, datierte Reports und Pflegevertrag.
- `docs/CHARTER.md:65-95,107-109` — menschliche Gates sowie NOW-/ROADMAP-
  Autorität.
- `docs/ROADMAP.md:21-42,44-81,246-267` — ein aktiver Produktpfad,
  Abhängigkeiten, H0/Event Economy und Merge-Gate.
- `docs/ARCHITECTURE.md:43-60,88-112,207-240,281-345` — append-only Ledger,
  Replay, Schema/Core, Change Trust, Dependency Direction und Grenzen.
- `docs/EVENT_CONTRACT.md:17-83,135-193` — Eventkatalog, Replay-, Seal- und
  Vertragssicherheit.
- `docs/SECURITY_MODEL.md:222-270,352-390` — Seal/Anchor, Reseal-Zeremonie,
  Incident und offene signierte Zeit.
- `docs/QUALITY.md:11-27,50-84,122-151` — Replay-No-Write, Gates und DoD.
- `docs/design/SELF_CODING.md:10-53,118-122,163-172` — beaufsichtigter Ablauf
  und kritische Grenzen.
- ADR-0001 bis ADR-0004 — Core/Membrane, Change Trust, Growth Loop und
  supervised Self-Coding; alle im Repo als accepted geführt.

### Code und Deploypfade

- `genus/db.py:16-57,141-170`; `schema.sql:1-224` — Connect, read-only Open,
  implizites Schema und Trigger.
- `genus/ledger.py:8-32`; `genus/sealing.py:33-71,96-208` — Append, Epoch,
  Verifier, Reseal und vollständiges Laden.
- `genus/anchor.py:12-15,23-116,154-195` — Anchorinhalt, Nullsignatur,
  Verifikation und Dateiname.
- `genus/event_router.py:117-131,197-272` — zwölf Replayziele, `fetchall`,
  Löschen und Projector-Loop.
- `genus/integrity.py:233-307,713-895` — In-Memory-Replay,
  Vollsnapshot und vollständige Projektionsaufnahme.
- `genus/cli.py:72-82,1819-1861,1976-2060,2079-2156` — Connection,
  Replaytransaktion, Reseal, Anchor und unvollständiger Snapshot.
- `.github/workflows/ci.yml:45-88` — frische Replay-DB, danach leere
  Präfixversiegelung und Anchor.
- `deploy/export_pi_status.py:22-27,55-99,121-168,240-246` — DB-Open,
  Statusmetriken/-writes und Anchortext.
- `deploy/pi_publish_status.sh:22-73`; `deploy/setup_pi_status_key.ps1:40-83`;
  `deploy/pi_deploy.sh:91-129` — Publish, Key-Setup und wiederholte Replays.

### Relevante Tests

- Schema: `test_init_schema_adds_lifecycle_columns_to_existing_projection_tables`,
  `test_init_schema_adds_sealing_columns_to_existing_event_log`,
  `test_readonly_connection_cannot_write_or_migrate`.
- Golden-/Replay-Komponenten:
  `test_legacy_prefix_tampering_is_detected_by_genesis`,
  `test_replay_is_deterministic_with_sealing`,
  `test_belief_stability_is_replay_stable_and_integrity_passes`,
  `test_lifecycle_replay_stable`, `test_experience_replay_is_stable`,
  `test_governance_replay_stable`,
  `test_forecast_events_pass_integrity_and_are_replay_stable`.
- Verträge: `test_jeder_geschriebene_event_typ_ist_entschieden`,
  `test_projection_target_contract_matches_router_schema_replay_and_integrity`
  und die Event-Contract-Docs-Tests.
- Seal/Anchor: `test_reseal_repairs_a_forked_chain`,
  `test_open_epoch_is_idempotent`, adaptive Reseal-/Tail-Truncation-Tests in
  `tests/test_sealing.py:168-276` und `tests/test_anchor.py:136-203`.
- Transaktion: `test_replay_command_holds_writer_gate_through_comparison`.

### Ausgeführte read-only bzw. temporäre Befehle

```text
Get-Location
git status --short
git rev-parse HEAD
git log -1 --oneline
git remote -v
.venv\Scripts\python.exe --version
rg / Get-Content / Select-String auf den in diesem Appendix genannten Dateien
.venv\Scripts\python.exe -B -m pytest --collect-only -q -p no:cacheprovider
.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider \
  tests/test_db_hardening.py tests/test_ledger.py tests/test_sealing.py \
  tests/test_anchor.py tests/test_integrity.py tests/test_event_vertrag.py \
  tests/test_event_contract_docs.py tests/test_cli.py tests/test_kartografie.py \
  tests/test_learning.py tests/test_belief_stability.py tests/test_lifecycle.py \
  tests/test_experience.py tests/test_governance.py
```

Ergebnis: `1499 tests collected`; fokussiert `141 passed in 30.12s`. Python lief
mit `-B`, Pytest ohne Cacheprovider; Test-Fixtures nutzen temporäre/synthetische
DBs (`tests/conftest.py:26-44`).

Nach Erstellung des Reports liefen zusätzlich
`tests/test_docs_structure.py`, `tests/test_event_contract_docs.py` und
`tests/test_atlas_facts.py`: `9 passed in 1.98s`.

Finale Scope-Prüfung:

```text
git diff --check
→ Exit 0, keine Ausgabe

git status --short
→  M docs/README.md
→ ?? docs/reports/2026-08-09-a0-foundation-audit.md

git diff --stat
→ docs/README.md | 1 +
```

`git diff --stat` zählt ohne Staging keine untracked Datei. Die vollständige
Änderungsliste aus `git status --short` besteht exakt aus:

- `docs/README.md`
- `docs/reports/2026-08-09-a0-foundation-audit.md`

Gezielte Repo-Suchen umfassten `schema_migrations`, `PRAGMA user_version`,
`ALTER TABLE`, Golden-/Fixture-Dateien, Replay-Aufrufer, Projektionsdigests,
Batch/Benchmark/RSS/WAL sowie Handbuchnamen. Fehlende Treffer sind nur für den
geprüften Commit und Dateibaum behauptet.

### Sanitisierte GitHub-GET-Pfade

```text
repos/WoltLab51/GENUS_PI_STATUS
repos/WoltLab51/GENUS_PI_STATUS/branches/main
repos/WoltLab51/GENUS_PI_STATUS/branches/main/protection
repos/WoltLab51/GENUS_PI_STATUS/rulesets?includes_parents=true
repos/WoltLab51/GENUS_PI_STATUS/keys
repos/WoltLab51/GENUS_PI_STATUS/git/trees/main?recursive=1
repos/WoltLab51/GENUS_PI_STATUS/contents/anchors/...
repos/WoltLab51/GENUS_PI_STATUS/contents/status/RonGen/...
repos/WoltLab51/GENUS_PI_SEED
repos/WoltLab51/GENUS_PI_SEED/branches/main
repos/WoltLab51/GENUS_PI_SEED/rulesets?includes_parents=true
repos/WoltLab51/GENUS_PI_SEED/keys
```

Protection-GET für STATUS ergab 404 „Branch not protected“, Branch
`protected=false`, Rulesets `[]`. Deploy-Key-Metadaten wurden auf Anzahl, Titel,
Verified-, Read-only- und Erstellzeitfelder beschränkt; kein Keywert/Secret wurde
ausgegeben. Ursprungscommits der geprüften Mechanismen sind unter anderem
`2bf67e6` (Sealing), `4ebeefd` (Anchors), `408f55a` (Reseal), `dd07d6d`
(Status-Publish) und `f0149bd` (Publish-Sync).

## 20. Offene menschliche Entscheidungen

1. Welche Schema-Version bezeichnet den heutigen Ausgangspunkt, welche
   Altversionen werden offiziell unterstützt und wann muss Startup hart
   verweigern?
2. Wer besitzt und prüft Golden Fixture, Datenschutzfreigabe und unabhängige
   Projektionsorakel; wie werden legitime Oracle-Änderungen genehmigt?
3. Welche Pi-Budgets gelten für Zeit, Peak RSS, WAL und Writer-Lock, und folgt
   daraus Volltransaktion oder Shadow-Projektion?
4. Welcher Fehlerzustand rechtfertigt überhaupt einen Reseal; soll ein intakter
   `--force`-Pfad entfallen?
5. Wie sieht der Multi-Epoch-/Repair-Vertrag aus, und welche alte Geschichte
   darf ausdrücklich **nicht** umgeschrieben werden?
6. Welche Anchor-v2-Kanonisierung, Signatur und Trust-/Revocation-Semantik wird
   angenommen?
7. Dient ein Hardware-Token oder ein verschlüsselter Workstation-Key als
   Primärsignierer; wer hält das Offline-Recovery-Medium und welche
   Mehrpersonenregel gilt?
8. Auf welchem Host liegt der heutige Status-Deploy-Key tatsächlich, und wie
   schnell werden Rechte, Branch-Regeln und unabhängige Verwahrung gehärtet?
9. Welche A1-Regeln definieren neue Evidenz, notwendigen Trace, bewiesenen No-op
   und epistemische Transition; welche Budgets folgen erst nach Messung?
10. Existiert ein offizielles Handbuch-v1.0-Artefakt außerhalb dieses Repos, und
    wer genehmigt sein minimales Snapshot-/Drift-Manifest?

Bis diese Entscheidungen über den vorgesehenen menschlichen Governance-Pfad
angenommen sind, bleibt dieser Report Evidenz und kein Implementierungsauftrag.

**No runtime, schema, ledger, seal, anchor, GitHub setting or production data was modified.**
