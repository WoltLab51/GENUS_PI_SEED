# A0.3b — Shadow Generation & Atomic Cutover Prototype

> **Status:** technisch grüner Kandidat · menschliche Entscheidung ausstehend
>
> **Messstand:** 2026-08-18
>
> **Baseline:** `123ab6b5e6716c98bd53e78e297c42bc489136d6`
>
> **Topologie:** Option C · G1/G2/G3 in derselben SQLite-Datei
>
> **Ausgewählter Final-Sync:** A · `a_bounded_fence`
>
> **Produktaktivierung:** nein

## Ergebnis zuerst

Der isolierte A0.3b-Prototyp erfüllt die angenommenen Korrektheits- und
Ressourcengates lokal sowie auf einer per SQLite Backup API erzeugten Kopie der
Pi-Produktdatenbank.

- G1, G2 und der unabhängig aufgebaute Verifier G3 stimmen in allen zwölf
  Projektionen und allen neun relevanten `sqlite_sequence`-Zuständen überein.
- Der Ledger bleibt unverändert; Seal und ein bereits vorhandener Anchor werden
  gebunden und erneut verifiziert.
- Der Generationenwechsel erfolgt im bevorzugten Modus A: bounded Rest-Tail und
  Pointer-CAS liegen in derselben kurzen Transaktion.
- Reopen/Recovery ergibt ausschließlich eine vollständig alte oder vollständig
  neue Generation. Der erfolgreiche Endzustand ist
  `NEW_ACTIVE_OLD_RETIRED`.
- Der finale lokale 1M-Lauf und der finale Pi-Kopienlauf halten 180 Sekunden
  G2-Build, 2 Sekunden pro Schreibtransaktion, 256 MiB RSS, 256 MiB WAL und
  10 Sekunden Recovery ein.
- Option B wurde als expliziter Crash-/Recovery-Pfad geprüft, aber weder
  automatisch gewählt noch als Livepfad empfohlen.

Damit ist der **A0.3b-Prototyp technisch annahmefähig**. Dieser Befund ist kein
Live-Go: Produktcode, Produktreader und Produktwriter kennen den
Generationen-Pointer noch nicht. Außerdem ist SQLite 3.46.1 auf dem Pi wegen der
offiziell dokumentierten WAL-Reset-Race nicht live-eligible.

## Scope und Nicht-Scope

Der Kandidat ändert ausschließlich:

- `experiments/a0_3b/`;
- `tests/test_a0_3b_shadow_cutover.py`;
- diesen datierten Report und genau einen Indexlink.

Unverändert bleiben insbesondere:

- `genus/`, `deploy/` und `schema.sql`;
- die produktiven Replay-, Integrity-, Startup- und Migrationspfade;
- A0.2 und A0.1;
- `NOW.md`, `ROADMAP.md`, ADRs und generierte Kartografie;
- die laufende Produktdatenbank auf dem Pi, die vom Experiment weder
  schreibend geöffnet noch beschrieben wurde.

Es fand kein Commit, Push, PR, Merge, Deployment, Dienststopp, Dienstneustart,
Pause, Reseal oder Anchor-Neubau statt.

## Topologie und Invarianten

Der Prototyp verwaltet in **einer** disposable SQLite-Datei:

| Generation | Rolle vor Cutover | Rolle nach Cutover |
|---|---|---|
| G1 | aktive, sichtbare Ausgangsgeneration | retired |
| G2 | bounded aufgebaute Shadow-Generation | active |
| G3 | unabhängige Verifier-Generation | verifier |

Physisch bestehen 36 Projektionstabellen
(12 Projektionen × 3 Generationen), sieben A0.3b-Metadatentabellen und 108
connection-local default-deny DML-Guards. Neun Autoincrement-Sequenzen je
Generation werden zusätzlich digestgebunden.

Der Ablauf ist:

1. H0 unter einem kurzen Writer-Lock erfassen.
2. G2 in Event- und Byte-beschränkten Batches bis H0 aufbauen.
3. G2 bounded an einen späteren festen Head W nachziehen.
4. G3 unabhängig aus dem Ledger bis W neu aufbauen.
5. G1 = G2 = G3 für zwölf Projektionen und neun Sequenzen beweisen.
6. Im Modus A einen bounded Tail bis H* auf G2/G3 anwenden und den Pointer
   G1 → G2 in derselben `BEGIN IMMEDIATE`-Transaktion wechseln.
7. Datei schließen, neu öffnen und Schema, Topologie, Receiptketten, Ledger,
   Projektionen und Sequenzen fail-closed validieren.

