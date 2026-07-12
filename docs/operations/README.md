# GENUS Operations

> **Status:** current navigation
> **Zuletzt verifiziert:** 2026-07-12

Diese Seite ist der Lotse. Ausführbare Anweisungen werden nicht mehrfach gepflegt.

## Häufige Wege

| Aufgabe | Quelle |
|---|---|
| Pi erstmals einrichten | [Sicheres First Setup](../../deploy/README.md#sicheres-first-setup) |
| auf `main` aktualisieren | [Deploy](../../deploy/README.md) |
| Dienste prüfen | [Systemd-Dienste](../../deploy/README.md#systemd-dienste) |
| Ledger prüfen und verankern | [Security-Modell](../SECURITY_MODEL.md) |
| aktuellen Zustand verstehen | [NOW](../NOW.md) |
| Schwachstelle melden | [Security Policy](../../SECURITY.md) |

## Schnellcheck

```bash
export GENUS_DB_PATH="$HOME/.genus/genus.sqlite3"
export GENUS_CORE_ID="mein-kern"

genus doctor
genus integrity check
genus ledger verify
systemctl --failed
systemctl status genus-learner.service genus-telegram-bot.service
systemctl list-timers genus-network-watchdog.timer
```

## Betriebsprinzipien

- Genau ein produktiver Ledgerpfad wird explizit gesetzt.
- Produktdienste laufen als GENUS-Benutzer, nicht als Root.
- Der privilegierte Watchdog läuft nur aus `/usr/local/libexec/genus`.
- Secrets stehen nie im Repository oder in world-readable Units.
- Logs gehen ins Journal; Diagnose darf keine neue Datenbank erzeugen.
- Ein Restore gilt erst nach Integritäts-, Seal- und Anchor-Prüfung als gelungen.

Konkrete Pfade und Installationsbefehle gehören in das
[Deploy-Runbook](../../deploy/README.md), nicht auf diese Navigationsseite.
