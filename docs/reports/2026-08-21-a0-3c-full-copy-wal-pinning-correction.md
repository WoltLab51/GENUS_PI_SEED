# A0.3c Full-Copy WAL-Pinning · technisches Korrektur-Addendum

> **Status:** `validation pending`
>
> **Datum:** 2026-08-21
>
> **Scope:** A0.3c-Kopienbeweis; keine Produktdatenbankmutation, kein
> Produkt-Cutover und kein Live-Go

## Ergebnis vorweg

Der erste produktgroße A0.3c-Concurrency-Lauf hat einen Vertragsfehler in der
Übertragung des angenommenen A0.3b-Prototyps auf die neue Full-Copy-Lastform
sichtbar gemacht: Der absichtlich langlebige G1-Reader wurde bereits vor dem
vollständigen G2-/G3-Aufbau geöffnet und hielt dadurch während des gesamten
Bulk-Replays einen alten WAL-Snapshot fest. Auf der produktgroßen Kopie wuchs
der WAL so auf ungefähr `3.48 GB` und überschritt das verbindliche Budget von
`268435456 B` (`256 MiB`) deutlich.

Das ist nach dem derzeitigen Quell- und Historienbefund kein aufsummierter
Samplerwert und kein durch eine kleinere Autocheckpoint-Zahl lösbares Tuning-
Problem. Die Korrektur begrenzt stattdessen die Lebensdauer genau dieses
langlebigen Readers auf den Beweis, den er erbringen soll: Er wird unmittelbar
vor dem atomaren Pointer-Commit gebunden, bleibt über den Commit hinweg auf G1
und wird nach dem G1/G2-Nachweis wieder geschlossen. Kurzlebige Reader und der
konkurrierende Writer bleiben während des Bulk-Aufbaus aktiv.

Der korrigierte Kandidat ist noch nicht angenommen. Seine Quellhashes sind
unten vorab gebunden; Commit, vollständige Kandidaten-Gates und drei
konsekutive Pi-Kopienläufe bleiben bis zu ihrer tatsächlichen Verifikation
offen.

## Unveränderte historische Evidenz

Dieses Addendum ändert oder ersetzt weder den
[A0.3b-Prototypreport](2026-08-15-a0-3b-shadow-cutover-prototype.md) noch den
[menschlichen Annahmebeleg](../reviews/2026-08-18-a0-3b-prototype-acceptance.md).
Beide Dateien und ihre damaligen Hashbindungen bleiben byteidentische
historische Evidenz.

Der Annahmebeleg bindet den A0.3b-Ausgangscommit
`123ab6b5e6716c98bd53e78e297c42bc489136d6` und diese vier kanonischen
LF-Quellhashes:

| Rolle | Historisch angenommener SHA-256 |
|---|---|
| `experiments/a0_3b/__init__.py` | `c8fdd59854fa9822867aadf602ce2a9a2e5c2bf64e0d3f30930521a6ffaee871` |
| `experiments/a0_3b/__main__.py` | `612e28134dfd3b9ab029628a824de93b29c4637892a23921ae3f783a9e99890e` |
| `experiments/a0_3b/harness.py` | `f8e31096637eaaf5abc44a77f10b0f09eb362ad3f4ea7c9d4e3f1d2cc895b579` |
| `tests/test_a0_3b_shadow_cutover.py` | `e90a10c87a599de6e1fc0bd9a5cabd56ad9d9cb7536ea41eb2e228a0ce37fcc6` |

Die damaligen Messungen bleiben innerhalb ihres dokumentierten Scopes gültig:

- Der produktgroße Pi-Kopienlauf war der writer-freie vollständige Prototyplauf
  mit `1,194,364` Events. Sein WAL-High-Water betrug `19994392 B`.
- Der gleichzeitig laufende Writer-/Short-Reader-/Long-Reader-Beweis war im
  Abschlussreport ausdrücklich ein separater synthetischer `10k`-Lauf.
- A0.3c kombiniert erstmals die produktgroße frisch erworbene Kopie mit dem
  vollständigen `run_concurrency_probe` und damit mit dem über den gesamten
  Lauf gehaltenen Long-Reader.