Modus B bleibt ein expliziter Testpfad: Nach einer Verifikationsbasis werden
Writes vorübergehend atomar nach G1/G2/G3 geroutet und der Pointer später in
einer Metadatentransaktion gewechselt. Es gibt keinen stillen A→B-Fallback.

## Verbindliche Gates und gemessene Ergebnisse

| Gate | Grenze | Lokal 1M | Pi-Produktkopie | Ergebnis |
|---|---:|---:|---:|---|
| G2-Build | `<= 180 s` | `84.7806383 s` | `169.746161856 s` | PASS |
| maximale experimentelle Schreibtransaktion | `<= 2.0 s` | `0.6792519 s` | `1.656518293 s` | PASS |
| finaler Fence | `<= 2.0 s` | `0.0056526 s` | `0.008216829 s` | PASS |
| Peak RSS | `<= 268435456 B` | `44765184 B` | `42303488 B` | PASS |
| WAL High-Water | `<= 268435456 B` | `7494312 B` | `19994392 B` | PASS |
| Recovery | `<= 10 s` | `0.8743786 s` | `0.460784818 s` | PASS |
| Projektionen | 12/12 | 12/12 | 12/12 | PASS |
| Sequenzen | 9/9 | 9/9 | 9/9 | PASS |
| Ledger | unverändert | ja | ja | PASS |
| Final-Sync | A, kein Fallback | A | A | PASS |

Die Pi-Kopie enthielt `1,194,364` Events. G2 und G3 wurden jeweils in 389
Batches aufgebaut; der unabhängige G3-Replay dauerte `170.973835998 s`. Der
DB-High-Water betrug `926822400 B`.

Der lokale finale 1M-Lauf nutzte 245 Batches; G3 dauerte `78.5420006 s`. Der
DB-High-Water betrug `1050230784 B`. Beide Läufe materialisierten weder Ledger
noch Projektionen vollständig im Python-Speicher.

## Lokale Matrix

| Fall | Ergebnis | Beleg |
|---|---|---|
| 0/1/1023/1024/1025 Events | grün | Fixed-Head, exakt einmal, 12/12, 9/9, A |
| Golden Ledger | grün | Oracle, 12 Projektionen, Seal und historischer Prefix-Anchor |
| historical-v1.1 | grün | Quelle read-only und unverändert; Rehydration in separate Current-Kopie, keine Migration |
| 10k/100k | grün | bounded Batches und alle Budgets |
| 1M final | grün | Receipt `a44c11c80126326b52a4ea0b14e2e42eceb2f4efd3ccb487c1ed18c220cece1b` |
| Konkurrenz 10k final | grün | 40 Writer-Commits, 0 Timeout/Fehler, keine Starvation, 22/22 Handoffs |
| Prozess-Kill, Modus A | 30/30 grün | Receipt `d8ca1cea93f9dd18f04082aedbd3c666368b242a2b42c7d86bd60a9b9ab35020` |
| Prozess-Kill, Modus B | 34/34 grün | Receipt `1a2855360be2b906f7a99424f7055a38bf6102ce92bbd568359850c8277b6d08` |

Im finalen Konkurrenzlauf lagen p50 bei `0.0464787 s`, p95 bei
`0.2666682 s` und das Maximum bei `0.4414618 s`. Jeder der 22 kooperativen
Slots lag außerhalb einer Replay-Transaktion und ließ exakt einen realen
Writer-Commit zu; der längste Slot dauerte `0.094055 s`.

## Bewusst erhaltene rote Evidenz

Rote Läufe wurden nicht überschrieben.

### Scheduler-/Writer-Fairness

Der erste 10k-Konkurrenzlauf hatte bei null Timeouts und null Fehlern eine
maximale Writerlatenz von `2.0672737 s` und meldete Starvation. Ein bloßer
1-ms-Yield blieb mit etwa `2.2126 s` ebenfalls rot.

Die wirksame Korrektur war ein ehrliches closed-loop Lastmodell plus genau ein
bounded Writer-Admission-Slot nach jedem committed Replay-Batch, immer außerhalb
der Transaktion. Das rote Receipt bleibt unter
`91817b065dd7abd3bd59429d3d2f08562fdf2ac8210008c49eb7066cad7dec0a`,
das grüne unter
`18bc0dc395b67da66223e24f6dc8213865429362ea083cb9dbed53cdb31ccc2e`.

### Lokaler 1M-Pfad

Ein früher 4096er Lauf überschritt im G3-Pfad das 2-Sekunden-Gate. Ein
2048er Lauf hielt die Einzeltransaktionen, brauchte aber `231.0844326 s` für
G2 und verfehlte damit 180 Sekunden.

