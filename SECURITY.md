# Security Policy

## Supported Versions

GENUS_PI_SEED ist ein fruehes, lokales Python/SQLite-Projekt. Unterstuetzt
wird jeweils nur der aktuelle Stand von `main`; aeltere Zwischenstaende werden
nicht separat gepflegt.

## Scope

Der aktuelle Umfang ist eine lokale Python/SQLite-CLI mit deterministischem
Ledger, Projektionen, Offline-Anchors und Pi-Self-Operation. Das System darf
keine LLM-, HTTP-, Web- oder Worker-Abhaengigkeiten verwenden. Besonders
kritische Invarianten sind:

- `event_log` ist append-only.
- `belief_projection`, `proposal_log` und `inquiry_log` sind rebuildbare
  Projektionen aus dem Ledger.
- `confidence` wird berechnet und nie gespeichert.

## Reporting a Vulnerability

Bitte melde Sicherheitsprobleme über GitHub, bevorzugt als private Security
Advisory, falls im Repository verfügbar. Wenn das nicht möglich ist, erstelle
ein knappes Issue ohne ausnutzbare Details und markiere es klar als
Sicherheitsmeldung.

Bitte füge reproduzierbare Schritte, betroffene Version bzw. Commit-SHA und
die erwartete Auswirkung hinzu. Keine Secrets, Tokens, privaten Datenbanken
oder sensiblen Hostdaten posten.
