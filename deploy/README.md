# GENUS auf dem Pi betreiben

> **Status:** kanonisches Pi-Runbook
>
> **Owner:** GENUS Operations
>
> **Verified:** 2026-07-13 gegen die Skripte in `deploy/`

Dieses Runbook führt vom leeren Raspberry Pi bis zum überprüfbaren Dauerbetrieb. Der kurze
Weg ist absichtlich langweilig: `main` holen, Tests ausführen, Projektion prüfen, Ledger
versiegeln, Anker schreiben, Diagnose zeigen.

Weiterführend: [Betriebsübersicht](../docs/operations/README.md) ·
[Sicherheitsmodell](../docs/SECURITY_MODEL.md) · [aktueller Stand](../docs/NOW.md)

## Cockpit

| Ich möchte … | Einstieg |
| --- | --- |
| einen neuen Pi aufsetzen | [Sicheres First Setup](#sicheres-first-setup) |
| von Windows aus aktualisieren | [Deploy von Windows](#deploy-von-windows) |
| direkt auf dem Pi aktualisieren | [Deploy auf dem Pi](#deploy-auf-dem-pi) |
| den Dauerbetrieb aktivieren | [Cron-Rhythmus](#cron-rhythmus) |
| Dienste und Grenzen installieren | [Systemd-Dienste](#systemd-dienste) |
| Anker und Status veröffentlichen | [Status und Anker](#status-und-anker) |
| einen Fehler eingrenzen | [Diagnose](#diagnose) |
| sicher zurückgehen | [Rollback und Recovery](#rollback-und-recovery) |

## Betriebsvertrag in 60 Sekunden

- GitHub `main` ist die Code-Wahrheit. [`pi_deploy.sh`](pi_deploy.sh) akzeptiert nur einen sauberen
  Working Tree, den erwarteten Branch und Fast-Forward-Updates.
- Das produktive Ledger bleibt auf dem Pi. Es wird weder in Git noch in das Status-Repo
  kopiert.
- Ein Deploy pausiert autonome Aktivität, installiert die Entwicklungsabhängigkeiten,
  führt standardmäßig alle Tests aus, baut die Projektion neu, prüft Integrität und
  Seal-Kette, erzeugt einen Anker und beendet sich mit `genus doctor`.
- GENUS läuft als normaler Login. Nur klar begrenzte Installer verwenden `sudo`.
  Ein stiller Betrieb als `root` wird verweigert; `GENUS_ALLOW_ROOT=1` ist ausschließlich
  für eine bewusst geprüfte Sonderinstallation gedacht.
- `GENUS_CORE_ID` bezeichnet diesen einen langlebigen Kern. Nach der Cron-Installation
  bleibt die ID in `$HOME/.genus/core_id` erhalten.

## Voraussetzungen und Variablen

Empfohlen ist Raspberry Pi OS mit Python 3.11 oder neuer, SSH-Zugang und einem eigenen
unprivilegierten Login, in den Beispielen `genus@pi.local`.

```bash
sudo apt update
sudo apt install -y git python3 python3-venv cron rsync
python3 --version
git --version
```

Die produktiven Defaults der Skripte:

| Variable | Default | Zweck |
| --- | --- | --- |
| `GENUS_REPO_DIR` | Verzeichnis oberhalb von `deploy/` | Code-Checkout |
| `GENUS_DB_PATH` | `$HOME/.genus/genus.sqlite3` | produktives Ledger |
| `GENUS_ANCHOR_DIR` | `$HOME/.genus/anchors` | lokale Offline-Anker |
| `GENUS_LOG_DIR` | `$HOME/.genus/logs` | Cron-Logs |
| `GENUS_PROFILE_DIR` | `$HOME/.genus/betriebsprofil` | private H0.1-Snapshots |
| `GENUS_CORE_ID` | leer bzw. gespeicherte Core-ID | stabile Identität des Kerns |
| `GENUS_DEPLOY_BRANCH` | `main` | freigegebener Deploy-Branch |
| `GENUS_STATUS_REPO_DIR` | `$HOME/GENUS_PI_STATUS` | lokaler Status-Checkout |
| `GENUS_STATUS_REPO_URL` | `git@github-genus-pi-status:WoltLab51/GENUS_PI_STATUS.git` | Status-Remote |
| `GENUS_SD_BACKUP` | `$HOME/genus-sd-backup` | Backup-Ziel auf einem zweiten Gerät |
| `GENUS_BACKUP_KEEP` | `5` | Anzahl geprüfter Backups |
| `PYTHON_BIN` | `python3` | Python zum Erzeugen der virtuellen Umgebung |

Für eine Shell-Sitzung sind diese Kürzel praktisch:

```bash
export GENUS_REPO_DIR="$HOME/GENUS_PI_SEED"
export GENUS_DB_PATH="$HOME/.genus/genus.sqlite3"
export GENUS_CORE_ID="genus-pi-01"
cd "$GENUS_REPO_DIR"
```

Die Core-ID sollte stabil, eindeutig und frei von Personenbezug sein. Zulässig sind
Buchstaben, Ziffern sowie `. _ : -` bei maximal 128 Zeichen.

## Sicheres First Setup

Auf dem Pi als normaler GENUS-Login:

```bash
git clone https://github.com/WoltLab51/GENUS_PI_SEED.git "$HOME/GENUS_PI_SEED"
cd "$HOME/GENUS_PI_SEED"
GENUS_CORE_ID="genus-pi-01" ./deploy/pi_deploy.sh
GENUS_CORE_ID="genus-pi-01" ./deploy/pi_install_cron.sh
```

Danach die drei grünen Lampen prüfen:

```bash
GENUS_DB_PATH="$HOME/.genus/genus.sqlite3" .venv/bin/genus doctor
GENUS_DB_PATH="$HOME/.genus/genus.sqlite3" .venv/bin/genus ledger verify
crontab -l | sed -n '/BEGIN GENUS_PI_SEED/,/END GENUS_PI_SEED/p'
```

Optional folgen erst danach Netzwerk-Watchdog, Learner, Telegram und Status-Publishing.
So bleibt jede zusätzliche Membran einzeln prüfbar.

## Deploy von Windows

Im Repository auf der Windows-Workstation, nicht in einer SSH-Sitzung:

```powershell
.\deploy\deploy_to_pi.ps1 `
  -HostName genus@pi.local `
  -CoreId genus-pi-01 `
  -InstallCron
```

Bei gesperrter PowerShell-Ausführungsrichtlinie nutzt der `.cmd`-Starter den Bypass nur
für diesen einen Aufruf:

```powershell
.\deploy\deploy_to_pi.cmd -HostName genus@pi.local -CoreId genus-pi-01 -InstallCron
```

Nützliche Schalter:

| Parameter | Wirkung |
| --- | --- |
| `-RepoDir`, `-DbPath`, `-AnchorDir` | Pi-Pfade explizit setzen |
| `-Branch` | Deploy-Branch setzen; Default `main` |
| `-InstallCron` | den markierten Cron-Block danach neu installieren |
| `-EnableStatusPublish` | zusammen mit `-InstallCron`: Publishing dauerhaft aktivieren und sofort ausführen |
| `-SkipTests` | Tests überspringen; nur für eine bewusst diagnostische Ausnahme |
| `-SkipAnchor` | Ankerexport überspringen; Ausnahme sichtbar begründen |

Ein vollständiger Pfad-Override sieht so aus:

```powershell
.\deploy\deploy_to_pi.ps1 `
  -HostName genus@pi.local `
  -RepoDir /home/genus/GENUS_PI_SEED `
  -DbPath /home/genus/.genus/genus.sqlite3 `
  -AnchorDir /home/genus/.genus/anchors `
  -StatusRepoDir /home/genus/GENUS_PI_STATUS `
  -CoreId genus-pi-01
```

## Deploy auf dem Pi

Direkt in der SSH-Sitzung:

```bash
cd "$HOME/GENUS_PI_SEED"
GENUS_CORE_ID="genus-pi-01" ./deploy/pi_deploy.sh
```

Oder von einer beliebigen Shell aus:

```bash
ssh genus@pi.local 'cd "$HOME/GENUS_PI_SEED" && GENUS_CORE_ID=genus-pi-01 ./deploy/pi_deploy.sh'
```

Gezielte Umgebungsoptionen sind `GENUS_DEPLOY_BRANCH`, `GENUS_DEPLOY_SKIP_TESTS=1`,
`GENUS_DEPLOY_SKIP_ANCHOR=1` sowie `PYTHON_BIN`. Ein normaler Deploy sollte keine Skip-Option
benötigen. Ein Fehler lässt den Pause-Schalter durch einen `trap` wieder frei; die Fehlermeldung
bleibt trotzdem bindend.

Nach den hermetischen Tests gleicht der Deploy die deklarativen Graph-Saaten automatisch ab:
`seed_verstehen.sh` ergänzt fehlende Rasterkanten, `gleiche_ziele_ab.sh` reconciliert Ziel- und
Fähigkeitsstatus. Beides geschieht unter der Pause und vor Replay/Integrität. Ein neues
Rasterblatt kann dadurch nicht mehr im Code vorhanden, im lebenden Deuter aber unerreichbar sein.
Der Replay-Vergleich hält außerdem vom Vorher-Snapshot bis zum Nachher-Snapshot ein einziges
SQLite-Schreibfenster; konkurrierende Schreiber können dadurch keinen falschen Driftbefund mehr
erzeugen.

## Cron-Rhythmus

[`pi_install_cron.sh`](pi_install_cron.sh) ersetzt ausschließlich den Block zwischen `BEGIN GENUS_PI_SEED` und
`END GENUS_PI_SEED`; fremde Cron-Einträge bleiben erhalten.

```bash
cd "$HOME/GENUS_PI_SEED"
GENUS_CORE_ID="genus-pi-01" ./deploy/pi_install_cron.sh
```

Der aktuelle Takt:

| Rhythmus | Aktivität |
| --- | --- |
| alle 2–5 Minuten | Hand-Ausführung, Gedanken-Push, Sensoren und State-Refresh |
| alle 15/20 Minuten | Clock-Check und News |
| stündlich | zwei Wetterquellen; Besinnung viertelstündlich versetzt; stiller Profil-Fälligkeitscheck um `:23` |
| morgens | Morgen-Push zwischen 05:00 und 09:59 |
| nachts | Backup 03:07, Experience 03:17, Doctor 03:27, optional Status 03:37, Repo 03:47, Konsolidierung 03:57 |

Das Backup zählt nur, wenn `GENUS_SD_BACKUP` auf einem **anderen Gerät** als das Ledger
liegt. Der Default ist ein Pfad, kein Beweis für ein zweites Medium; bei gleicher Geräte-ID
bricht [`backup_ledger_to_sd.sh`](backup_ledger_to_sd.sh) ehrlich ab. Standardmäßig bleiben fünf geprüfte Backups.

```bash
tail -f "$HOME/.genus/logs/cron.log"
tail -f "$HOME/.genus/logs/doctor.log"
tail -f "$HOME/.genus/logs/status.log"
```

### 24/48/72-Stunden-Betriebsprofil

Der Cron-Eintrag startet **keine** Messreihe. Er prüft nur stündlich, ob eine bewusst gestartete
Reihe fällig ist. Die Baseline wird einmal von Hand ausgelöst:

```bash
cd "$HOME/GENUS_PI_SEED"
export GENUS_DB_PATH="$HOME/.genus/genus.sqlite3"
.venv/bin/genus betriebsprofil capture --start
.venv/bin/genus betriebsprofil status
```

Danach schreibt GENUS genau `baseline.json`, `h24.json`, `h48.json`, `h72.json` und
`manifest.json` nach `$HOME/.genus/betriebsprofil`. Das Manifest enthält für jeden Snapshot
einen SHA-256-Prüfwert und gleicht dessen feste Metadaten ab. Das erkennt lokalen Dateischaden,
ist aber kein externer Manipulationsanker. Die drei Tagesintervalle sind exakt
`(voriger Head, neuer Head]`; gleiche Zeitstempel verlieren deshalb kein Ereignis. Jede
Folgemessung prüft außerdem die DB-Datei und einen vollständigen Hash aller Zeilenfelder im
bisherigen Ledger-Präfix – auch bei aktivem Seal. Ein Restore, Ledger-Tausch oder eine Änderung
an Payload, Zeitstempel oder Seal beendet die Reihe deshalb geschlossen.

Eine planmäßige Aufnahme darf höchstens zwei Stunden verspätet sein. Das deckt den stündlichen
Cron-Takt ab. Wird ein Punkt später erreicht, markiert GENUS die Reihe als `aborted`, erzeugt
keinen irreführenden Tages-Snapshot und meldet den einmaligen Abbruch mit Fehlerstatus; danach
bleibt der fällige Check still. Für einen Neustart den abgebrochenen
Ordner archivieren und bewusst einen neuen `GENUS_PROFILE_DIR` wählen. Nach `h72` bleibt der
Cron-Aufruf ebenfalls dauerhaft still.

Das Profil öffnet nur ein bestehendes Ledger mit SQLite `mode=ro`. Es speichert keine Payloads,
Entitäten, freien Quellenwerte oder Dateipfade, sondern ausschließlich kontrollierte Aggregate.
Hauptdatei, belegte Seiten und die flüchtige WAL-Dateiallokation bleiben getrennt; keine dieser
Punktmessungen ist für sich eine tägliche Wachstumsrate. Verzeichnis und Dateien werden auf dem
POSIX-Ziel Pi trotz Umask auf `0700` beziehungsweise `0600` gesetzt, als reguläre Dateien ohne
Symlink-Folge geprüft und durch einen exklusiven Lock geschützt. Unter Windows arbeitet der Lock
ebenfalls exklusiv; die belastbare Unix-Rechtegarantie gilt jedoch für den Pi. Der Cron-Wrapper
läuft mit niedriger Priorität und einer harten Laufzeitgrenze von 180 Sekunden. Normale No-ops
bleiben vollständig still; Capture-Meldungen und Fehler gehen mit höchstens 4096 Byte pro Lauf
unter dem Tag `genus-betriebsprofil` an Syslog beziehungsweise das Journal.
Ein gelöschter oder durch einen Symlink ersetzter Profilordner wird ebenfalls als Fehler gemeldet.

Eine bestehende Reihe wird nie überschrieben. Für eine spätere neue Messung den abgeschlossenen
Ordner zuerst bewusst und geschützt archivieren und einen neuen `GENUS_PROFILE_DIR` wählen.

Status-Publishing ist nach einmaligem `GENUS_ENABLE_STATUS_PUBLISH=1` sticky. Abschalten:

```bash
rm "$HOME/.genus/status_publish.enabled"
GENUS_CORE_ID="genus-pi-01" ./deploy/pi_install_cron.sh
```

## Systemd-Dienste

### Netzwerk-Watchdog und Root-Grenze

Der Watchdog prüft zwei Minuten nach Timer-Aktivierung und danach alle fünf Minuten das Default-
Gateway. Fehler erzeugen Ledger-Evidenz. Zuerst wird der aktive Netzwerkdienst neu gestartet;
ein Reboot kommt erst nach dem geklammerten, selbst kalibrierten Schwellenwert und dem
root-eigenen Stunden-Cooldown infrage. Während `genus pause` endet der Tick vor Supervision,
Netzwerkbeobachtung und Recovery; insbesondere schreibt er dann keine Operations-Evidenz in ein
parallel geprüftes Ledger.

Installation vom Pi als normaler Login; das Skript fordert `sudo` nur für die Systemdateien an:

```bash
cd "$HOME/GENUS_PI_SEED"
GENUS_CORE_ID="genus-pi-01" ./deploy/pi_install_network_watchdog.sh
sudo systemctl start genus-network-watchdog.service
```

Von Windows geht es ebenso:

```powershell
.\deploy\install_pi_network_watchdog.ps1 -HostName genus@pi.local -CoreId genus-pi-01
```

Bei blockierter Skriptausführung übernimmt `install_pi_network_watchdog.cmd` dieselben Parameter.

Die privilegierte Unit führt **nicht** den beschreibbaren Checkout als `root` aus. Installer und
Watchdog werden root-owned nach `/usr/local/libexec/genus` kopiert; der Zähler liegt geschützt
unter `/var/lib/genus-network-watchdog`. Nach Änderungen an diesen Skripten den Installer erneut
ausführen: Erst das befördert geprüften Code über die Root-Grenze. Bei jedem Tick prüft der
Watchdog außerdem die installierten Learner- und Telegram-Units und repariert Vertragsdrift mit
den privilegierten, idempotenten Installer-Kopien.

```bash
systemctl list-timers genus-network-watchdog.timer
systemctl status genus-network-watchdog.timer
journalctl -u genus-network-watchdog.service -f
```

### Learner

Der Learner läuft dauerhaft mit Idle-CPU- und Idle-I/O-Priorität und weicht normaler Last aus:

```bash
cd "$HOME/GENUS_PI_SEED"
GENUS_CORE_ID="genus-pi-01" ./deploy/pi_install_learner.sh
systemctl status genus-learner.service
journalctl -u genus-learner.service -f
```

`GENUS_LEARN_DELAY` ist standardmäßig `2` Sekunden pro Wort. `genus pause` stoppt die autonome
Arbeit logisch; `sudo systemctl stop genus-learner.service` stoppt den Prozess vollständig.

### Telegram

Der sicherste Weg gibt das Bot-Token nicht als Kommandozeilenargument weiter:

```bash
cd "$HOME/GENUS_PI_SEED"
install -d -m 700 "$HOME/.genus"
umask 077
read -rsp "Telegram Bot-Token: " BOT_TOKEN; printf '\n'
printf '%s' "$BOT_TOKEN" > "$HOME/.genus/telegram_bot_token"
unset BOT_TOKEN
chmod 600 "$HOME/.genus/telegram_bot_token"
GENUS_CORE_ID="genus-pi-01" ./deploy/pi_install_telegram_bot.sh 123456789
```

Die letzte Zahl ist durch die eigene numerische Telegram-User-ID zu ersetzen. Bis persönliche
Erinnerungen echte Nutzer-Namespaces besitzen, ist genau **ein** Besitzer erlaubt und der Bot
antwortet ausschließlich in dessen Direktchat. Der Installer validiert die ID, bettet nur sie
in die root-owned Unit ein und hält das Token in der Datei mit Modus `0600`. Die Unit läuft unprivilegiert, mit
Prozess-Lock, Systemd-Sandbox und Speichergrenzen. Im Kompaktmodus bleibt die Modell-Waage aus,
der lokale Deuter wird nur bei einer ungelösten Formulierung geladen und nach 90 Sekunden Ruhe
wieder freigegeben; eine zweite Stimme bleibt standardmäßig aus. Dadurch bezahlt der Pi die
Modellkosten nur für den seltenen offenen Lesefall, nicht während des gesamten Leerlaufs.

Das Journal enthält nur Betriebsmetadaten (zum Beispiel Nachrichtenlänge und Fehlerklasse),
keinen Nachrichtentext und keine Absender-ID. `~/.genus/chat_tag.jsonl` speichert ebenfalls nur
destillierte Struktur: Zeit, Konzept-IDs, Lesarten und Warum-Folge. Die Nacht rotiert diese Datei
atomar unter demselben Lock wie der Bot-Schreiber. Historische Journale oder Legacy-Logs werden
beim Installieren und Deployen nicht automatisch gelöscht; ihre Retention ist eine bewusste
Betriebsentscheidung. Details und die noch offene physische Episodenlöschung stehen in
[`docs/design/MEMORY.md`](../docs/design/MEMORY.md).

Chat-Wortlernen ist aus Datenschutzgründen standardmäßig aus. Ein bewusstes
Das Opt-in kann als `GENUS_CHAT_WORD_LEARNING=1` für Bot **und** Learner gesetzt werden. Für
einen laufenden Headless-Pi ist der gemeinsame, widerrufbare Zustimmungsmarker einfacher:
`install -m 600 deploy/chat_word_learning.enabled ~/.genus/chat_word_learning.enabled`.
Erst dann wird der unbekannte Einzelbegriff einer ausdrücklichen Definitionsfrage an externe Lexikonquellen
übermittelt. Freier Chat, persönliche Aussagen und beiläufige Großschreibung werden nicht
eingereiht. Die Queue ist `0600`,
gemeinsam verriegelt und der Learner schreibt die Wortform nicht ins Journal.

```bash
systemctl status genus-telegram-bot.service
journalctl -u genus-telegram-bot.service -f
```

### Modell-Gateway, selektiver Remote-Deuter und synthetischer Bake-off

`model_gateway.py` ist die providerneutrale Netz-Membran für entfernte Modelle. Der Kern unter
`genus/` importiert sie nie. Der erste Adapter spricht die versionierte GitHub-Models-API mit
Python-Standardbibliothek an; ein schweres Provider-SDK wird nicht Teil des Kern-Venv-Vertrags.
Jeder Aufruf trägt eine Rolle, ein explizites Modell, eine Datenschutzklasse, Tokenobergrenze
und optional ein JSON-Schema. Zurück kommt neben dem Entwurf ein Beleg über Provider, Modell,
Request-ID, Latenz, Token und Abschlussgrund. Providertext ist nie selbst Wahrheit.

Die Vergleichswerkzeuge bleiben bewusst **kein Live-Chat**. `model_bakeoff.py` erzeugt Antworten aus
der lebenden 17-Fälle-Alltagsprobe lokal und sendet ausschließlich die Datenschutzklasse
`synthetic`. Freie Eingaben, Telegram-Verläufe, Ledger und Memory-Vault werden von diesem CLI-Pfad
nicht angenommen. GitHub Models ist im Provider zusätzlich fail-closed auf `synthetic` beschränkt.
Die bestehende Anker-, Inhalts- und Richtungsprüfung aus `stimme.py` entscheidet anschließend, ob
ein Kandidat überhaupt treu genug für eine menschliche Bewertung ist. Daneben prüft
`remote_deuter_benchmark.py` die strukturierte Absichtserkennung mit ausschließlich synthetischen
deutschen Sätzen. Beide Werkzeuge schalten keinen entfernten Anbieter in Telegram frei.

Telegram kann nach einer **persönlichen, widerrufbaren Freigabe** den gemessenen Sieger
`openai/gpt-4.1-nano` als selektiven Deuter verwenden. Der Aufruf geschieht erst nach lokalen
Ritualen und Muster-Zellen. Übertragen werden ausschließlich der statische Segmentvertrag und
der aktuelle Nachrichtentext (höchstens 1.000 Zeichen) — niemals Telegram-ID, Verlauf, Ledger,
Antworten oder frühere Korrekturbeispiele. Das Modell darf höchstens drei strukturierte Lesarten
vorschlagen; Segment-Herkunft und Wirkung prüft danach derselbe deterministische Kern wie beim
lokalen Deuter. Ein Providerfehler lädt nicht automatisch das große lokale Modell nach.

Die Freigabe ist eine private `0600`-Datei und damit ohne Root widerrufbar:

```bash
install -d -m 700 "$HOME/.genus"
umask 077
printf '%s\n' 'github-models:remote_minimal' > "$HOME/.genus/remote_deuter.enabled"
chmod 600 "$HOME/.genus/remote_deuter.enabled"
touch "$HOME/.genus/telegram_bot.neustart"
```

Widerruf: `rm "$HOME/.genus/remote_deuter.enabled"` und denselben Neustart-Flag berühren. Der
Live-Pfad ist zusätzlich auf 10 Aufrufe pro Minute, 120 pro UTC-Tag, 160 Ausgabetoken und acht
Sekunden Laufzeit begrenzt. Das Tagesbudget liegt ohne Nachrichtentext in
`~/.genus/remote_deuter_budget.json`; HTTP 429 öffnet eine fünfminütige Ausfall-Sperre. Das
Journal enthält nur Modell-, Latenz-, Token- und Segmentzahlen, niemals den Chattext.

Ein Fine-grained PAT braucht nur `models: read`. Nicht in Shell-Historie, Repo oder Unit legen:

```bash
install -d -m 700 "$HOME/.genus"
umask 077
read -rsp "GitHub Models PAT: " GITHUB_MODELS_PAT; printf '\n'
printf '%s' "$GITHUB_MODELS_PAT" > "$HOME/.genus/github_models_token"
unset GITHUB_MODELS_PAT
chmod 600 "$HOME/.genus/github_models_token"
```

Ein kleiner Vergleich bleibt unter den kostenlosen Prototyping-Limits überschaubar:

```bash
cd "$HOME/GENUS_PI_SEED"
.venv/bin/python deploy/model_bakeoff.py \
  --model openai/gpt-4.1-mini \
  --model meta/llama-4-scout-17b-16e-instruct \
  --max-cases 5 \
  --max-requests 20
```

Der Bake-off wartet standardmaessig mindestens 4,1 Sekunden zwischen zwei Provideraufrufen.
Damit bleibt auch ein laengerer Lauf unter dem freien Low-Tier-Limit von 15 Anfragen pro Minute.
`--min-request-interval` kann fuer ein strengeres Providerlimit erhoeht werden; die harte
`--max-requests`-Kostenbremse gilt davon unabhaengig weiterhin vor dem ersten Netzaufruf.

Modell-IDs sind Beispiele und müssen vor dem Lauf im GitHub-Models-Katalog geprüft werden. Das
CLI dedupliziert IDs und bricht **vor** dem ersten Netzaufruf ab, wenn Fälle × Modelle das harte
Request-Limit überschreiten. Bezahlte GitHub-Models-Nutzung bleibt in GitHub standardmäßig aus;
ein dort gesetztes Budget ist die zweite, externe Kostengrenze. `remote_minimal` ist im
GitHub-Adapter ausschließlich für den explizit freigegebenen Live-Deuter erreichbar; synthetische
Werkzeuge bleiben auf `synthetic` gepinnt.

## Clock

Falsche Zeit beschädigt die Bedeutung zeitlicher Beobachtungen. Der Cron-Installer prüft daher
alle 15 Minuten den NTP-Status und schreibt `clock.sync`-Evidenz. Nach einem Kaltstart:

```bash
timedatectl status
cd "$HOME/GENUS_PI_SEED"
GENUS_CORE_ID="genus-pi-01" ./deploy/pi_clock_check.sh
GENUS_DB_PATH="$HOME/.genus/genus.sqlite3" .venv/bin/genus operation list
```

Eine RTC-Batterie schützt den Pi 5 zusätzlich bei Stromverlust; sie ersetzt den NTP-Check nicht.

## Workstation-Sensor

[`observe_repo_from_x1.sh`](observe_repo_from_x1.sh) läuft in Git Bash auf der Workstation. Er zählt Commits und geänderte
Zeilen im Zeitfenster und überträgt nur diese Zahlen, keine Committexte, Dateinamen oder Diffs:

```bash
GENUS_PI_HOST=genus@pi.local \
GENUS_PI_REPO_DIR=/home/genus/GENUS_PI_SEED \
GENUS_PI_DB_PATH=/home/genus/.genus/genus.sqlite3 \
GENUS_REPO_WINDOW_HOURS=24 \
./deploy/observe_repo_from_x1.sh
```

Das Skript eignet sich für die Windows-Aufgabenplanung. Fällt ein Lauf aus, entsteht keine
Messung — „nicht gemessen“ wird nicht als „ruhig“ erfunden. Cron ergänzt täglich die Pi-seitige
Sicht auf den veröffentlichten Branch über `observe_repo_on_pi.sh`.

## Status und Anker

Jeder reguläre Deploy erzeugt einen lokalen Offline-Anker in `$HOME/.genus/anchors`. Prüfen:

```bash
GENUS_DB_PATH="$HOME/.genus/genus.sqlite3" \
  "$HOME/GENUS_PI_SEED/.venv/bin/genus" ledger anchor verify \
  "$HOME/.genus/anchors/<ankerdatei>.json"
```

Für ein externes Status-Repo zuerst auf Windows einen eigenen Pi-Deploy-Key erzeugen:

```powershell
.\deploy\setup_pi_status_key.ps1 `
  -HostName genus@pi.local `
  -CoreId genus-pi-01 `
  -Repository "<owner>/<status-repo>"
```

Den ausgegebenen Public Key im genannten Repository als Deploy Key **mit Schreibrecht**
eintragen. Danach mit der passenden Remote-URL veröffentlichen:

```powershell
.\deploy\publish_pi_status.ps1 `
  -HostName genus@pi.local `
  -CoreId genus-pi-01 `
  -StatusRepoUrl "git@github-genus-pi-status:<owner>/<status-repo>.git"
```

Pi-seitig entspricht das:

```bash
cd "$HOME/GENUS_PI_SEED"
GENUS_CORE_ID="genus-pi-01" \
GENUS_STATUS_REPO_URL="git@github-genus-pi-status:<owner>/<status-repo>.git" \
./deploy/pi_publish_status.sh
```

Für eingeschränkte PowerShell-Umgebungen stehen außerdem `setup_pi_status_key.cmd` und
`publish_pi_status.cmd` mit denselben Parametern bereit.

Veröffentlicht werden Anker sowie aggregierte Dateien unter `status/<core-id>/`: `latest.json`,
`history.jsonl` und `STATUS.md`. Lokale Pfade, Rohereignisse, Doctor-Ausgabe und das SQLite-
Ledger bleiben privat. Der lokale Status-Checkout ist generierter Austauschoutput und wird vor
dem Publish auf `origin/main` synchronisiert.

## Diagnose

Der kleine Gesundheitsblock, der fast immer zuerst hilft:

```bash
cd "$HOME/GENUS_PI_SEED"
export GENUS_DB_PATH="$HOME/.genus/genus.sqlite3"
.venv/bin/genus doctor
.venv/bin/genus integrity check
.venv/bin/genus ledger verify
.venv/bin/genus ledger head
.venv/bin/genus paused
.venv/bin/genus betriebsprofil status
git status --short
git branch --show-current
```

Takt und Dienste:

```bash
crontab -l | sed -n '/BEGIN GENUS_PI_SEED/,/END GENUS_PI_SEED/p'
tail -n 100 "$HOME/.genus/logs/cron.log"
tail -n 100 "$HOME/.genus/logs/doctor.log"
journalctl -t genus-betriebsprofil -n 20 --no-pager
# falls das System Syslog-Dateien statt Journal-Tags nutzt:
grep 'genus-betriebsprofil' /var/log/syslog | tail -n 20
systemctl --no-pager --full status genus-learner.service genus-telegram-bot.service
systemctl list-timers --all genus-network-watchdog.timer
journalctl -u genus-network-watchdog.service -n 100 --no-pager
```

Typische Befunde:

| Symptom | Erstes Vorgehen |
| --- | --- |
| Deploy meldet `working tree is dirty` | `git status --short` lesen; Pi-Änderung bewusst sichern oder entfernen, nie blind überschreiben |
| falscher Branch / kein Fast-Forward | Abweichung im Quell-Repo klären; danach auf `main` normal deployen |
| Anker wird übersprungen | `GENUS_CORE_ID` setzen oder `$HOME/.genus/core_id` prüfen |
| Cron-Job fehlt | `pi_install_cron.sh` erneut ausführen; nur der markierte Block wird ersetzt |
| Dienst nutzt alte Unit-Eigenschaften | den zugehörigen Installer erneut ausführen; er startet die Unit neu |
| Seal- oder Integritätsfehler | pausieren, Evidenz erhalten, Backup prüfen; **nicht** spontan `ledger reseal` ausführen |

## Rollback und Recovery

### Code zurückrollen

Der normale Rollback ist ein neuer, nachvollziehbarer Revert auf `main`: auf der Workstation
den fehlerhaften Commit mit `git revert <commit>` rückgängig machen, prüfen und pushen; danach
den normalen Deploy erneut ausführen. So bleiben GitHub-Wahrheit, Pi und Auditspur deckungsgleich.
Ein lokales `reset --hard` oder ein dauerhaft detached Pi-Checkout ist kein Betriebsweg.

### Ledger aus geprüftem Backup wiederherstellen

Nur bei einem echten Datenproblem — niemals als Code-Rollback. Das Backup muss von
[`backup_ledger_to_sd.sh`](backup_ledger_to_sd.sh) stammen, auf einem zweiten Medium liegen
und mit der eingesetzten Codeversion prüfbar sein. Plane ein Wartungsfenster: Zusätzlich zu
den GENUS-Units wird `cron.service` kurz systemweit gestoppt, weil nicht jeder historische
Cron-Einstieg den Pause-Schalter selbst prüft. Notiere vorher, welche optionalen Units aktiv
waren; nur diese werden am Ende wieder gestartet. Jede schreibende Unit muss vor dem
Verschieben `inactive` melden.

```bash
cd "$HOME/GENUS_PI_SEED"
export GENUS_DB_PATH="$HOME/.genus/genus.sqlite3"
BACKUP="/pfad/zum/zweiten-medium/genus-YYYYMMDD-HHMMSS.sqlite3"
ANCHOR="/pfad/zum/zweiten-medium/anchors/<passender-nicht-juengerer-anchor>.json"

GENUS_DB_PATH="$BACKUP" .venv/bin/genus integrity check
GENUS_DB_PATH="$BACKUP" .venv/bin/genus ledger verify
GENUS_DB_PATH="$BACKUP" .venv/bin/genus ledger anchor verify "$ANCHOR"
.venv/bin/genus pause --reason "ledger recovery"
sudo systemctl stop cron.service
sudo systemctl stop genus-network-watchdog.timer genus-network-watchdog.service
sudo systemctl stop genus-learner.service genus-telegram-bot.service
sudo systemctl stop genus-telegram-bot-fallback.service
systemctl is-active cron.service genus-network-watchdog.timer genus-network-watchdog.service \
  genus-learner.service genus-telegram-bot.service genus-telegram-bot-fallback.service

STAMP="$(date -u +%Y%m%d-%H%M%S)"
mv -- "$GENUS_DB_PATH" "$GENUS_DB_PATH.before-recovery-$STAMP"
[ ! -e "$GENUS_DB_PATH-wal" ] || mv -- "$GENUS_DB_PATH-wal" "$GENUS_DB_PATH-wal.before-recovery-$STAMP"
[ ! -e "$GENUS_DB_PATH-shm" ] || mv -- "$GENUS_DB_PATH-shm" "$GENUS_DB_PATH-shm.before-recovery-$STAMP"
install -m 600 "$BACKUP" "$GENUS_DB_PATH"

.venv/bin/genus replay
.venv/bin/genus integrity check
.venv/bin/genus ledger verify
.venv/bin/genus doctor
```

Der `is-active`-Block muss für alle installierten Schreibpfade `inactive` melden. Ein fehlender
passender Anchor ist kein Grund, einen jüngeren Anchor zu verwenden: Dann bleibt die
Wiederherstellung ein Incident mit schwächerem Herkunftsnachweis und wird entsprechend
dokumentiert. `replay` darf nicht ignoriert oder zweimal „grün gelaufen“ werden; eine
Projektionsabweichung im geprüften Backup ist ein Abbruchsignal.

Erst wenn alle Prüfungen grün sind:

```bash
.venv/bin/genus resume
sudo systemctl start genus-network-watchdog.timer
sudo systemctl start genus-learner.service genus-telegram-bot.service
sudo systemctl start cron.service
```

Die optionalen Learner-/Telegram-Zeilen gelten nur für Units, die vor der Wartung aktiv waren.
Bei einem fehlgeschlagenen Check bleiben GENUS pausiert und `cron.service` gestoppt. Das vorherige Ledger und seine
WAL/SHM-Dateien bleiben mit Zeitstempel erhalten; nichts resealen und keine Datei löschen,
bevor die Ursache verstanden ist.