Die statische Analyse lokalisierte wiederholte Regex-Umschreibung derselben
Projektor-SQL-Texte. Ein auf 128 Einträge hart begrenzter, adapterlokaler Cache
speichert nur umgeschriebenen SQL-Text — keine Resultate, Parameter, Cursor oder
Events. Danach sank der 100k-Lauf von `16.3927 s` auf `5.818 s`; der finale
1M-Lauf war mit den oben genannten Werten grün. Semantik, Guards, Receipts und
Digests bleiben unverändert geprüft.

### Pi-Batchtuning

Der erste Pi-Kopienlauf mit 4096 Events pro Batch war fachlich vollständig
konsistent, aber rot:

- G2-Build `158.639406994 s`;
- eine G2-Transaktion `2.167361215 s`;
- G3-Maximum `1.779271125 s`;
- A gewählt, kein Fallback;
- 12/12 Projektionen, 9/9 Sequenzen, Ledger unverändert;
- Recovery `NEW_ACTIVE_OLD_RETIRED`.

Der rote Receipt
`b140dd449977f3eaf21533c884cf5e765cc8f99bea51893cd13d2ed5778b3bf5`
bleibt in seinem privaten Root erhalten. Genau ein neuer, frischer Lauf mit
3072 Events pro Batch reduzierte die maximale Transaktion auf
`1.656518293 s`, während G2 mit `169.746161856 s` unter 180 Sekunden blieb.
Code und Gates wurden zwischen diesen Läufen nicht geändert.

## Crash-, Tamper- und Recovery-Beweis

Die 119 fokussierten Tests decken unter anderem ab:

- Pre-/Post-Commit und echte Prozess-Kills in Build, Catch-up, G3-Purge,
  G3-Replay, Verifikation, Admission und Cutover;
- vollständige alte oder neue Zustände und deterministischen Retry;
- Projector-Fehler, Oracle-Mismatch und simuliertes `SQLITE_FULL`;
- unbekannte oder widersprüchliche Rollen, Zustände und Topologien;
- Receipt-, Hashketten-, Schema- und Metadatenmanipulation;
- DML-Tamper an allen 108 Guard-Triggern;
- rohe `sqlite_sequence`-Manipulation in G1, G2 und G3;
- parallele Builder und lebende/stale Leases;
- WAL→DELETE-Manipulation;
- Lücken in SQLite-IDs;
- harte Batchcaps, bounded G3-Purge und vollständige Transaktionsmessung;
- false-positive Budget-, Telemetrie- und Receipt-Gates.

Die Fault-Matrix behauptet keinen literal power loss. `SQLITE_FULL` ist eine
gezielte Fehler-Injektion, kein physisch volles Dateisystem.

## Pi-Kopienbeweis

Nur der temporäre Acquisition-Helper erhielt den Produktpfad. Er öffnete die
Quelle als URI `mode=ro`, in Autocommit und mit `PRAGMA query_only=ON`. Sein
Trace enthielt ausschließlich `SELECT` und `PRAGMA`; `total_changes` blieb
null. Das Ziel wurde exklusiv in einem frischen, EUID-eigenen `0700`-Root
angelegt und ausschließlich per `sqlite3.Connection.backup()` gefüllt.

Der A0.3b-Prozess erhielt nur die Kopie. Drei `/proc`-Stichproben bestätigten:

- Produktpfad nicht in `cmdline`;
- Produktpfad nicht in `environ`;
- Produkt-Inode nicht in offenen Deskriptoren.

Vor und nach dem Lauf galten:

- Repo-HEAD und `origin/main` exakt
  `123ab6b5e6716c98bd53e78e297c42bc489136d6`;
- Worktree sauber;
- kein Pause-Marker;
- Learner PID `523808`, Bot PID `523815`;
- beide Dienste `active/running`, `NRestarts=0`;
- kein Produkt-Journal und kein Dienstneustart.

Normale Produktwriter blieben aktiv. Deshalb wird keine künstliche
Byte-Unverändertheit der Produktdatei behauptet. Nichtmutation durch das
Experiment ist durch fehlende Schreibfähigkeit, Backup API und Prozess-/
Pfadtrennung belegt.

Der Postcheck öffnete ausschließlich die Kopie und bestätigte erneut:

- exaktes A0.3b-Extended-Schema;
- Topologie `new_active` mit aktiver G2;
- G1 = G2 = G3 für Projektionen und Sequenzen;
- unveränderten Ledger und Seal;
- denselben bereits vorhandenen, byteidentischen Anchor;
- den grünen A-Receipt ohne Fallback.

Gebundene Pi-Receipts:

