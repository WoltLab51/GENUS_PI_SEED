# GENUS Runtime-Kartografie · Pi-Audit vom 2026-07-13

> **Status:** report · datierter, read-only erhobener Befund
> **Quelle:** sanitisierte SSH-Prüfung von `ronny@pi` und Abgleich mit dem Repo
> **Snapshot:** 2026-07-13, ca. 11:55 CEST
> **Datenschutz:** keine Token, Chat-/Nutzer-IDs oder Ledgerinhalte gelesen oder exportiert

Dieser Report ist die Ist-Evidenz hinter der Betriebsansicht der generierten
[GENUS-Kartografie](../visual/GENUS_KARTOGRAFIE.html). Er ist **kein Live-Monitor**:
`genus kartografie check` prüft Quellbaum, Verträge und die unveränderte Einbindung dieses
Snapshots, verbindet sich aber nicht selbst mit dem Pi.

## Sanitisierter Ist-Zustand

| Laufzeitknoten | Beobachtung |
|---|---|
| Pi-Codecheckout | `main`, sauber, zum Audit auf dem erwarteten Deploy-Stand |
| Kern-Venv | installiert und funktionsfähig |
| Produktives SQLite-Ledger | WAL aktiv, genau ein produktiver Fund, Integrität gesund |
| Cron-Vertrag (17 Jobs) | installiert; häufige und nächtliche Jobs mit aktuellen Ticks |
| Netzwerk-Watchdog-Timer | aktiv, Fünf-Minuten-Takt |
| Root-Watchdog | letzter Lauf erfolgreich |
| Root-eigene Helper-Kopien | bytegleich zum Repo |
| Permanenter Learner | aktiv, unprivilegiert, Idle-Scheduling |
| Telegram-Bot | aktiv, gehärtet, Stimme aus, ein Besitzervertrag |
| Qwen-Deuter | installiert und im Bot lazy geladen |
| FastEmbed Sense-Bridge | installiert; Modellcache lag jedoch flüchtig unter `/tmp` |
| Lokale Modellablage | vorhanden; mehrere nicht aktive Werkstattmodelle |
| H0.1-Betriebsprofil | Baseline-Reihe gestartet |
| Physisches Backupziel | getrenntes Dateisystem, aktuelle geprüfte Snapshots |
| Status-Publisher | aktiver nächtlicher, sanitiserter Export |
| Cron-/Doctor-/Statuslogs | aktiv, aber ohne Rotation oder Größenvertrag |

Zusätzlich waren NTP synchron, keine System-Unit fehlgeschlagen und kein GENUS-eigener
TCP-/UDP-Listener sichtbar. Produkt-Ledger und Backup lagen auf getrennten Dateisystemen.

## Vertrauenspfad

```text
Internet / Telegram / Modelle
        ↓ untrusted
deploy/-Membranen als unprivilegierter GENUS-Login
        ↓ validierte Events
privater GENUS-State + Ledger
        ↓ Projektionen
deterministischer Kern

root: systemd-Verträge + root-eigene Watchdog-Helper
        ↓ prüft/repariert
unprivilegierte Learner-/Telegram-Dienste
```

## Soll-/Ist-Drift

### D1 · FastEmbed-Cache flüchtig — hoch

Das Embedder-Venv ist persistent, das geladene Modell lag live aber in einem temporären
Cache. Boot-/Tmp-Bereinigung kann deshalb einen überraschenden Netzdownload auslösen.
Soll: privater persistenter Cache, vorab geladen, Modellidentität und Hash inventarisiert.

### D2 · Unit-Drift beim Chat-Wortlernen — mittel

Die Installer deklarieren `GENUS_CHAT_WORD_LEARNING=0`; die live geladenen Units verließen
sich beim Audit noch auf denselben Code-Default. Verhalten und Sollwert stimmten überein,
die deklarative Unit jedoch nicht. Der Watchdog prüfte diese Eigenschaft nicht vollständig.

### D3 · Backuprechte — hoch

