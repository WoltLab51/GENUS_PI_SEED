# ADR-0010 — Human-Supervised Model Assistance in A0 Critical Verification Work

> **Status:** accepted · **Datum:** 2026-08-10
>
> **Owner:** Ronny
>
> **Scope:** ausschließlich human-supervised A0.2 verification work

## 1. Context

[ADR-0006](ADR-0006-GOLDEN-LEDGER-ORACLE.md) verlangt vor dem ersten
Golden-Ledger- oder Oracle-Artefakt benannte menschliche Rollen und einen
geprüften Eingangskontrakt. [ADR-0009](ADR-0009-HUMAN-OWNED-CRITICAL-LANE.md)
hält kritische Dateien aus dem autonomen Modellscope heraus und weist
Implementierungsautorenschaft, Patchhoheit, Review, Commit und Freigabe dem
Menschen zu.

Ein früherer A0.2-Auftrag kollidierte mit diesen Grenzen und wurde vor dem ersten
kritischen Artefakt gestoppt. Ronny trifft deshalb diese engere
Spezialentscheidung für interaktive, menschlich geführte Modellassistenz.

## 2. Problem

A0.2 braucht eine statische synthetische Fixture, ein vom Runtime-Code
unabhängiges Oracle und Tests gegen bestehende kritische Verträge. Eine
allgemeine Critical-Scope-Autorität für Modelle würde ADR-0009 aushöhlen. Ein
vollständiges Assistenzverbot würde dagegen auch eine von Ronny einzeln
beauftragte, read-only und test-only begrenzte Werkzeugnutzung ausschließen.

Die Architektur muss deshalb zwischen einem autonomen Modellpatch und einem
Kandidaten unterscheiden, den ein Modell nur als nicht autoritatives Werkzeug
unter unmittelbarer menschlicher Führung erzeugt.

## 3. Decision

A0 bleibt eine human-owned critical lane. Ronny darf Codex als eng begrenztes,
nicht autoritatives Werkzeug für A0.2 einsetzen.

Ronny darf Codex für A0.2 beauftragen:

- vorab benannte kritische Quellen read-only analysieren;
- Testfälle und Gegenbeispiele vorschlagen;
- ausschließlich test-only Kandidatendateien in einem vorab benannten Scope
  erstellen;
- Tests gegen temporäre, vollständig synthetische Datenbanken ausführen;
- Kandidatendiffs und Fehler erklären.

Diese Erlaubnis gehört Ronny als menschlichem Verantwortlichen. Sie verleiht
weder Codex noch GENUS eigene Critical-Scope-Autorität.

## 4. Allowed read-only source scope

Erst nach Annahme des
[A0.2 Entry Contract](../reviews/A0_2_GOLDEN_LEDGER_ENTRY_CONTRACT.md) und einem
neuen ausdrücklichen A0.2-Implementierungsauftrag darf Ronny Codex ausschließlich
folgende namentlich eingefrorene Quellen read-only betrachten lassen:

- `genus/db.py`
- `genus/ledger.py`
- `genus/sealing.py`
- `genus/anchor.py`
- `genus/event_router.py`
- `genus/integrity.py`
- `schema.sql`
- `tests/test_anchor.py`
- `tests/test_integrity.py`
- `tests/test_ledger.py`
- `tests/test_sealing.py`
- `docs/ARCHITECTURE.md`
- `docs/EVENT_CONTRACT.md`
- `docs/SECURITY_MODEL.md`
- `docs/QUALITY.md`
- `docs/decisions/ADR-0006-GOLDEN-LEDGER-ORACLE.md`
- `docs/decisions/ADR-0009-HUMAN-OWNED-CRITICAL-LANE.md`
- `docs/decisions/ADR-0010-HUMAN-SUPERVISED-MODEL-ASSISTANCE-A0.md`
- `docs/reviews/A0_2_GOLDEN_LEDGER_ENTRY_CONTRACT.md`

`70565fe` ist die Code-/Test-Ausgangsbaseline vor dieser Docs-Entscheidung, kein
Versionsbezeichner für die erst danach angenommenen Governance-Dokumente. Ein
späterer Implementierungslauf erfasst seinen sauberen HEAD; der Pfadsatz bleibt
unverändert und jede inhaltliche oder pfadbezogene Scope-Erweiterung verlangt
Ronnys erneute Freigabe.

