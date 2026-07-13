# GENUS Operations

> **Status:** current navigation
> **Zuletzt verifiziert:** 2026-07-13

Diese Seite ist der Lotse. Ausführbare Anweisungen werden nicht mehrfach gepflegt.

## Häufige Wege

| Aufgabe | Quelle |
|---|---|
| Pi erstmals einrichten | [Sicheres First Setup](../../deploy/README.md#sicheres-first-setup) |
| auf `main` aktualisieren | [Deploy](../../deploy/README.md) |
| Dienste prüfen | [Systemd-Dienste](../../deploy/README.md#systemd-dienste) |
| 24/48/72-Profil starten oder prüfen | [Betriebsprofil](../../deploy/README.md#244872-stunden-betriebsprofil) |
| Antwortqualität hermetisch prüfen | [Alltagsprobe](../design/ANSWER_QUALITY.md) |
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
genus betriebsprofil status
genus alltagsprobe --contracts-only
systemctl --failed
systemctl status genus-learner.service genus-telegram-bot.service
systemctl list-timers genus-network-watchdog.timer
```

## Antwortqualität prüfen

Die Alltagsprobe braucht weder `GENUS_DB_PATH` noch einen laufenden Dienst. Sie erzeugt für
jeden Fall eine frische In-Memory-Datenbank, sät ausschließlich synthetisches Wissen und
lädt weder Modell noch Netzwerk oder Pi-Ledger.

```bash
# Harte Verträge als automatisches Gate
genus alltagsprobe --contracts-only

# Exakte synthetische Dialoge für die menschliche Abnahme
genus alltagsprobe --details

# Vollständige maschinen- oder menschenlesbare Berichte
genus alltagsprobe --json-output
genus alltagsprobe --markdown

# Optional eine andere hashgebundene Reviewdatei verwenden
genus alltagsprobe --reviews /pfad/zu/reviews.json --details
```

Der aktuelle Stand ist **85/85 harte Verträge** und **0/17 menschlich akzeptierte Fälle**.
Deshalb endet der normale Aufruf absichtlich mit Exitcode 2. Die Exitcodes bedeuten:

| Code | Bedeutung |
|---:|---|
| `0` | Alle harten Verträge und alle menschlichen Reviews tragen – oder `--contracts-only` wurde bei grünen Verträgen verwendet. |
| `1` | Mindestens ein harter Vertrag ist verletzt. |
| `2` | Die harten Verträge sind grün, aber mindestens eine menschliche Wertung fehlt, ist veraltet oder trägt nicht. |

Die Standardreviews stehen in
[`docs/reviews/ALLTAGSPROBE_V1.json`](../reviews/ALLTAGSPROBE_V1.json). `--details` zeigt
den exakten Wortlaut und kurze Fall- und Antwort-Hashes; der
[generierte Bericht](../generated/ANTWORTQUALITAET.md) ergänzt kopierbare Vorlagen mit den
vollständigen Hashes. Nur wenn **Ton** und **Nutzen** beide `traegt` sind und beide Hashes
noch passen, zählt der Fall als akzeptiert. `holprig`,
`unbrauchbar`, fehlende oder nach einer Änderung veraltete Reviews bleiben sichtbar offen.
Eine vollständige Erklärung steht im
[Designvertrag zur Antwortqualität](../design/ANSWER_QUALITY.md).

## Betriebsprinzipien

- Genau ein produktiver Ledgerpfad wird explizit gesetzt.
- Produktdienste laufen als GENUS-Benutzer, nicht als Root.
- Der privilegierte Watchdog läuft nur aus `/usr/local/libexec/genus`.
- Secrets stehen nie im Repository oder in world-readable Units.
- Betriebsprofil-Meldungen gehen begrenzt unter `genus-betriebsprofil` an Journal/Syslog;
  Diagnose darf keine neue Datenbank erzeugen.
- Das Betriebsprofil schreibt nur private Aggregate außerhalb des Ledgers und startet nie still.
- Die Alltagsprobe schreibt weder ins Produkt-Ledger noch aus menschlichen Reviews zurück in
  Strategie, Modell oder Wissensgraph.
- Mehr als zwei Stunden verpasste Profilpunkte brechen die Reihe ab; Restore oder Ledger-Tausch
  ebenso. Neu starten heißt: alten Profilordner archivieren und einen neuen Zielordner wählen.
- Ein Restore gilt erst nach Integritäts-, Seal- und Anchor-Prüfung als gelungen.

Konkrete Pfade und Installationsbefehle gehören in das
[Deploy-Runbook](../../deploy/README.md), nicht auf diese Navigationsseite.
