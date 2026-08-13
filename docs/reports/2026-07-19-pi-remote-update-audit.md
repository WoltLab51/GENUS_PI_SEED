# Pi-Betriebszustand und manueller Updatevertrag

> **Erhoben:** 2026-07-19, Europe/Berlin
>
> **Status:** datierter Report
>
> **Quellen:** Repository-Skripte und -Doku plus ausschließlich lesende SSH-Abfragen an
> `ronny@pi`. Keine Systemkonfiguration wurde dabei verändert.

## Realer Ist-Zustand

Der Pi meldet Hostname `Pi`. Der produktive Checkout liegt unter
`/home/ronny/GENUS_PI_SEED`, verwendet Branch `main` und war bei der Prüfung sauber. `HEAD` und
`origin/main` zeigten beide auf `1a73db0db72ebf57f1611b42b97a3e7bef9ec404`; die installierte
GENUS-Version war `1.17.0`. Lokale Änderungen auf dem Pi sind kein vorgesehener Betriebsweg:
`pi_deploy.sh` verweigert einen Dirty Tree und einen anderen als den expliziten Deploy-Branch.

Der Checkout enthält Quellcode, `deploy/` und die virtuelle Umgebung
`/home/ronny/GENUS_PI_SEED/.venv`. Persistente oder private Laufzeitdaten liegen außerhalb:

| Bereich | Tatsächlicher Pfad |
| --- | --- |
| Ledger mit WAL/SHM | `/home/ronny/.genus/genus.sqlite3*` |
| Marker, Secrets und Laufzeitzustand | `/home/ronny/.genus/` |
| Cron-Logs | `/home/ronny/.genus/logs/` |
| Offline-Anker | `/home/ronny/.genus/anchors/` |
| H0.1-Betriebsprofil | `/home/ronny/.genus/betriebsprofil/` |
| verifizierte Zweitmedium-Backups | `/home/ronny/genus-sd-backup/` |
| optionaler Status-Checkout | `/home/ronny/GENUS_PI_STATUS/` |

Das Ledger war rund 505 MiB groß. Im Zweitmedium lagen fünf tägliche Backups vom 15. bis
19. Juli; das jüngste war vom 19. Juli 03:07. `backup_ledger_to_sd.sh` benutzt die SQLite-
Backup-API, verlangt ein anderes Blockgerät, prüft Integrität und Seal und rotiert erst danach.

## Start- und Dauerbetriebsmodell

Es gibt keinen einzelnen allumfassenden `genus.service`. Der Betrieb besteht aus Cron plus drei
systemd-Komponenten:

| Komponente | Zustand bei Prüfung | Ausführung |
| --- | --- | --- |
| `genus-learner.service` | enabled, active | Benutzer `ronny`, `deploy/pi_learn.sh` aus dem Checkout |
| `genus-telegram-bot.service` | enabled, active | Benutzer `ronny`, `.venv/bin/python deploy/telegram_bot.py` |
| `genus-network-watchdog.timer` | enabled, active | alle fünf Minuten |
| `genus-network-watchdog.service` | static, oneshot | root-eigene Kopie `/usr/local/libexec/genus/pi_network_watchdog.sh` |

Die Unit-Dateien liegen unter `/etc/systemd/system/`. Änderungen an Installer oder Watchdog im
Checkout ersetzen die root-eigene Kopie **nicht**; dazu muss der jeweilige Installer bewusst
erneut ausgeführt werden.

Der markierte Benutzer-Cronblock führt Beobachtung, State-Refresh, Clock, Wetter, News,
Gedanken/Hand, Besinnung und Profilchecks aus. Nachts laufen um 03:07 Backup, 03:17 Experience,
03:27 Doctor, 03:37 Status-Publish, 03:47 Repo-Beobachtung und 03:57 Konsolidierung. Das ist
Dauerbetrieb, aber **kein** automatisches Software-Update.

`pi_deploy.sh` besitzt bereits Dirty-Tree-, Branch- und Fast-Forward-Gates sowie Tests,
Integritäts-, Seal-, Replay-, Doctor- und Pause-Prüfungen. Vor diesem Auftrag fehlten dort jedoch
ein zwingendes Vorab-Backup, bedarfsabhängige Dependency-Installation und ein automatischer
Code-Rollback. Der neue Wrapper ändert den bestehenden Deploypfad nicht.