Die Freigabe umfasst keine Produktdatenbank, keine produktiven Anchors, keine
Secrets, keine Hostartefakte und keine sonstigen kritischen Dateien.

## 5. Allowed test-only write scope

Nach derselben ausdrücklichen Freigabe darf Ronny Codex Kandidaten
ausschließlich in folgenden Pfaden erzeugen oder ändern lassen:

- `tests/fixtures/golden_ledger_v1/*`
- `tests/golden_ledger_support.py`
- `tests/test_golden_ledger_oracle.py`

Jeder andere persistente Repository-Kandidatenpfad ist verboten. Disposable
SQLite-/WAL-/SHM-Testwrites sind ausschließlich unter den Temp- und
Cache-Grenzen des Entry Contracts erlaubt. Eine Scope-Erweiterung benötigt eine
neue menschliche Entscheidung vor der Änderung.

## 6. Human roles

| Rolle | Träger |
|---|---|
| Corpus Owner | Ronny |
| Datenschutzprüfer | Ronny |
| Oracle Reviewer | Ronny, in einem ausdrücklich getrennten zweiten Review-Durchlauf |
| Canonicalization and Digest Contract Owner | Ronny |
| Human Implementer and Committer of Record | Ronny |
| Non-authoritative Model Assistant | Codex |

In diesem privaten Ein-Personen-Projekt darf Ronny mehrere menschliche Rollen
tragen. Corpus-Erstellung und Oracle-Abnahme bleiben dennoch getrennte
Handlungen. Codex ist niemals menschlicher Reviewer oder Freigeber. Grüne Tests
ersetzen keine menschliche Oracle-Abnahme. Eine spätere zweite menschliche
Prüfung ist willkommen, aber keine Voraussetzung für Golden Ledger v1.

## 7. Candidate status

Alle von Codex erzeugten A0.2-Dateien tragen bis zur getrennten menschlichen
Abnahme den Status:

> **CANDIDATE — PENDING HUMAN REVIEW**

Dieser Status darf nicht durch Testgrün, einen Modellkommentar oder eine
automatische Ableitung aufgehoben werden. Nur Ronny darf einen Kandidaten nach
dem getrennten Review annehmen, ändern, verwerfen und später committen.

## 8. Oracle independence

Codex darf weder die kanonische Ereignismenge allein bestimmen noch erwartete
semantische Projektionszeilen oder Digests zur Testlaufzeit aus dem aktuell
geprüften Replay-/Projektorcode erzeugen. Die Erwartungen werden aus
Event-Vertrag, dokumentierter Projektorsemantik und handprüfbarer Ereigniskette
hergeleitet und statisch reviewbar festgehalten.

Ein lokaler Runtime-Lauf darf nur als Gegenprüfung dienen. Er besitzt keine
Autorität, das Oracle zu definieren oder automatisch zu aktualisieren. Codex
darf keine menschlichen Review-Checkboxen markieren.

## 9. Human patch sovereignty

Ronny behält vollständig:

- Implementierungsautorenschaft und Patchhoheit;
- Entscheidung über Corpus und Oracle;
- Datenschutz- und Oracle-Abnahme;
- Annahme, Änderung oder Verwerfung jedes Kandidatendiffs;
- Commit, Merge, Push, Deploy und spätere Laufzeitfreigabe.

Codex darf einen Kandidaten erzeugen und erklären, aber nicht dessen Annahme
behaupten oder technisch vollziehen.

## 10. Prohibited effects

Codex darf in diesem Scope nicht:

- Runtime-, Schema-, Replay-, Integrity-, Seal-, Anchor- oder Deploy-Code ändern;
- Produktdaten lesen oder eine Produktdatenbank beziehungsweise produktive
  Anchors öffnen;
- neue Eventtypen oder Runtime-Verträge erfinden;
- ein Oracle aus dem aktuellen Replay ableiten;
- eigene Artefakte menschlich freigeben oder Reviewpunkte abhaken;
- committen, mergen, pushen oder deployen;
- Rechte des GENUS-Self-Coding-Loops erweitern.