Backupfunktion und physische Trennung waren gesund. Zielverzeichnis und Snapshotdateien
hatten jedoch keinen eigenständigen `0700`-/`0600`-Vertrag. Der private Home-Vorfahre
schützte im eingebauten Zustand, nicht zwingend nach Ausbau oder anderer Einhängung.

### D4 · Unbegrenzte Betriebslogs — mittel

Cron-, Doctor- und Statuslogs wurden ohne Rotation fortgeschrieben; das Cronlog enthielt
außerdem alte NUL-Bytes. Soll: private Größen-/Generationsgrenze oder Journal-only.

### D5 · Uneinheitliche Rechte in der privaten Zone — mittel

Der Elternpfad war `0700`, einzelne Ledger-, State- und Logdateien aber nicht durchgängig
`0600`. Rohtextfähiger Membranzustand braucht unabhängig vom Elternpfad einen Eigenvertrag.

### D6 · Modellinventar — niedrig

Mehrere Coder-Modelle waren nicht Teil des Dauerbetriebs. Rollen, Aktualität und bewusste
Archivierung sollten in einem Modellmanifest stehen.

### D7 · Breite Learner-Vertrauenszone — architektonisch

Der netzaktive Learner lief als derselbe Nutzer wie Ledger und privater Membranzustand.
Ein eigener Service-Nutzer oder enge `ReadWritePaths` würden den Ausfallradius verkleinern.

### D8 · Cron-Zeitzone — niedrig

Cron wurde in Europe/Berlin interpretiert, Tickzeilen waren UTC. Sommer-/Winterzeit und
der gewünschte lokale beziehungsweise UTC-Vertrag sollten im Runbook explizit werden.

## Repo-Evidenz

- Deploykette: `deploy/pi_deploy.sh`
- Cronvertrag: `deploy/pi_install_cron.sh`
- Watchdog: `deploy/pi_install_network_watchdog.sh`, `deploy/pi_network_watchdog.sh`
- Learner: `deploy/pi_install_learner.sh`, `deploy/pi_learn.sh`
- Telegram: `deploy/pi_install_telegram_bot.sh`, `deploy/telegram_bot.py`
- Embedder: `deploy/pi_install_embedder.sh`
- Backup: `deploy/backup_ledger_to_sd.sh`
- Status: `deploy/pi_publish_status.sh`
- Betriebsprofil: `deploy/pi_betriebsprofil_capture.sh`

## Repo-Nachtrag: H1-Antwortpilot

Nach diesem read-only Pi-Snapshot wurde im Repo der erste geschlossene H1-
Vertikalschnitt ergänzt. Dieser Nachtrag verändert die historischen Laufzeitbeobachtungen
oben nicht und behauptet insbesondere keine rückwirkende Pi-Evidenz.

- Definitionen und Beziehungen können als `AnswerDraft` mit Claims, vorhandener
  Provenienz, Unsicherheit und treuem Fallback gerendert werden.
- Ein `DialogueFrame` bindet Absicht, strukturelle Ankerkontinuität, Follow-up und
  kontrollierte Persönlichkeitseinstellung für genau diese Darstellung — ohne Rohtext.
- Erst ein gültiger Telegram-Zustellbeleg erzeugt `response_outcome_recorded`; seine
  Event-ID ist die Response-ID und bestätigt zugleich den RAM-Session-Zug.
- Reine 👍-/👎-Nachrichten und enge Korrektur-Cues werden als explizites
  `response_feedback_recorded` an eine feedbackfähige Response-ID gebunden.
- Beide neuen Events sind projiziert und replaybar. Damit umfasst der Eventvertrag nun
  39 Typen: 23 projiziert, 16 bewusst roh; die Replayfläche umfasst 12 Tabellen.

Offen bleiben der löschbare Memory-Vault, die Migration der übrigen String-Handler, ein
vollständiger Diskursplan, ein Neustart-fester löschbarer Telegram-Randindex und jede
automatische Strategiegewichtung aus Feedback. Auch eine Edge-Outbox für den seltenen
Fehler nach Zustellung, aber vor Outcome-Persistenz fehlt. Der technische und
datenschutzbezogene Vertrag steht im
[H1-Response-Loop-Report](2026-07-13-h1-response-loop.md).
