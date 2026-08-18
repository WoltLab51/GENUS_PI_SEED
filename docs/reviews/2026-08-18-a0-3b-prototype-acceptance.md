# A0.3b Shadow Generation & Atomic Cutover · menschlicher Annahmebeleg

> **Status:** accepted human decision · live activation blocked
>
> **Reviewer:** Ronny
>
> **Decision date:** 2026-08-18
>
> **Entscheidung:** A0.3b prototype accepted · Option C / Mode A / batch 3072

## Gebundene Evidenz

Ronny nimmt den isolierten A0.3b-Prototyp an. Die fachliche Grundlage ist der
unveränderte
[A0.3b Shadow Generation & Atomic Cutover Prototype Report](../reports/2026-08-15-a0-3b-shadow-cutover-prototype.md).

| Bindung | Wert |
|---|---|
| Ausgangscommit | `123ab6b5e6716c98bd53e78e297c42bc489136d6` |
| Report SHA-256 | `fe5edd268395d5e02be595997e93678d2a95ffaabcc1f2b275259429a8a155f1` |
| `experiments/a0_3b/__init__.py` | `c8fdd59854fa9822867aadf602ce2a9a2e5c2bf64e0d3f30930521a6ffaee871` |
| `experiments/a0_3b/harness.py` | `f8e31096637eaaf5abc44a77f10b0f09eb362ad3f4ea7c9d4e3f1d2cc895b579` |
| `experiments/a0_3b/__main__.py` | `612e28134dfd3b9ab029628a824de93b29c4637892a23921ae3f783a9e99890e` |
| `tests/test_a0_3b_shadow_cutover.py` | `e90a10c87a599de6e1fc0bd9a5cabd56ad9d9cb7536ea41eb2e228a0ce37fcc6` |

Die akzeptierte Pi-Kopienmessung ist durch drei getrennte Receipts gebunden:

| Receipt | SHA-256 |
|---|---|
| Acquisition | `2d3c6bae41480a91db5c6304dff972d08bbc4361c3c8ec829206dd90a26b6c45` |
| A0.3b Prototype | `00838af1bf0698515349b4dafc0a66ee9f025ce9773663e09bd61a6458046e71` |
| Postcheck | `2da013eeec6fbc6a44d850102539a7b61fe0cec76771e2d33a8771618071e354` |

## Menschliche Entscheidung

```text
[x] Accept A0.3b prototype
[ ] Reject
[ ] Request changes

Live activation: BLOCKED
```

Angenommen sind:

- Topologie C mit versionierten Generationen in derselben SQLite-Datei;
- Final-Sync Mode A, `a_bounded_fence`;
- eine begrenzte Batchgröße von 3072 Events;
- kein Fallback im akzeptierten Pi-Kopienlauf;
- der experimentelle Beweis gegen Fixtures, synthetische Ledger und
  Produktdatenbankkopien.

Der akzeptierte Pi-Kopienlauf hielt alle angenommenen A0.3-Budgets:

| Gate | Akzeptierter Wert |
|---|---:|
| G2-Build | `169.746161856 s` |
| Peak RSS | `42303488 B` |
| WAL High-Water | `19994392 B` |
| maximale experimentelle Schreibtransaktion | `1.656518293 s` |
| finaler Writer-Fence | `0.008216829 s` |
| Recovery | `0.460784818 s` |
| Recoveryzustand | `NEW_ACTIVE_OLD_RETIRED` |
| Projektionen | 12/12 |
| Sequenzen | 9/9 |
| Ledger | unverändert |

Der vorherige rote Pi-Lauf mit Batchgröße 4096 und einer
`2.167361215 s` langen Schreibtransaktion bleibt als Receipt
`b140dd449977f3eaf21533c884cf5e765cc8f99bea51893cd13d2ed5778b3bf5`
Teil der permanenten Messgeschichte. Die Annahme überschreibt oder relativiert
diesen Befund nicht.

## Kein Live-Go

Diese Entscheidung nimmt den **Prototyp** an. Sie aktiviert keine
Produktfunktion. Produktreader und Produktwriter sind nicht generation-aware,
und weder Shadow-Aufbau noch Catch-up oder Cutover dürfen gegen die
Produktdatenbank ausgeführt werden.

