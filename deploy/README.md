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
| konservativ mit Backup und Rollback aktualisieren | [Manuelles Safe-Update](#manuelles-safe-update) |
| die A0.3c-Runtime vorbereiten und prüfen | [A0.3c-Runtime und Live-Readiness](#a03c-runtime-und-live-readiness) |
| vom Handy diagnostizieren | [Kompakter Status](#kompakter-status) |
| privaten Fernzugriff einrichten | [Tailscale-Runbook](../docs/operations/REMOTE_ACCESS.md) |
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

## Manuelles Safe-Update

Für die Fernwartung ist der konservative Wrapper der bevorzugte Einstieg. Er ergänzt den
historischen Deployweg um ein zwingendes verifiziertes Zweitmedium-Backup, eine private
Konfigurationskopie, bedarfsabhängige Dependency-Installation und Code-Rollback:

```bash
cd "$HOME/GENUS_PI_SEED"
./deploy/pi_safe_update.sh --dry-run
./deploy/pi_safe_update.sh
```

Der Dry-Run führt weder `git fetch` noch Backup oder Neustart aus. Der echte Lauf akzeptiert nur
den sauberen Branch `main` und einen Fast-Forward von `origin/main`. Tests laufen vor dem Neustart;
ein roter Test oder Healthcheck stellt den vorherigen Commit mit `git reset --keep` wieder her.
Ledger und Konfiguration werden beim Rollback weder ersetzt noch gelöscht. Vollständiger Vertrag
und Live-Befund: [Pi-Remote-Update-Audit](../docs/reports/2026-07-19-pi-remote-update-audit.md).

## A0.3c-Runtime und Live-Readiness

A0.3c trennt die **Runtime-Bereitstellung** von ihrer **Aktivierung** und beide
von einem späteren A0.3b-Live-Cutover. Das Verfahren darf weder Shadow-Tabellen
in der Produktdatenbank erzeugen noch Produktreader oder -writer umschalten.
Auch eine vollständig grüne Readiness-Serie ist deshalb noch kein Live-Go.

Der Runtime-Kandidat ist vollständig gepinnt:

| Bestandteil | Gebundener Wert |
| --- | --- |
| CPython | `3.13.15`, Archiv `Python-3.13.15.tar.xz` |
| CPython SHA-256 | `1e66a7945a48390ee4c2a4268a0e4185884059a13c4aab6d148aa208deea4a76` |
| SQLite | `3.53.4`, Archiv `sqlite-autoconf-3530400.tar.gz` |
| SQLite SHA3-256 | `454e45f61c6bd75b7420e7190732dea03ce6639c63ada47bbc592f67fc340338` |
| SQLite Source ID | `2026-07-24 19:02:57 bf7c7f30031888f4e796e429ab3978879485813aaca6f641c7b33e4e09459bcc` |
| installierte Runtime | `/opt/genus/runtime/cpython-3.13.15-sqlite-3.53.4` |

[`pi_a0_3c_runtime.sh`](pi_a0_3c_runtime.sh) prüft nicht die Version des
`sqlite3`-CLI, sondern `sys.executable`, `sqlite3.sqlite_version` und
`sqlite3.sqlite_version_info` im tatsächlich gestarteten Python. Das normale
Gate bleibt fail-closed unter SQLite `3.51.3`; dieser Kandidat muss exakt
`3.53.4` und die gebundene Source ID melden.
Der Operator bleibt der normale Pi-Login; nur die Installation in den
root-eigenen `/opt/genus/runtime`-Prefix überschreitet eng die `sudo`-Grenze.
Runtime-State und beide Venvs bleiben Eigentum des unprivilegierten Logins.

### Runtime-Sets und beide Venvs

Jeder Stage-Lauf bindet Runtime-Pins und aufgelöste Requirements in eine
deterministische Manifest-ID. Die ID wird vom Skript berechnet und wird nicht
von Hand erfunden. Ein Set liegt unter
`/home/ronny/.genus/runtime-a0.3c/sets/<manifest>/` und enthält getrennt:

- `core`: das produktive GENUS-Venv;
- `embed`: das Embedder-Venv.

Genau ein atomar ausgetauschter Symlink
`/home/ronny/.genus/runtime-a0.3c/active` wählt beide Venvs gemeinsam aus. Die
vorhandenen Aufrufpfade bleiben kompatibel: Die realen Pointer-Verzeichnisse
`/home/ronny/GENUS_PI_SEED/.venv` und `/home/ronny/.genus/embed-venv` besitzen
je einen `current`-Link auf `.../active/core` beziehungsweise
`.../active/embed`; `bin`, `lib`, `include` und `pyvenv.cfg` verweisen von dort
auf das aktive Venv. Das beim ersten Stage vorgefundene Venv-Paar wird als
Legacy-Set gebunden, damit ein Runtime-Rollback keinen Code- oder
Ledger-Rollback benötigt.

### Stufe 1: stage, Gates und Readiness-Manifest

Auf dem exakt sauberen Pi-Checkout zuerst nur bereitstellen und prüfen. `stage`
ist bewusst **zweiphasig**: Der erste Aufruf baut die gepinnte Runtime und lädt
alle Artefakte, hält dann aber an, *bevor* fremder Build-Code läuft, und druckt
die Supply-Versiegelung. Erst ein zweiter Aufruf mit exakt dieser Versiegelung
autorisiert den Wheel-Bau.

```bash
cd /home/ronny/GENUS_PI_SEED
EXPECTED_COMMIT="$(git rev-parse HEAD)"
./deploy/pi_a0_3c_runtime.sh status

# Phase 1 baut Runtime und Artefakte und endet planmäßig mit Status 78 sowie
# der Zeile "[A0.3c] SUPPLY_SEAL=<64 Hexzeichen>" auf der Fehlerausgabe.
./deploy/pi_a0_3c_runtime.sh stage

# Phase 2 gibt genau diese Versiegelung frei und liefert die Manifest-ID auf
# der Standardausgabe.
MANIFEST_ID="$(./deploy/pi_a0_3c_runtime.sh stage <SUPPLY_SEAL aus Phase 1>)"
./deploy/pi_a0_3c_runtime.sh status --json
./deploy/pi_a0_3c_runtime.sh verify "$MANIFEST_ID"
```

`stage` baut die gepinnte Runtime und beide versionierten Venvs und gibt auf
Standardausgabe ausschließlich die deterministisch berechnete Set-Manifest-ID
aus. Es ändert weder `active` noch das vorhandene `.venv` oder einen laufenden
Prozess. `status --json` macht Kandidat und aktives Set getrennt
maschinenlesbar. `verify [<manifest>|active|staged]` prüft Runtime, Manifest,
Venv-Ziele und Abhängigkeiten ohne Aktivierung.

Beide Phasen brauchen `sudo` — für den apt-Bootstrap am Anfang und für die
root-eigene Veröffentlichung nach `/opt` am Ende. Dazwischen liegt der lange
unprivilegierte Übersetzungslauf, in dem die sudo-Freigabe ablaufen und die
nächste Root-Stufe nach einem Passwort fragen kann. `stage` gehört deshalb in
eine interaktive Sitzung mit wachgehaltener Freigabe, etwa:

```bash
sudo -v
( while sleep 60; do sudo -n true || exit; done ) &
KEEPALIVE=$!
./deploy/pi_a0_3c_runtime.sh stage
STAGE_STATUS=$?
kill "$KEEPALIVE" 2>/dev/null || true
wait "$KEEPALIVE" 2>/dev/null || true
( exit "$STAGE_STATUS" )
```

`sudo -v` muss als eigener Vordergrundbefehl laufen; ein angehängtes `&& ... &`
würde die gesamte AND-Liste hintergründen und könnte die Passworteingabe stoppen.
Für Phase 2 erhält der `stage`-Aufruf in derselben Hülle zusätzlich die zuvor
ausgegebene Supply-Versiegelung als einziges Argument.

**Lieferkette: Wheel vor Quelle.** Der Akquirierer bevorzugt ein bereits
veröffentlichtes Wheel, sobald dessen Tags zur Zielplattform passen, und nimmt
die sdist nur als Rückfall. Das ist keine Bequemlichkeit, sondern notwendig:
Die netzlose Build-Sandbox besitzt weder `rustc` noch Zugang zu crates.io,
weshalb Rust-Erweiterungen wie `tokenizers`, `py_rust_stemmers` und `hf-xet`
dort grundsätzlich nicht aus Quelle baubar sind — ihre manylinux-Wheels sind
zugleich exakt die Artefakte, die der Pi heute schon ausführt. Die
Herkunftsbindung bleibt für Wheel und sdist identisch: fester Index, feste
Datei-Origin `files.pythonhosted.org` und der vom Index ausgewiesene SHA-256.
Akzeptiert werden nur `manylinux`-Wheels der Zielarchitektur, deren
glibc-Untergrenze das System erfüllt, sowie reine Python-Wheels; `musllinux`,
fremde Architekturen und zu junge Interpreter-Tags fallen fail-closed heraus.
Aus dem heutigen Pin-Satz bleibt genau `llama_cpp_python` ein Quellbau, dessen
Backends offline im Wheelhouse liegen und dessen `cmake`/`ninja` aus dem
apt-Bootstrap kommen.

Die drei festen Gates laufen direkt unter dem noch nicht aktiven
Kandidaten-Python. Jeder Aufruf bindet zusätzlich den lexikalisch erwarteten
Aufrufpfad; freie Testkommandos sind keine A0.3c-Gate-Evidenz:

```bash
CANDIDATE_CORE_PY="/home/ronny/.genus/runtime-a0.3c/sets/$MANIFEST_ID/core/bin/python"
READINESS_ID="$EXPECTED_COMMIT-$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_ROOT="/home/ronny/.genus/a0.3c/readiness/$READINESS_ID"
install -d -m 700 "$EVIDENCE_ROOT"
umask 077
mkdir -m 700 "$EVIDENCE_ROOT/scratch-full-suite"
mkdir -m 700 "$EVIDENCE_ROOT/scratch-a0-2-golden"
mkdir -m 700 "$EVIDENCE_ROOT/scratch-a0-2-historical-sqlite"
"$CANDIDATE_CORE_PY" -m experiments.a0_3c gate \
  --gate full_suite --candidate-commit "$EXPECTED_COMMIT" \
  --scratch-root "$EVIDENCE_ROOT/scratch-full-suite" \
  --receipt "$EVIDENCE_ROOT/full-suite.json" \
  --expected-invocation "$CANDIDATE_CORE_PY"
"$CANDIDATE_CORE_PY" -m experiments.a0_3c gate \
  --gate a0_2_golden --candidate-commit "$EXPECTED_COMMIT" \
  --scratch-root "$EVIDENCE_ROOT/scratch-a0-2-golden" \
  --receipt "$EVIDENCE_ROOT/a0-2-golden.json" \
  --expected-invocation "$CANDIDATE_CORE_PY"
"$CANDIDATE_CORE_PY" -m experiments.a0_3c gate \
  --gate a0_2_historical_sqlite --candidate-commit "$EXPECTED_COMMIT" \
  --scratch-root "$EVIDENCE_ROOT/scratch-a0-2-historical-sqlite" \
  --receipt "$EVIDENCE_ROOT/a0-2-historical-sqlite.json" \
  --expected-invocation "$CANDIDATE_CORE_PY"
```

Danach bindet derselbe Kandidatenpfad Commit, exakten Runtime-Fingerprint,
A0.3b-/A0.3c-Code und die drei grünen Gate-Receipts in das externe private
Readiness-Manifest. Die getrennte Verifikation muss vor jeder Aktivierung grün
sein:

```bash
MANIFEST_JSON="$EVIDENCE_ROOT/manifest.json"
"$CANDIDATE_CORE_PY" -m experiments.a0_3c manifest-create \
  --candidate-commit "$EXPECTED_COMMIT" \
  --full-suite-receipt "$EVIDENCE_ROOT/full-suite.json" \
  --a0-2-golden-receipt "$EVIDENCE_ROOT/a0-2-golden.json" \
  --a0-2-historical-sqlite-receipt "$EVIDENCE_ROOT/a0-2-historical-sqlite.json" \
  --receipt "$MANIFEST_JSON" \
  --expected-invocation "$CANDIDATE_CORE_PY"
"$CANDIDATE_CORE_PY" -m experiments.a0_3c manifest-verify \
  --manifest "$MANIFEST_JSON" \
  --receipt "$EVIDENCE_ROOT/manifest-verify-candidate.json" \
  --expected-invocation "$CANDIDATE_CORE_PY"
```

Alle Evidence-Ziele müssen neu und außerhalb des Checkouts liegen. Ein rotes
Gate, ein unsauberer Worktree oder ein abweichender Invocation-Pfad stoppt
geschlossen; weder einen teilweise gebauten Set-Pfad noch einen selbst
gewählten Symlink als Ersatz aktivieren.

### Stufe 2: Drei journalgebundene Pi-Kopienläufe

Die Serie ist Readiness-Evidenz und läuft deshalb **vor** jeder Aktivierung
unter genau dem Kandidatenpfad aus Stufe 1 — der Produktpfad bleibt dabei
unangetastet, und ein grüner Abschluss ist weiterhin kein Live-Go.

Das append-only Serienjournal besitzt einen eigenen frischen Root. Seine
externe Init-Kopie und alle Datenbankkopien liegen als Geschwister außerhalb;
im Journal-Root selbst erzeugt der CLI ausschließlich `series-init.json` und
das Verzeichnis `journal/`:

```bash
SERIES_PARENT="/home/ronny/.genus/a0.3c/series/$READINESS_ID"
JOURNAL_ROOT="$SERIES_PARENT/journal-root"
SERIES_INIT_COPY="$SERIES_PARENT/series-init-receipt.json"
FINAL_SERIES_RECEIPT="$SERIES_PARENT/final-series.json"
install -d -m 700 /home/ronny/.genus/a0.3c/series
mkdir -m 700 "$SERIES_PARENT"
mkdir -m 700 "$JOURNAL_ROOT"
"$CANDIDATE_CORE_PY" -m experiments.a0_3c series-init \
  --root "$JOURNAL_ROOT" \
  --manifest "$MANIFEST_JSON" \
  --receipt "$SERIES_INIT_COPY" \
  --expected-invocation "$CANDIDATE_CORE_PY"
INTERNAL_SERIES_INIT="$JOURNAL_ROOT/series-init.json"
```

Jeder `acquire`-Aufruf öffnet die Produktdatenbank read-only und legt zwei
Arbeitskopien in einem neuen privaten Root an. Core-ID und Anchor-Verzeichnis
werden begrenzt gelesen; genau ein vorhandener gültiger Anchor wird privat in
der Kopienevidenz gebunden. Die drei Acquisition-Roots sind Geschwister des
Journal-Roots, niemals dessen Kinder. In derselben dafür vorbereiteten
Maintenance-Shell:

```bash
set -Eeuo pipefail
umask 077
for SEQUENCE in 1 2 3; do
  ACQUISITION_ROOT="$(mktemp -d "$SERIES_PARENT/acquisition-$SEQUENCE.XXXXXX")"
  "$CANDIDATE_CORE_PY" -m experiments.a0_3c acquire \
    --source /home/ronny/.genus/genus.sqlite3 \
    --core-id-file /home/ronny/.genus/core_id \
    --anchor-dir /home/ronny/.genus/anchors \
    --root "$ACQUISITION_ROOT" \
    --manifest "$MANIFEST_JSON" \
    --receipt "$ACQUISITION_ROOT/acquisition.json" \
    --expected-invocation "$CANDIDATE_CORE_PY"
  "$CANDIDATE_CORE_PY" -m experiments.a0_3c run \
    --root "$ACQUISITION_ROOT" \
    --manifest "$MANIFEST_JSON" \
    --acquisition "$ACQUISITION_ROOT/acquisition.json" \
    --series-root "$JOURNAL_ROOT" \
    --series-init "$INTERNAL_SERIES_INIT" \
    --sequence "$SEQUENCE" \
    --receipt "$ACQUISITION_ROOT/run.json" \
    --expected-invocation "$CANDIDATE_CORE_PY"
done
```

Ein roter oder abgebrochener Run beendet die Maintenance-Shell. Für den neuen
Versuch bleiben Journal und alte Kopienevidenz erhalten; mit drei neuen
Acquisition-Roots wieder bei Sequenz 1 beginnen. Der Journalvertrag schließt
den alten Versuch als Reset und akzeptiert nur die jüngste, exakt konsekutive
grüne Folge 1, 2, 3. Code, Runtime, Manifest, Konfiguration und Tuning bleiben
dabei unverändert.

Das abschließende Receipt liegt ebenfalls außerhalb des Journal-Roots. Der CLI
liest ausschließlich die vollständige Journal-Kette; einzelne `--run`-Dateien
können nicht ausgewählt oder ausgelassen werden. Dieses finale Receipt ist ein
explizites Pflichtargument der späteren Runtime-Aktivierung; ein Readiness-
Manifest allein genügt nicht:

```bash
"$CANDIDATE_CORE_PY" -m experiments.a0_3c verify-series \
  --manifest "$MANIFEST_JSON" \
  --series-root "$JOURNAL_ROOT" \
  --series-init "$INTERNAL_SERIES_INIT" \
  --receipt "$FINAL_SERIES_RECEIPT" \
  --expected-invocation "$CANDIDATE_CORE_PY"
```

Jeder Lauf verwendet Mode A und Batchgröße 3072 und muss alle A0.3c-Budgets
einzeln erfüllen: höchstens 2,0 Sekunden je Schreibtransaktion und finalem
Fence, null Writer-Timeouts und keine Starvation, höchstens 256 MiB Peak RSS
und WAL, höchstens 180 Sekunden Build sowie höchstens 10 Sekunden Recovery;
außerdem 12/12 Projektionsdigests, 9/9 Sequenzzustände, unverändertes Ledger,
nur vollständig alten oder vollständig neuen Zustand und keinen Fallback.

Nach grüner Serie bleiben Shadow-/Scratch-Platz, vollständige Backup-Kopie und
Betriebsreserve eine getrennte menschliche Speicherbudgetentscheidung; der
frühere 512-MiB-Vorschlag ist nicht automatisch angenommen. A0.3c endet mit
einem gebundenen Readiness-Receipt. Shadow-Aufbau, Catch-up, Cutover und jede
Produktintegration bleiben bis zu einem weiteren ausdrücklichen **Human
Live-Go** gesperrt.

### Stufe 3: Runtime aktivieren und produktiven Prozesspfad beweisen

Erst nach den grünen Kandidaten-Gates und der verifizierten Drei-Lauf-Serie darf
genau dieses Set als **Python-/SQLite-Runtime** aktiviert werden. Commit,
externes Readiness-Manifest, finales Serien-Receipt und Set-Manifest-ID sind
vier getrennte Pflichtbindungen:

```bash
./deploy/pi_a0_3c_runtime.sh activate \
  "$EXPECTED_COMMIT" "$MANIFEST_JSON" "$FINAL_SERIES_RECEIPT" "$MANIFEST_ID"
./deploy/pi_a0_3c_runtime.sh status
./deploy/pi_a0_3c_runtime.sh verify active
```

`activate` verifiziert und pinnt zuerst den kanonischen Pfad und Rohdatei-Hash
des Readiness-Manifests. Unter dem Set-Python prüft es anschließend die
kanonische Serienablage (`final-series.json` direkt im Serien-Elternverzeichnis,
daneben `journal-root/series-init.json`) exakt gegen dieses gepinnte Manifest.
Es spielt die vollständige append-only Journal-Kette erneut ab und vergleicht
jedes deterministische Feld sowie das Digest-Inventar mit dem finalen Receipt;
nur Verifikationszeit und daraus folgender Receipt-Hash dürfen neu entstehen.
Owner, Modus, Link- und Verzeichnisgrenzen werden vor und nach dem Replay
geprüft. Vor dem durable Pending-Journal muss der während des Replays stabil
gelesene Readiness-Rohhash weiterhin exakt der ersten Pinnung entsprechen.
Damit sind drei konsekutive grüne Läufe an Commit, Readiness-Manifest,
Runtime-Identität und Kandidatenkonfiguration gebunden. Erst danach erzeugt es ein
frisches geprüftes Ledger-Backup samt Konfigurationsinventar,
pausiert und stoppt Cron, Watchdog, Learner und Bot kontrolliert und verweigert
alte Runtime- oder Datenbank-Handles. Erst dann tauscht es den gemeinsamen
`active`-Selector atomar und startet ausschließlich die zuvor aktiven Prozesse.
Core und Embedder werden nie einzeln gemischt.

Noch vor Pause, Selector-Tausch oder Start wird diese verifizierte Readiness-
und Serienbindung mit kanonischem Pfad und Rohdatei-Hash im fsync-ten
`genus-a0.3c-runtime-activation-pending-v2`-Journal persistiert. Die spätere
`genus-a0.3c-runtime-start-authorization-v3` und der Boot-Guard verlangen exakt
dieselben vier Werte. Direkt vor der Startfreigabe läuft außerdem ein zweiter
vollständiger Replay; Pending-Validator, Approval und Boot-Guard vergleichen
danach bei jedem Start den internen Init-Digest und jede gepinnte Journal-Entry
mit dem unveränderten finalen Receipt. Ein Absturz nach Selector-Tausch oder Startfreigabe, aber
vor dem Abschluss-Receipt, kann das Ziel deshalb nicht ohne dauerhafte
Serienevidenz booten; Completion und Recovery spielen die Journal-Kette erneut
ab.

Nach dem Wechsel müssen Runtime-Identität und Manifest erneut über genau den
stabilen Pfad grün sein, den die produktiven GENUS-Einstiege verwenden:

```bash
ACTIVE_CORE_PY="/home/ronny/GENUS_PI_SEED/.venv/bin/python"
ACTIVE_GENUS="/home/ronny/GENUS_PI_SEED/.venv/bin/genus"
"$ACTIVE_CORE_PY" -m experiments.a0_3c identity \
  --receipt "$EVIDENCE_ROOT/active-identity.json" \
  --expected-invocation "$ACTIVE_CORE_PY"
"$ACTIVE_CORE_PY" -m experiments.a0_3c manifest-verify \
  --manifest "$MANIFEST_JSON" \
  --receipt "$EVIDENCE_ROOT/manifest-verify-active.json" \
  --expected-invocation "$ACTIVE_CORE_PY"
```

Der Script-Postflight verlangt drei aufeinanderfolgende stabile Dienstproben,
attestiert den privaten Bot-Runtimepfad sowie den gepinnten Learner-Einstieg und
schreibt private Receipts unter
`/home/ronny/.genus/runtime-a0.3c/receipts/`. Das abschließende
`genus-a0.3c-runtime-activation-v3`-Receipt bindet insbesondere:

- das frische Backup-Receipt;
- Readiness-Manifest und dessen Kandidaten-Verifikation;
- das finale Drei-Lauf-Serien-Receipt;
- das Identitäts-Receipt der dann aktiven Runtime;
- den Dienst-Postflight und seinen Zustands-Hash;
- Commit sowie vorheriges und aktiviertes Set-Manifest mit Pfad und Hash;
- falls vorhanden das Operator-Reauthorization-Receipt.

Diese Aktivierung ändert nur Python/SQLite und beide Venv-Selectoren. Sie
aktiviert **keine** A0.3b-Shadow-Generation, keinen Catch-up und keinen Cutover.

Doctor, Integrity und Seal-Verifikation dürfen während dieses Schritts nicht
gegen die aktive WAL-Produktdatenbank laufen. Der Aktivierungslauf legt seinen
Snapshot selbst an und protokolliert dessen Pfad **nicht** im Log, sondern
ausschließlich im Backup-Receipt unter
`/home/ronny/.genus/runtime-a0.3c/receipts/backup-*.json`. Von dort wird der
Pfad gelesen; die schweren Gates laufen ausschließlich gegen diese bereits
verifizierte Kopie:

```bash
BACKUP_RECEIPT="$(ls -1t /home/ronny/.genus/runtime-a0.3c/receipts/backup-*.json | head -1)"
VERIFIED_BACKUP="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["ledger_path"])' "$BACKUP_RECEIPT")"
test -f "$VERIFIED_BACKUP" && test ! -L "$VERIFIED_BACKUP"
GENUS_DB_PATH="$VERIFIED_BACKUP" "$ACTIVE_GENUS" doctor
GENUS_DB_PATH="$VERIFIED_BACKUP" "$ACTIVE_GENUS" integrity check
GENUS_DB_PATH="$VERIFIED_BACKUP" "$ACTIVE_GENUS" ledger verify
```

Die produktive Datei `/home/ronny/.genus/genus.sqlite3` ist für diese drei
Kommandos ausdrücklich kein zulässiges Ziel. Scheitern Runtime-Aktivierung,
Prozessidentität, Dienst-Postflight oder diese Backup-Healthchecks, wird nur auf
das gebundene vorherige Runtime-Set zurückgeschaltet:

```bash
./deploy/pi_a0_3c_runtime.sh rollback "$EXPECTED_COMMIT"
./deploy/pi_a0_3c_runtime.sh status
./deploy/pi_a0_3c_runtime.sh verify active
```

Rollback verändert weder `main` noch die Produktdatenbank und führt kein
Reseal aus. Ein fehlendes oder nicht vollständig gebundenes Legacy-Set ist ein
Abbruchsignal. Ein roter späterer Kopienlauf blockiert dagegen die
Readiness-Serie, löst aber nicht automatisch einen Runtime-Rollback aus.

### Update-Lifecycle: `reauthorize`

Nach einer Aktivierung bindet der Boot-Guard jeden Dienststart an den freigegebenen
Commit und einen exakt sauberen Checkout — ein gewöhnlicher Fast-Forward auf
`main` würde die Units also beim nächsten Start aussperren. Genau dafür gibt es
`reauthorize`:

```bash
./deploy/pi_a0_3c_runtime.sh reauthorize "$ALTER_COMMIT" "$NEUER_COMMIT"
```

Der Aufruf akzeptiert ausschließlich einen sauberen Fast-Forward, dessen Diff
nur nicht live-importierbare Pfade berührt (`deploy/pi_a0_3c_runtime.sh`,
`deploy/README.md`, `docs/`, `tests/`, `experiments/`, `.github/`,
`README*`, `CONTRIBUTING.md`). Er schreibt ein Receipt und einen Token, der
**genau einen** nachfolgenden `stage`-plus-`activate`-Durchgang autorisiert;
ein `rollback` ist unter Reauthorisierung ausdrücklich gesperrt. Die
alte Boot-Freigabe bleibt dabei bewusst stale. Beim Schemawechsel wird nur ein
exakt aus dem attestierten OLD-Git-Objekt reproduzierter v2-Boot-Guard nach
vollständiger Token-/Receipt-Prüfung auf v3 migriert; die Veröffentlichung
erfolgt über eine fsync-te root-eigene Tempdatei und atomaren Rename. Der
v3-Guard lehnt die alte v2-Freigabe ab. Wer zwischen Reauthorisierung und
Aktivierung neu startet, findet die Dienste daher fail-closed statt halb
umgestellt vor.

Berührt ein Fast-Forward dagegen `genus/`, `schema.sql` oder andere produktiv
importierte Pfade, ist er kein A0.3c-Update, sondern eine Produktänderung — er
läuft dann über den normalen Deploypfad und eine erneute menschliche Freigabe.

## Kompakter Status

Für eine schmale SSH-Sitzung vom Telefon:

```bash
cd "$HOME/GENUS_PI_SEED"
./deploy/genus_status.sh
```

Die Ausgabe bündelt Version/Git, Unit-Zustände, die letzten fünf Journalfehler, CPU, RAM,
Speicher, Temperatur, Ledger und jüngstes feststellbares Backup.

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

Chat-Wortlernen ist aus Datenschutzgründen standardmäßig aus. Das bewusste Opt-in kann als
`GENUS_CHAT_WORD_LEARNING=1` für Bot **und** Learner gesetzt werden. Für
einen laufenden Headless-Pi ist der gemeinsame, widerrufbare Zustimmungsmarker einfacher:
`install -m 600 deploy/chat_word_learning.enabled ~/.genus/chat_word_learning.enabled`.
Erst dann wird der unbekannte Einzelbegriff einer ausdrücklichen Definitionsfrage an externe Lexikonquellen
übermittelt. Freier Chat, persönliche Aussagen und beiläufige Großschreibung werden nicht
eingereiht. Die Queue ist `0600`,
gemeinsam verriegelt und der Learner schreibt die Wortform nicht ins Journal. Zusätzlich hält
`~/.genus/chat_word_learning_status.json` höchstens 200 Zustände für sieben Tage. Darin stehen
nur normalisierter Begriff, `queued`/`learning`/`learned`/`failed` und Zeitstempel — kein
Chattext und keine Telegram-ID. Darum sagt der Bot beim ersten Mal „ich schlage nach“, während
der Verarbeitung „ich lerne noch“ und nach einem erfolglosen Quellenlauf ehrlich, dass er den
Begriff noch nicht sicher erschließen konnte. Die Datei kann jederzeit gelöscht werden; das
bereits erworbene, quellenbelegte Wortwissen bleibt davon unberührt im Ledger.

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

### Beaufsichtigter Coding-Worker

Der allgemeine Entwicklerloop ist **kein Dienst** und läuft nicht dauerhaft auf dem Pi. Diagnose
und ChangeSpec kommen aus `genus entwickler ...`; `deploy/entwickler_worker.py` wird je Entwurf
explizit gestartet. Er arbeitet ausschließlich in einem detached Worktree unter
`~/.genus/entwickler/worktrees`, besitzt keinen Commit-/Merge-/Push-/Deploy-Unterbefehl und
liefert am Ende ein Review-JSON für den Menschen.

Remote-Codegenerierung benötigt zusätzlich zum vorhandenen GitHub-Models-Token:

```bash
printf '%s\n' 'github-models:repository-source:draft-only' > "$HOME/.genus/coder.enabled"
chmod 600 "$HOME/.genus/coder.enabled"
export GENUS_CODER_ENABLE=1
export GENUS_CODER_MODEL='<explizit gewähltes Coding-Modell>'
```

Ohne beide Schalter wird kein Repository-Quelltext gesendet. Kritische Spezifikationen werden
unabhängig davon abgewiesen. Vollständiger Ablauf, Artefakte und Grenzen:
[`docs/design/SELF_CODING.md`](../docs/design/SELF_CODING.md).

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