## 11. Relationship to ADR-0006

ADR-0006 bleibt vollständig gültig. Der zugehörige Entry Contract benennt vor
Artefakterzeugung Rollen, Corpusgrenzen, JSONL-Kanonisierung,
Projektionsnormalisierung, Digests, menschliches Review und Stop Conditions.
ADR-0010 ändert weder Oracle-Inhalt noch Unabhängigkeitsmaßstab; es regelt nur,
wie Ronny Codex innerhalb dieser Vorbedingungen als Werkzeug einsetzen darf.

## 12. Relationship to ADR-0009

ADR-0010 ersetzt oder lockert ADR-0009 nicht allgemein. Es ist die engere
Spezialentscheidung ausschließlich für human-supervised A0.2 verification
work. Nur soweit ADR-0009 kritische Dateien und kritischen Quelltext absolut aus
dem Modellscope ausschließt, hat ADR-0010 für Ronnys namentlich begrenzte,
read-only Nutzung von Codex in A0.2 Vorrang. Alle übrigen Grenzen aus ADR-0009
bleiben unverändert. Insbesondere bleibt der autonome, GENUS-generierte oder
durch die Coding-Membran laufende Modellpfad im Critical Scope verboten. Aus
dieser Ausnahme entstehen keine dauerhaften oder übertragbaren Modellrechte.

## 13. Consequences

- A0.2 darf nach einem neuen Auftrag test-only Kandidaten erhalten, ohne die
  human-owned Critical Lane aufzugeben.
- Jede Kandidatendatei bleibt bis Ronnys getrenntem Review sichtbar offen.
- Der erlaubte Read- und Write-Scope ist klein, statisch und überprüfbar.
- Menschliche Mehrfachrollen sind für v1 zulässig, die Handlungen bleiben aber
  zeitlich und dokumentarisch getrennt.
- Ein zweiter menschlicher Oracle-Reviewer kann später additiv hinzukommen.

## 14. Failure modes

Die Entscheidung ist verletzt, wenn insbesondere:

- der Kandidat als akzeptiertes Oracle dargestellt wird;
- erwartete Zeilen oder Digests aus dem aktuellen Runtime-Ergebnis übernommen
  werden, ohne unabhängige menschliche Herleitung;
- Corpus-Erstellung und Oracle-Abnahme zu einer ungekennzeichneten Handlung
  verschmelzen;
- der Modellscope über die benannten Dateien hinauswächst;
- echte oder identifizierende Daten in Fixture, Prompt, Log oder Testausgabe
  gelangen;
- ein unkritisch wirkender Helfer Runtime- oder Schemaautorität erhält;
- Testgrün als menschliche Freigabe behandelt wird.

## 15. Revocation / stop conditions

Die Modellassistenz stoppt sofort bei:

- Widerspruch zu ADR-0006, ADR-0009, ADR-0010 oder dem Entry Contract;
- Produktdaten oder identifizierenden Inhalten im Corpus;
- notwendiger Änderung an Runtime, Schema, Replay, Integrity, Seal, Anchor,
  Deploy oder CI;
- Ableitung des Oracles aus aktuellem Replay-/Projektoroutput;
- unklarem Eventvertrag oder ungeklärter Kanonisierung;
- fremden Änderungen im Worktree;
- erforderlichem Zugriff auf Produktdatenbank, Produktanchor, Secret oder Netz;
- jeder nicht vorab menschlich freigegebenen Scope-Erweiterung.

Ronny kann die Erlaubnis jederzeit ohne Ersatzpfad widerrufen. Ein gestoppter
Lauf hinterlässt keine still akzeptierten Teilresultate.

## 16. Non-goals

Dieser ADR:

- erzeugt kein Golden Ledger, Oracle, Testartefakt oder Digest;
- ändert keinen Runtime-, Schema-, Replay-, Seal-, Anchor- oder Deploy-Code;
- autorisiert keine Produktdaten und keinen Produktlauf;
- autorisiert keinen Commit, Push, Merge, Deploy oder Pull Request durch Codex;
- öffnet keine allgemeine Critical-Scope-Autorität für Modelle;
- erweitert weder ADR-0004 noch den GENUS-Self-Coding-Loop.