Die neue Beobachtung widerlegt daher nicht die damaligen Messwerte. Sie zeigt,
dass deren zwei Lastformen nicht unverändert zu einer produktgroßen
Concurrency-Lastform zusammengesetzt werden konnten.

## Befund am unveränderten A0.3b-Kandidaten

Der angenommene Ablauf in `run_concurrency_probe` besitzt vor der Korrektur
folgende Reihenfolge:

1. `active_reader(...)` öffnet den langlebigen Reader vor dem Bulk-Aufbau.
2. `ActiveReader` startet mit `BEGIN` eine Transaktion und führt einen ersten
   `SELECT` aus, der den WAL-Snapshot etabliert.
3. G2-Build, Catch-up, unabhängiger G3-Replay, Verifikation und Cutover schreiben
   danach in dieselbe disposable SQLite-Datei.
4. Der langlebige Reader wird erst nach dem Cutover-Nachweis geschlossen.

Der A0.3b-Harness setzt weder `PRAGMA wal_autocheckpoint` noch
`PRAGMA journal_size_limit` und führt in diesem Ablauf keinen expliziten
`PRAGMA wal_checkpoint(...)` aus. SQLite kann einen WAL während eines aktiven
alten Snapshot-Readers nicht über dessen Endmark hinweg checkpointen und
resetten. Kleinere Batches oder ein niedrigerer Autocheckpoint-Schwellwert
beseitigen diese Sperre nicht; ein späteres `TRUNCATE` würde außerdem den zuvor
bereits gemessenen High-Water nicht rückwirkend ändern.

Beide Resource-Sampler lesen in einem festen Intervall direkt die Dateigröße
von `<database>-wal` per `stat().st_size` und speichern das Maximum. Sie
addieren keine Samples. Der beobachtete Wert ist daher die größte sichtbare
logische WAL-Dateigröße im Messfenster. Das 20-ms-Sampling kann kurze Spitzen
übersehen, aber aus einer kleineren Datei keine mehrere Gigabyte große Summe
erzeugen.

## Roter A0.3c-Lauf

Der fehlgeschlagene Lauf bleibt als negative Evidenz erhalten und darf nicht
als Teil einer grünen Serie wiederverwendet werden.

| Bindung | Wert |
|---|---|
| Kandidatencommit | `e5db14c43b396d54101645d8d0f4570512b21b54` |
| Runtime-/Set-Manifest-ID | `e108a99031e087206b3723309ff5073f4122ed22a4bfe3a300862f84d3055d4d` |
| Readiness-Manifest | intern `ff72327b37aa9386e5246185d9a29b5bfe224247025c6885669d68a37fb0a3ec`; Rohdatei `261ae6e75fb5b792ad2f63392febee8d0c38f7e4381d24ac004a367f749af84b` |
| Acquisition-Receipt-Rohhash | `72adf162b83dd3abecd450c1a1d17bb7eb0f0b45fbb65149ffcf08c3784d7268` |
| Run-Receipt-Rohhash / Folge | `465629b4a8cdd074001f499e40f59210dd261e9e59b56da7e937fc0e8ff826f7` / `1` |
| Journal-Entry-Rohhash | `3edff4dccc325ddbcb6c1ec2a0f7687c12204e8893220f509db289f02c454672` |
| exakter WAL-High-Water | `3483072752 B` |
| übrige Gates/Budgets | Build `135.48491106 s`; RSS `69779456 B`; max. Schreiben `1.171657898 s`; Fence `0.01785562 s`; Recovery `0.769486075 s`; 12/12 und 9/9 grün; Reader alt/neu grün; Mode A ohne Fallback |
| Serienfolge | `reset required` |

Die zugehörigen privaten Datenbankkopien und Receipts bleiben externe
Operator-Evidenz. Sie werden weder in dieses Repository kopiert noch automatisch
gelöscht.

## Korrigierter Kandidatenvertrag

Die fachlich kleinste Korrektur verschiebt ausschließlich den langlebigen
Snapshot-Reader:

