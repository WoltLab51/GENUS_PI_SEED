# GENUS Security Policy

> **Status:** current · **Zuletzt verifiziert:** 2026-07-12 · **Zweck:** vertrauliche Meldung und Sicherheitsumfang

## Unterstützte Version

GENUS ist ein frühes, lokal betriebenes Python-/SQLite-System. Sicherheitsfixes
gelten für den aktuellen Stand von `main`; ältere Zwischenstände werden nicht
separat gepflegt.

## Was zum Sicherheitsumfang gehört

GENUS besteht aus klar getrennten Zonen:

- Der deterministische Kern unter [`genus/`](genus/) verarbeitet übergebene
  Daten und schreibt Ereignisse. Ein CI-Gate weist bekannte direkte Imports
  für Netzwerk-, Prozess- und Modellzugriffe ab. Es ist ein Regressionsgate,
  keine vollständige Prozess-Sandbox; dynamische Zugriffswege brauchen
  zusätzlich Review.
- Membranen unter [`deploy/`](deploy/) dürfen mit Betriebssystem, Netzwerk und
  lokalen Modellen sprechen. Ihre Eingaben sind grundsätzlich nicht vertrauenswürdig;
  erst validierte Ereignisse gelangen in den Kern.
- Die privilegierte Pi-Membran darf systemd-Units reparieren und eng begrenzte
  Netzwerk-Recovery ausführen. Ihr Watchdog und ihre Installer starten aus
  einem root-eigenen Verzeichnis. Auf der verifizierten Pi-Installation werden
  Aufrufe in den nutzerbeschreibbaren Checkout zuvor mit `runuser` auf die
  GENUS-Identität herabgestuft; diese Laufzeitvoraussetzung ist Teil des
  Sicherheitsmodells.

Die vollständigen Grenzen, Garantien und Betriebsverfahren stehen im
[kanonischen Sicherheitsmodell](docs/SECURITY_MODEL.md). Der zuletzt
abgeschlossene Repo-/Pi-Härtungslauf ist im
[Audit vom 12. Juli 2026](docs/reports/2026-07-12-hardening-audit.md)
festgehalten.

Besonders kritische Invarianten sind:

- `event_log` ist in normalen Schreibpfaden append-only.
- Projektionen sind aus dem Ledger deterministisch wiederherstellbar.
- `confidence` wird gelesen und berechnet, nicht als Wahrheit gespeichert.
- Lokale Siegel werden gegen die gesamte versiegelte Epoche geprüft; ein
  extern verwahrter Anchor bezeugt genau den Präfix bis zu seinem Head.
- Produktive Dienste laufen am ausdrücklich gesetzten Nutzer-, Home- und
  Datenbankpfad. Eine zufällige Streu-Datenbank ist niemals stillschweigend die
  neue Wahrheit.
- Vorschlag, Review, Entscheidung und Ausführung bleiben getrennte Akte.

## Ehrliche Grenze

Ein Angreifer mit vollständiger Kontrolle über den GENUS-Nutzer kann dessen
Code und lokale Daten verändern. Ein extern verwahrter Anchor macht eine
nachträgliche Umschreibung des bereits bezeugten Ledger-Präfixes erkennbar,
schützt aber weder den jüngeren, noch nicht verankerten Tail noch die
Verfügbarkeit des Pi. Vollständiger Root- oder physischer Hostzugriff liegt
außerhalb dessen, was das Repository allein verhindern kann.

## Sicherheitslücken melden

Bitte melde eine Schwachstelle bevorzugt über eine **private GitHub Security
Advisory** dieses Repositories. Falls diese Funktion nicht verfügbar ist,
erstelle nur ein knappes öffentliches Issue ohne Exploit, Secret oder sensible
Hostdaten und bitte dort um einen privaten Rückkanal.

Eine gute Meldung enthält:

- betroffene Version oder Commit-SHA;
- betroffene Zone: Kern, Ledger, Membran, systemd/Root oder Lieferkette;
- reproduzierbare Schritte mit harmlosen Testdaten;
- erwartete und beobachtete Auswirkung;
- Hinweise auf bereits versuchte Gegenmaßnahmen.

Bitte niemals Tokens, Telegram-IDs, private Datenbanken, Anchor-Dateien mit
persönlichen Metadaten, Nutzer-/Core-Kennungen, Hostpfade, Hostnamen oder
vollständige Logs öffentlich posten.
Erhaltene Beweismittel sollten unverändert und gehasht aufbewahrt werden.
