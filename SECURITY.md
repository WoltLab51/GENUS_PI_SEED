# Security Policy

## Supported Versions

GENUS_PI_SEED ist ein pre-1.0-Projekt. Unterstützt wird jeweils nur der
aktuelle Stand von `main`; ältere Zwischenstände werden nicht separat
gepflegt.

## Scope

Der aktuelle v0.x-Umfang ist eine lokale Python/SQLite-CLI. Das System darf
keine LLM-, HTTP-, Web- oder Worker-Abhängigkeiten verwenden. Besonders
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