1. Bulk-G2/G3, Catch-up und die unabhängige Verifikation laufen mit dem bereits
   vorhandenen konkurrierenden Writer und den kurzlebigen Reader-Transaktionen.
2. Am vorhandenen Fault-/Fence-Punkt `cutover_pre_commit` wird genau ein
   langlebiger Reader geöffnet. Er muss dort die noch aktive G1 binden.
3. Derselbe Reader bleibt während des atomaren Pointer-Commits offen und muss
   danach weiterhin die vollständige G1 sehen.
4. Ein frisch geöffneter Reader muss nach dem Commit die vollständige G2 sehen.
5. Der langlebige Reader wird auch auf jedem Fehlerpfad geschlossen.

Damit bleibt der eigentliche Old-or-New-Beweis erhalten, ohne den gesamten
Bulk-Replay unnötig mit einem alten WAL-Endmark zu pinnen. Die Korrektur ändert
nicht:

- Topologie C und Final-Sync Mode A;
- Batchgröße `3072` und die bestehende Bytegrenze;
- Writer-Intervall `0.005 s` und Short-Reader-Intervall `0.003 s`;
- die Grenzen `2.0 s` Writer/Fence, `180 s` Build, `10 s` Recovery sowie
  `256 MiB` RSS und WAL;
- zwölf Projektionsdigests, neun Sequenzzustände, Ledger-/Seal-/Anchor-Bindung;
- Copy-only-Scope und Verbot jedes produktiven Shadow-Aufbaus, Catch-ups oder
  Cutovers; die getrennte A0.3c-Runtime-Aktivierung bleibt erst nach vollständig
  grüner, gebundener Serie zulässig.

Die Reader-Lebensdauer muss im neuen Kandidaten explizit hash- und
receiptgebunden sein:

```text
long_reader_snapshot_scope = cutover_pre_commit_through_post_commit
bulk_replay_wal_pinned = false
```

Diese Felder beschreiben eine Korrektur des Beweisfensters, kein Retuning. Ein
abweichender oder fehlender Wert muss Manifest-, Run- und Serienverifikation
fail-closed rot machen.

## Neue Hash- und Kandidatenbindungen

Die historischen Hashes oben bleiben unverändert benannt und erhalten. Der
A0.3c-Readiness-Kandidat bekommt einen getrennten neuen Hashsatz; er darf nicht
durch stilles Überschreiben als rückwirkend identisch mit dem menschlich
angenommenen A0.3b-Stand dargestellt werden.

| Bindung | Neuer Wert |
|---|---|
| korrigierter Kandidatencommit | `validation pending` |
| `experiments/a0_3b/__init__.py` | `c8fdd59854fa9822867aadf602ce2a9a2e5c2bf64e0d3f30930521a6ffaee871` (byteidentisch) |
| `experiments/a0_3b/__main__.py` | `612e28134dfd3b9ab029628a824de93b29c4637892a23921ae3f783a9e99890e` (byteidentisch) |
| `experiments/a0_3b/harness.py` | `418a7169f9ee476c74fe4718033fe9af92c97991ea8c6f7e6bb6d91c5b30bb96` |
| `tests/test_a0_3b_shadow_cutover.py` | `3f9a333d08957457a610bf5f27638c6de90d47776f0cdc372f08b886e7e67e35` |
| A0.3c-Codehashsatz | package `ac681b50c2293167e2c0a7c025bcb452384d0aeb46c66badbe06d72cd6cb5e67`; CLI `2c1a796d3c27b7b32d7a79304cf3ea9d918f362132a745afa6b515b0221d1263`; Harness `4c0cf567fe06b8e1278d619950976db36a6f5b40de21fcd7ede855a32832d628`; Tests `a469101ac47f72509ba82065f04e5b4b5e68efdd28525dbf8effea3f39b74782` |
| Candidate-Config-SHA-256 | `0225367a6a6fc7c750c8223eaa5e9ccb860d7daa3973d6d7001405b3b3226cfd` |
| Runtime-Manifest-SHA-256 | `validation pending` |
| Runtime-Set-Manifest-ID | `validation pending` |

