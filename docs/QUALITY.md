# GENUS Quality

> **Status:** canonical
> **Zuletzt verifiziert:** 2026-07-12
> **Besitzt:** Plan-, Bau-, Abnahme-, Dokumentations- und Laufzeitgates

Qualität bedeutet bei GENUS nicht „viele grüne Tests“. Qualität heißt: Die Behauptung
einer Änderung ist klar, ihre Grenzen sind sichtbar, ihr Verhalten ist reproduzierbar
und ihre Wirkung wird nach dem Deploy erneut geprüft.

## Die sieben Invarianten

1. **Eine epistemische Ereigniswahrheit.** Dauerhafte fachliche Kerntransitionen
   leben im Ledger. Betriebsmarker, Secrets und flüchtiges Membrangedächtnis dürfen
   außerhalb liegen, sind aber niemals eine zweite Wissenswahrheit.
2. **Ableitung bleibt Ableitung.** Projektionen und read-time Größen dürfen existieren,
   wenn Herkunft und Rekonstruktion klar sind.
3. **Keine unbegründete Magnitude.** Lernbare Schwellen werden aus Daten abgeleitet.
   Physik-, Sicherheits- und Ressourcenbudgets dürfen fest sein, müssen aber benannt,
   begründet und getestet werden.
4. **Keine stille Autorität.** Modell, Membran, Proposal und Inquiry dürfen keine
   Entscheidung vortäuschen.
5. **Replay ist Bedeutung.** Nach Replay muss dieselbe aktuelle Sicht entstehen, ohne
   neue Events zu erzeugen.
6. **Fehler werden sichtbar.** Unsicherheit, Widerspruch und Betriebsdrift werden nicht
   durch einen bequemen Default versteckt.
7. **Laufzeit gehört zur Abnahme.** Ein Merge beweist noch keine Wirkung.

## Vor dem Bauen

Eine Scheibe beginnt erst, wenn diese Fragen beantwortet sind:

- Welches konkrete Problem oder welche beobachtete Lücke wird gelöst?
- Welche bestehende Mechanik wird wiederverwendet?
- Welches Ereignis hält Input oder Transition fest?
- Welche Projektion oder read-time Sicht entsteht daraus?
- Was bleibt bewusst außerhalb des Kerns?
- Welcher Gegenfall würde die Lösung widerlegen?
- Wie wird Erfolg im echten Betrieb sichtbar?
- Welche Dokumente besitzen die geänderten Verträge?

Für neue Fähigkeiten zusätzlich:

- Generalisiert die Mechanik oder wächst nur eine Spezialfallliste?
- Wer definiert die Abnahme, wenn ein Generator den Entwurf liefert?
- Welches Event-, Zeit-, Speicher- und Außenwirkungsbudget gilt?

## Beim Bauen

### Kern-Gates

- Eventtyp und Pflichtfelder sind im [Event-Vertrag](EVENT_CONTRACT.md).
- Projektionen sind replaybar und verändern das Ledger nicht.
- Source/Derivation bleiben erhalten.
- `supported`, `contested` und `uncertain` werden nicht zusammengeschoben.
- Relationsemantik ist explizit.
- Kein neuer LLM-/HTTP-/subprocess-Import im Kern.

### Sicherheits-Gates

- Pfade, Benutzer und Privilegien sind explizit.
- Root führt keinen benutzerschreibbaren Code aus.
- Secrets erscheinen weder in Git noch in world-readable Units oder Logs.
- Externe Prozesse haben Timeout, Ausgabelimit und Ressourcenbudget.
- Eine Benutzerentscheidung kann Root höchstens einschränken.

### Test-Gates

- Positivfall, Gegenfall und Wiederholung.
- Replay-/Idempotenzfall.
- Fehler- und Rollbackpfad.
- adversarialer Fall an jeder Trust Boundary.
- Property-/Differenzialtest, wenn eine endliche Zustandsmaschine oder Graphinvariante
  unabhängig prüfbar ist.

## Dokumentations-Gate

Ein Dokumentationschange ist Teil der Implementierung, wenn sich ein Vertrag ändert.

- Neue aktuelle Zahlen werden generiert oder datiert, nicht frei kopiert.
- Jeder Dokumentpfad ist im [Index](README.md) klassifiziert.
- Interne Links sind relativ und klickbar.
- Ein Snapshot erhält `superseded by`, statt still umgeschrieben zu werden.
- Code verweist nur auf kanonische Verträge oder klar benannte ADRs als Autorität.
- Eventkatalog, Atlas-Fakten und andere ableitbare Flächen besitzen Drift-Tests.

## Abnahmefolge

```text
Scope prüfen
  → fokussierte Tests
  → vollständige Tests + Lint + Compile + Dependency Audit
  → Replay
  → Integrity
  → Seal / Anchor
  → Deploy
  → effektive Unit- und Laufzeitwerte lesen
  → ursprünglichen Fehler erneut versuchen
  → Restunsicherheit dokumentieren
```

Für den Pi bedeutet „Unit geprüft“ immer `systemctl show` der **effektiven** Werte, nicht
nur das Lesen der Quelldatei.

## Definition of Done

Eine Änderung ist fertig, wenn:

- der ursprüngliche Fehler nicht mehr reproduzierbar ist,
- alle relevanten Tests und Verträge grün sind,
- keine ungeklärte Datenmigration oder zweite Wahrheit verbleibt,
- der reale Zielbetrieb die erwarteten Werte zeigt,
- historische Artefakte erhalten oder bewusst quarantänisiert sind,
- verbleibende Unsicherheit und nächster Messpunkt benannt sind.

## PDCA als GENUS-Muster

```text
Plan: Lücke + Behauptung + Gegenbeweis
Do:   kleinste tragende Scheibe
Check: Tests + Replay + reale Wirkung
Act:  behalten, nachschärfen oder zurücknehmen
```

GENUS wendet diesen Kreis zunehmend auf sich selbst an. Genau deshalb sind
[Change Trust](decisions/ADR-0002-CHANGE-TRUST.md) und
[Wachstum als Kreislauf](decisions/ADR-0003-GROWTH-LOOP.md) keine Projektfolklore,
sondern Teil der Architektur.