Die aktuell für GENUS auf dem Pi verwendete Python-Runtime meldet SQLite
`3.46.1`. Diese Version liegt im von SQLite dokumentierten Bereich der
[WAL-reset race](https://www.sqlite.org/wal.html#the_wal_reset_bug) und enthält
nicht den für
[SQLite 3.51.3](https://www.sqlite.org/releaselog/3_51_3.html) bestätigten Fix.
Für GENUS zählt nicht die Version des `sqlite3`-CLI, sondern
[`sqlite3.sqlite_version`](https://docs.python.org/3/library/sqlite3.html#sqlite3.sqlite_version)
der tatsächlich verwendeten Python-Runtime.

## Nächster aktiver Schritt: A0.3c

**A0.3c — Runtime Prerequisite & Live Readiness** ist der einzige aktive
Produktentwicklungspfad. Er verändert die Produktdatenbank nicht und
autorisiert keine Live-Aktivierung.

A0.3c muss vor einem weiteren Human-Go mindestens beweisen:

1. Der genaue Python-Executable- und Environment-Pfad jedes betroffenen
   GENUS-Prozesses ist bekannt und reproduzierbar.
2. Derselbe Prozesspfad protokolliert `sys.executable`,
   `sqlite3.sqlite_version` und `sqlite3.sqlite_version_info`. Das Gate bleibt
   fail-closed, solange die Runtime nicht nachweislich den WAL-reset-Fix enthält;
   Ziel ist eine [aktuelle 3.53.x-Runtime](https://www.sqlite.org/releaselog/current.html),
   die normale Mindestgrenze ist
   `sqlite3.sqlite_version_info >= (3, 51, 3)`.
3. Die vollständige GENUS-Suite sowie die A0.2-Golden-/SQLite-Gates sind unter
   genau dieser Runtime grün.
4. Mindestens drei **aufeinanderfolgende** Läufe verwenden jeweils eine frisch
   read-only erworbene Pi-Produktdatenbankkopie, denselben Kandidaten, dieselbe
   Runtime, dieselben Gates und Batchgröße 3072. Zwischen den drei Läufen wird
   weder getunt noch Code oder Konfiguration gewechselt.
5. Jeder dieser drei Läufe erfüllt einzeln:
   - maximale Schreibtransaktion und finaler Fence jeweils höchstens `2.0 s`;
   - null Writer-Timeouts und keine Writer-Starvation;
   - Peak RSS und WAL High-Water jeweils höchstens `256 MiB`;
   - G2-Build höchstens `180 s` und Recovery höchstens `10 s`;
   - 12/12 Projektionsdigests und 9/9 Sequenzzustände;
   - unverändertes Ledger, ausschließlich vollständig alt oder vollständig neu;
   - Mode A ohne Fallback.
6. Jeder Fehlversuch unterbricht die Serie. Ein erneutes Tuning ist ein neuer,
   separat zu messender Kandidat und kein automatischer Fallback.

Der im Report vorgeschlagene zusätzliche Main-DB-Rahmen von 512 MiB ist mit
dieser Entscheidung **nicht** verbindlich angenommen. Shadow-/Scratch-Platz,
vollständige Backup-Kopie und Betriebsreserve brauchen in A0.3c eine getrennte
menschliche Speicherbudgetentscheidung.

## Autorisiert und nicht autorisiert

Autorisiert ist ausschließlich die Repository-Promotion des gebundenen
Prototyps, seiner Tests, seines Reports und dieser Statusdokumentation über
Commit, Review, grüne CI, Merge und Pi-Fast-Forward.

Nicht autorisiert sind insbesondere:

- Shadow-Tabellen oder Generationenmetadaten in der Produktdatenbank;
- produktiver Catch-up, Cutover, Migration oder Ersatz des bestehenden
  Replay-/Integrity-Pfads;
- ein Runtime-Upgrade ohne reproduzierbaren Installations- und Rollbackpfad;
- ein Versionsnachweis nur über das `sqlite3`-CLI;
- Live-Aktivierung ohne vollständig grünes A0.3c und ein weiteres ausdrücklich
  gebundenes Human-Go.

A0.2, A0.1a und A0.1b bleiben eingefroren. Codex setzt diese Entscheidung
ausschließlich als technischer, nicht autoritativer Operator um.