Ein neuer Commit erfordert neue Full-Suite-/A0.2-Gate-Receipts, ein neues
Readiness-Manifest, eine neue Stage-/Set-Bindung, ein neues Serienjournal und
drei frische Acquisitions. Alte und neue Run-Receipts dürfen weder im Manifest
noch in der Serie gemischt werden.

## Pflichtregressionen vor Pi-Validierung

Der korrigierte Kandidat ist erst prüfbar, wenn mindestens diese Regressionen
grün sind:

- Der persistente Long-Reader wird nicht während G2-Build, Catch-up oder G3-
  Bulk-Replay geöffnet, sondern genau am `cutover_pre_commit`-Punkt.
- Derselbe Reader sieht vor und nach dem Commit G1; ein frischer Reader sieht
  danach G2.
- Ein fehlgeschlagener erster Final-Sync-Versuch erhält den Old-or-New-Beweis
  beim Retry und hinterlässt keinen offenen Reader.
- Exceptions vor, während und nach der Reader-Bindung schließen Connection und
  Transaktion zuverlässig.
- Raw Receipt und A0.3c-Concurrency-Summary binden das Reader-Fenster; fehlende,
  zusätzliche oder abweichende Werte werden abgelehnt.
- Manifest-Verifikation lehnt den historischen A0.3b-Hash als aktuellen
  Korrekturkandidaten sowie jede Config-/Code-Tamperung ab.
- Serienverifikation lehnt eine Mischung aus altem und neuem Commit,
  Codehashsatz, Kandidatenconfig oder Manifest ab.
- Der vollständige lokale Testlauf, Ruff, Shellsyntax und die A0.2-Gates sind
  unter dem exakt gebundenen Kandidaten grün.

## Ausstehende Pi-Validierung

Alle folgenden Felder bleiben bis zu realen, receiptgebundenen Läufen offen.
Ein roter oder abgebrochener Lauf setzt die Serie zurück.

| Gate | Lauf 1 | Lauf 2 | Lauf 3 | Grenze |
|---|---:|---:|---:|---:|
| frische Acquisition | `pending` | `pending` | `pending` | jeweils neu |
| G2-Build | `pending` | `pending` | `pending` | `<= 180 s` |
| max. Schreibtransaktion | `pending` | `pending` | `pending` | `<= 2.0 s` |
| finaler Fence | `pending` | `pending` | `pending` | `<= 2.0 s` |
| Writer-Timeouts | `pending` | `pending` | `pending` | `0` |
| Writer-Starvation | `pending` | `pending` | `pending` | `false` |
| Peak RSS | `pending` | `pending` | `pending` | `<= 268435456 B` |
| WAL High-Water | `pending` | `pending` | `pending` | `<= 268435456 B` |
| Recovery | `pending` | `pending` | `pending` | `<= 10 s` |
| Projektionen / Sequenzen | `pending` | `pending` | `pending` | `12/12`, `9/9` |
| Long-Reader alt / Fresh-Reader neu | `pending` | `pending` | `pending` | G1/G1, G2 |
| Mode A / Fallback | `pending` | `pending` | `pending` | A / keiner |
| Run-Receipt-SHA-256 | `pending` | `pending` | `pending` | je eindeutig |

Abschließend sind noch zu binden:

| Abschlussartefakt | Wert |
|---|---|
| finales Serien-Receipt | `validation pending` |
| Serien-Receipt-SHA-256 | `validation pending` |
| Readiness-/Series-Crossbinding | `validation pending` |
| Kandidatenstatus | `validation pending` |

## Entscheidungsschranke

Dieses Addendum autorisiert weder die rückwirkende Änderung der A0.3b-Annahme
noch eine Produktintegration. Ein technisch grüner Korrekturkandidat bleibt ein
neuer A0.3c-Kandidat. Seine Runtime-Aktivierung muss an den neuen Commit, das
neue Readiness-Manifest, das neue finale Serien-Receipt und die neue Set-
Manifest-ID gebunden sein. Shadow-Aufbau, Catch-up oder Cutover gegen die
Produktdatenbank sowie jedes Live-Go benötigen weiterhin eine getrennte
ausdrückliche menschliche Entscheidung.