| Receipt | SHA-256 |
|---|---|
| Acquisition | `2d3c6bae41480a91db5c6304dff972d08bbc4361c3c8ec829206dd90a26b6c45` |
| A0.3b Prototype | `00838af1bf0698515349b4dafc0a66ee9f025ce9773663e09bd61a6458046e71` |
| Postcheck | `2da013eeec6fbc6a44d850102539a7b61fe0cec76771e2d33a8771618071e354` |

Die beiden temporären, nicht zu promotenden Messhelfer waren ebenfalls
hashgebunden:

| Helfer | SHA-256 |
|---|---|
| `acquire_copy.py` | `aaa201a9f1226d61708492ccbdf049b12f9bb24f850cc2ba6f84ba62a17dfd0d` |
| `postcheck_copy.py` | `bad123d767a21ed403056e38c65f5ff3376da47b037be269f44b52e271669a9f` |

Die Datenbankkopien bleiben in privaten Pi-Roots zur menschlichen Prüfung und
werden nicht hochgeladen oder automatisch gelöscht.

## Speicherbudget-Vorschlag

Der höchste beobachtete zusätzliche Main-DB-Bedarf gegenüber der jeweiligen
Ausgangsdatei lag bei rund `339.3 MB` (lokales 1M-Synthetic); auf der
Pi-Produktkopie waren es rund `304.7 MB`. Der höchste beobachtete WAL lag bei
rund `21.7 MB` in einem bewusst roten Pi-Lauf.

Für einen späteren Live-Kandidaten wird daher vorgeschlagen:

- **512 MiB** zusätzliches Main-DB-Budget für G2+G3;
- das bereits angenommene **256 MiB** WAL-Budget bleibt separat bestehen;
- vor jedem Lauf zusätzlich Platz für eine vollständige verifizierte
  Backup-Kopie und 20 % Betriebsreserve.

Dieses Speicherbudget ist nur ein Messvorschlag. Es wird erst durch eine
separate menschliche Entscheidung verbindlich.

## Gebundener Kandidat

| Datei | SHA-256 |
|---|---|
| `experiments/a0_3b/__init__.py` | `c8fdd59854fa9822867aadf602ce2a9a2e5c2bf64e0d3f30930521a6ffaee871` |
| `experiments/a0_3b/harness.py` | `f8e31096637eaaf5abc44a77f10b0f09eb362ad3f4ea7c9d4e3f1d2cc895b579` |
| `experiments/a0_3b/__main__.py` | `612e28134dfd3b9ab029628a824de93b29c4637892a23921ae3f783a9e99890e` |
| `tests/test_a0_3b_shadow_cutover.py` | `e90a10c87a599de6e1fc0bd9a5cabd56ad9d9cb7536ea41eb2e228a0ce37fcc6` |

Letzter fokussierter Stand vor diesem Report: **119 Tests bestanden**; Ruff
und `git diff --check` grün. Nach dem Report folgt die abschließende erneute
Ausführung.

## Grenzen vor jeder Liveintegration

1. Dies ist Prüf- und Prototypcode unter `experiments/`, kein Produktpfad.
2. Produktreader und -writer sind noch nicht generation-aware.
3. Der kooperative Writer-Slot beweist die gemessene Lastform, nicht allgemeine
   Scheduler-Fairness für beliebige Writerzahlen.
4. Der Recovery-Beweis nutzt echte Prozess-Kills, aber keinen Hardware-
   Stromverlust.
5. SQLite 3.46.1 auf dem Pi liegt im offiziell dokumentierten betroffenen
   Bereich der seltenen WAL-Reset-Race. SQLite nennt 3.51.3 und später sowie
   die Backports 3.44.6 und 3.50.7 als gefixt. Die Race erfordert mehrere
   Connections mit gleichzeitigem Write/Checkpoint — genau deshalb bleibt
   die aktuelle Pi-Version für Live-Cutover fail-closed. Siehe
   [SQLite WAL, Abschnitt 11](https://www.sqlite.org/wal.html#the_wal_reset_bug)
   und [Release 3.51.3](https://www.sqlite.org/releaselog/3_51_3.html).
6. Vor Produktintegration sind ein generation-aware Produktdesign, eine
   gefixte SQLite-Version und ein weiteres ausdrückliches Human-Go erforderlich.

## Menschliche Entscheidung

```text
A0.3b Shadow Generation & Atomic Cutover candidate:

[ ] Accept candidate
[ ] Reject candidate
[ ] Request changes
```

**Formeller Status: menschliche Prüfung ausstehend.**

Eine Annahme dieses Kandidaten würde nur den experimentellen A0.3b-Beweis und
die Auswahl von Modus A bestätigen. Sie autorisiert weder Produktintegration,
Migration noch Live-Cutover.
