# GENUS · Beaufsichtigtes Selbst-Codieren

> **Status:** active design · **Owner:** ADR-0004 / Change Trust
> **Zuletzt verifiziert:** 2026-07-19

GENUS codiert sich nicht, indem ein Modell freien Zugriff auf sein Repository erhält. Er lernt
den Entwicklungsprozess als Folge kleiner, beweisbarer Zustände. Am Anfang begleitet ein Mensch
jeden Übergang; wiederkehrende Prüfungen werden zu Verträgen, nicht zu stillen Modellrechten.

## Der vollständige v1-Kreis

```text
1 Selbstkarte lesen       read-only, aus Kartografie + Git-HEAD
2 Symptom diagnostizieren Quellbelege + Import-Wirkungsraum, keine behauptete Root Cause
3 ChangeSpec erzeugen     Basiscommit + Scope + Risiko + Budget + Gates
4 Draft freigeben         menschlich, hashgebunden, nur draft_only
5 Worktree vorbereiten    detached, außerhalb des produktiven Checkouts
6 Patch entwerfen         optionaler API-Coder, nur freigegebene Dateien
7 Patch prüfen            Scope, Secrets, Kernreinheit, Zeilen-/Dateibudget
8 Gates fahren            registrierte argv-Kommandos, kein Plan-Shelltext
9 Diff prüfen             Mensch entscheidet über Änderung, Commit, Merge und Deploy
10 Wirkung zurückmelden   angenommen/abgelehnt/Regression; Rechte bleiben gleich
```

Die Kernseite liegt in [`genus/entwickler.py`](../../genus/entwickler.py). Sie startet keinen
Prozess und berührt kein Netz. Die Außenwerkbank liegt in
[`deploy/entwickler_worker.py`](../../deploy/entwickler_worker.py). Nur sie darf Git und den
optionalen Provider benutzen.

## Die Artefakte

| Artefakt | Beweist | Darf nicht |
|---|---|---|
| `genus-developer-status-v1` | Commit, Selbstkarte, vorhandene Fähigkeiten und Grenzen | Laufzeitdienste vortäuschen |
| `genus-diagnosis-v1` | rangierte Quellnähe und angrenzende Module | eine Root Cause behaupten |
| `genus-change-spec-v1` | Ziel, erlaubte Dateien, Risiko, Budget und Gates | Schreibrechte erteilen |
| `genus-change-approval-v1` | menschliches `draft_only` für exakt Spec + Commit | Commit/Merge/Deploy erlauben |
| `genus-code-generation-receipt-v1` | Provider, Modell, Token-/Zeitbeleg und Patchhash | Modelltext zu Vertrauen erklären |
| `genus-code-review-v1` | finaler Diff, automatische Gates und offene manuelle Gates | `merge_ready=true` setzen |
| `genus-change-outcome-v1` | menschlich bestätigte Wirkung | Autonomie nach Erfolg vergrößern |

## Risikostufen

| Risiko | Typischer Scope | Modell-Draft | Zusätzliche Klinken |
|---|---|---:|---|
| `low` | Dokumentation, begrenzte Daten | ja | Diff-/Scopeprüfung |
| `medium` | normale Kern- oder Membranlogik | ja | Ruff, fokussierte Tests, Kartografie |
| `high` | Telegram, Modellgateway, Hand/Control | ja, kleinster Scope | Vollsuite + Security-Review |
| `critical` | Ledger, Schema, Siegel, Governance, kritische Deploywege | **nein** | Mensch baut; Vollsuite + Security-Review |

Budgets werden mit steigendem Risiko kleiner. Ein Modell darf keine neue Datei außerhalb der
erlaubten Liste „entdecken“. Deterministisch neu erzeugte Kartografieartefakte sind getrennt vom
Modellscope ausgewiesen.

## Bedienung

### 1. Stand und Diagnose

```bash
genus entwickler stand
genus entwickler diagnose \
  "GENUS Antworten klingen unnatürlich und der Säugetier-Pfad ist falsch" \
  --output ~/.genus/entwickler/antwort-diagnose.json
```

Die Diagnose ist Such- und Wirkungsraum, kein automatischer Fehlerbeweis. Ein Mensch prüft die
Belege und begrenzt daraus den Scope.

### 2. Änderungsspezifikation und Draft-Freigabe

```bash
genus entwickler plan "Antwortplan und sprachliche Realisierung trennen" \
  --diagnose ~/.genus/entwickler/antwort-diagnose.json \
  --allow genus/antwort.py \
  --allow tests/test_antwort.py \
  --test tests/test_antwort.py \
  --output ~/.genus/entwickler/antwort-spec.json

genus entwickler genehmige ~/.genus/entwickler/antwort-spec.json \
  --reviewer ronny \
  --output ~/.genus/entwickler/antwort-approval.json
```