## Unantastbare Daten beim Code-Update

Ein Update darf niemals den Inhalt von `/home/ronny/.genus/`,
`/home/ronny/genus-sd-backup/`, `/home/ronny/GENUS_PI_STATUS/`, die systemd-Units unter `/etc`
oder die root-eigenen Watchdog-Dateien unter `/usr/local/libexec/genus/` durch Checkout-Dateien
ersetzen. Dazu gehören insbesondere Ledger/WAL/SHM, Core-ID, Token und `.env`-Dateien,
Opt-in-Marker, Chat-/Lernzustand, Logs, Anker und Backups. Der Safe-Update-Rollback bewegt nur den
Git-Branch mit `git reset --keep` auf den vorherigen Commit; er restauriert oder löscht keine
Datenbank und keine Konfiguration.

## Neuer manueller Ablauf

Vorschau, ohne Fetch, Backup oder Arbeitsbaumänderung:

```bash
cd "$HOME/GENUS_PI_SEED"
./deploy/pi_safe_update.sh --dry-run
```

Bewusster Updatebefehl:

```bash
cd "$HOME/GENUS_PI_SEED"
./deploy/pi_safe_update.sh
```

Der Wrapper prüft Dirty State und `main`, merkt den Commit, verlangt ein neues verifiziertes
Ledger-Backup auf dem konfigurierten Zweitmedium und legt daneben eine private Kopie der
relevanten Marker/Secrets ab. Erst dann pausiert er autonome Aktivität, fetched ausschließlich
`origin/main`, akzeptiert nur einen Fast-Forward und installiert Abhängigkeiten nur bei Änderungen
an `pyproject.toml` oder `requirements.txt`. Die hermetischen Tests laufen vor jedem Neustart.
Danach werden nur zuvor aktive langlebige GENUS-Units neu gestartet und Doctor, Integrität, Seal
und Unit-Zustand geprüft.

Jeder Fehler nach dem Fast-Forward löst `git reset --keep <alter-commit>` aus. Geänderte
Abhängigkeiten werden für den alten Commit erneut installiert, die alten Dienste neu gestartet
und erneut geprüft. Schlägt auch das fehl, endet das Skript laut mit Exit 72 und verlangt manuelle
Diagnose. Es verwendet kein `reset --hard`, löscht keine Daten und führt weder Replay noch Saaten
oder Migrationen aus.

Statusbefehl für eine schmale Handy-Sitzung:

```bash
cd "$HOME/GENUS_PI_SEED"
./deploy/genus_status.sh
```

## Noch direkt am Pi vor der Reise prüfen

1. Tailscale nach [`docs/operations/REMOTE_ACCESS.md`](../operations/REMOTE_ACCESS.md) installieren und den Mobilfunktest
   einschließlich Rebootprobe durchführen.
2. `./deploy/genus_status.sh` ausführen und aktuelle Journalfehler bewerten. Die Abfrage fand alte
   Watchdog-Fehler vom 12. Juli; der Timer und seine letzten Ticks waren am 19. Juli aktiv, aber die
   historische Ursache sollte vor der Abreise noch kurz bestätigt werden.
3. Prüfen, dass `sudo systemctl restart genus-learner.service genus-telegram-bot.service` im
   geplanten Fernwartungslogin bewusst möglich ist. Das Update verlangt bei Bedarf das Passwort;
   es richtet keine pauschale passwordless-sudo-Regel ein.
4. Nach Merge dieses PRs einmal `--dry-run` ausführen. Einen echten Update-/Rollbacktest nur in
   einem Wartungsfenster und mit lokalem Rückfallzugang durchführen.
5. Dateirechte prüfen: Ledger und `core_id` waren bei der Abfrage gruppen-/weltlesbarer als die
   Token-Dateien. Dieser PR ändert Rechte nicht automatisch; eine bewusste Härtung ist ein
   separates, vor Ort zu prüfendes Arbeitspaket.