Diese Freigabe erlaubt nur einen isolierten Entwurf. Sie kann technisch weder Commit noch Merge,
Push oder Deploy öffnen.

### 3. Isolierter Worktree

```bash
python deploy/entwickler_worker.py prepare \
  --spec ~/.genus/entwickler/antwort-spec.json \
  --approval ~/.genus/entwickler/antwort-approval.json \
  --workspace ~/.genus/entwickler/worktrees/antwort-v1 \
  --receipt ~/.genus/entwickler/antwort-worktree.json
```

Ein bestehender Zielordner wird nicht überschrieben. Entfernen oder Wiederverwenden bleibt eine
menschliche Dateisystementscheidung.

### 4. Optionaler API-Coder

Repository-Quelltext hat eine eigene Datenschutzklasse. Tokenfreigabe allein reicht nicht:

```bash
printf '%s\n' 'github-models:repository-source:draft-only' > ~/.genus/coder.enabled
chmod 600 ~/.genus/coder.enabled
export GENUS_CODER_ENABLE=1
export GENUS_CODER_MODEL='<explizit gewähltes Coding-Modell>'

python deploy/entwickler_worker.py generate \
  --spec ~/.genus/entwickler/antwort-spec.json \
  --approval ~/.genus/entwickler/antwort-approval.json \
  --workspace ~/.genus/entwickler/worktrees/antwort-v1 \
  --output ~/.genus/entwickler/antwort.patch \
  --receipt ~/.genus/entwickler/antwort-generation.json
```

Der Provider erhält Ziel, Budget, Tests und ausschließlich `allowed_files`. Keine Umgebung,
Tokens, Git-Metadaten, Live-Datenbank oder übrigen Repositorydateien werden in den Prompt gelegt.
Die Quelle muss der vorbereitete, saubere detached Worktree auf dem freigegebenen Basis-Commit
sein. Das Hauptrepository und schmutzige Worktrees werden abgewiesen. Kritische Spezifikationen
werden vor dem Provideraufruf abgewiesen.

Zu Beginn kann statt eines API-Coders ein von Codex oder einem Menschen erzeugter Unified-Diff
als Patchdatei dienen. Der nachfolgende Vertrag ist identisch und damit providerneutral.

### 5. Anwenden und prüfen

```bash
genus entwickler pruefe-patch \
  ~/.genus/entwickler/antwort-spec.json \
  ~/.genus/entwickler/antwort-approval.json \
  ~/.genus/entwickler/antwort.patch

python deploy/entwickler_worker.py apply \
  --spec ~/.genus/entwickler/antwort-spec.json \
  --approval ~/.genus/entwickler/antwort-approval.json \
  --patch ~/.genus/entwickler/antwort.patch \
  --workspace ~/.genus/entwickler/worktrees/antwort-v1 \
  --receipt ~/.genus/entwickler/antwort-review.json
```

Die Werkbank wendet den Patch ausschließlich im detached Worktree an. Gates kommen aus einer
festen Registry: Diff-Check, Ruff, fokussierte oder vollständige Tests, Alltagsprobe,
Architekturbudget und Kartografie. `security_review` und `runtime_observation` bleiben sichtbar
manuell. Das Reviewpaket setzt `merge_ready` immer auf `false`.

### 6. Wirkung zurückgeben

```bash
genus entwickler lerne \
  ~/.genus/entwickler/antwort-spec.json \
  ~/.genus/entwickler/antwort-approval.json \
  --outcome accepted --reason quality --reviewer ronny

genus entwickler erfahrung
```

Mögliche Ausgänge sind `accepted`, `rejected`, `runtime_regression` und `withdrawn`. Bei einem
Fehlschlag erhöht der nächste Plan für dieselben Dateien Risiko und Prüfpflicht. Erfolg weitet
keine Rechte aus. Rohcode wird nicht in der Ergebnisdatei gespeichert.

## Bewusste Grenzen

- v1 eröffnet oder merged keinen Pull Request und führt keinen Deploy aus.
- Die Freigabedatei ist hashgebunden, aber keine kryptografische Personen-Signatur.
- Quellnähe ist Retrieval, keine semantisch bewiesene Root Cause.
- Ein grünes automatisches Gate ersetzt weder Diff-Review noch reale Laufzeitabnahme.
- Die Werkbank soll auf X1 oder CI laufen; der Pi bleibt Orchestrator und kann bei Bedarf nur
  kleine Drafts prüfen. Es wird kein großes Coding-Modell dauerhaft auf dem Pi geladen.
- Mehr Autonomie ist eine spätere, eigene Architekturentscheidung — nicht ein Schwellenwert in
  dieser Implementierung.
