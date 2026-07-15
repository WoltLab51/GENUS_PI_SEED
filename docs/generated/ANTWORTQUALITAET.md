# GENUS Alltagsprobe · Antwortqualität v1

> **Status:** generierte, hermetische Abnahmefläche · menschliche Wertung bleibt bindend
>
> **Suite:** `2026-07-13.1` · **Inhalt:** `3f98e4c265d447a4`
>
> **Datengrenze:** ausschließlich synthetische In-Memory-Fälle; kein Pi-Ledger, kein Chat-Export, kein Modell als Richter

## Ergebnis zuerst

Die harten Verträge stehen bei **85/85**. Menschlich akzeptiert sind **4/17** Fälle; **13** warten auf die erste Bewertung und **0** sind nach einer Änderung veraltet.

Das ist bewusst **keine Gesamtnote**. Grün beweist Treue, Ehrlichkeit, Richtung, Anschluss und Datensparsamkeit. Ob eine Antwort nativ, tief und nützlich wirkt, entscheidet Ronny an genau dem hier gezeigten Wortlaut.

## Harte Dimensionen

| Dimension | bestanden | fehlgeschlagen | Verträge |
|---|---:|---:|---:|
| Fakten- und Richtungstreue | 17 | 0 | 17 |
| Nichtwissen und Unsicherheit | 21 | 0 | 21 |
| Herkunft und Nachvollziehbarkeit | 5 | 0 | 5 |
| Modelltransparenz | 5 | 0 | 5 |
| Dialoganschluss | 11 | 0 | 11 |
| Mehrteilige Antworten | 3 | 0 | 3 |
| Bekannte Alltagsreibungen | 6 | 0 | 6 |
| Datensparsamkeit | 17 | 0 | 17 |

## Fallübersicht

| Fall | harte Verträge | menschlich | Antwort-Hash |
|---|---:|---|---|
| `01-gruss-ohne-technikrest` · Ein natürlicher Gruß | 5/5 | `accepted` | `cd6161b6d420` |
| `02-definition-hund` · Belegte Alltagsdefinition | 7/7 | `accepted` | `74bd178ac90f` |
| `03-definition-schwach` · Schwach belegte Bedeutung | 4/4 | `accepted` | `d9d788bdfab4` |
| `04-definition-korroboriert` · Unabhängig bestätigte Bedeutung | 4/4 | `accepted` | `eb8d42e5a8d3` |
| `05-beziehung-direkt` · Direkte gerichtete Beziehung | 6/6 | `review_pending` | `ab09b8f189b1` |
| `06-beziehung-transitiv` · Mehrstufige Herleitung | 6/6 | `review_pending` | `92e735fcbb4e` |
| `07-beziehung-offen` · Offene Welt statt falsches Nein | 6/6 | `review_pending` | `3611007a75b0` |
| `08-deuter-leer` · Ehrliches Nichtverstehen | 4/4 | `review_pending` | `091e67d91c5f` |
| `09-pflichtslot-fehlt` · Unvollständige Beziehung | 5/5 | `review_pending` | `a62b0b48ccaf` |
| `10-freie-definition` · Freie Formulierung, graphgeprüft | 5/5 | `review_pending` | `ed8ea16ffc00` |
| `11-empfehlung-noch-nicht` · Verstandene, noch nicht beherrschte Bitte | 4/4 | `review_pending` | `4364c8ffbacf` |
| `12-warum-rueckbezug` · Warum bleibt am Thema | 4/4 | `review_pending` | `2baa42cb91a0` |
| `13-anschluss-ja` · Ein angebotenes Thema wird eingelöst | 6/6 | `review_pending` | `628e9ee54bbd` |
| `14-von-vorhin` · Rückbezug über eine Floskel hinweg | 4/4 | `review_pending` | `bdf1ffaf60ee` |
| `15-mehrsegment` · Gruß, Frage und Dank in einer Nachricht | 6/6 | `review_pending` | `354208b8a5e3` |
| `16-mehrsegment-mit-luecke` · Gruß plus unvollständige Frage | 5/5 | `review_pending` | `780f2cbf3025` |
| `17-enge-korrektur` · Eine Lesart wird gezielt korrigiert | 4/4 | `review_pending` | `a12a2e49dbf3` |

## So wird menschlich abgenommen

Für jeden Fall werden **Ton** und **Nutzen** getrennt als `traegt`, `holprig` oder `unbrauchbar` bewertet. Die Freigabe in `docs/reviews/ALLTAGSPROBE_V1.json` traegt Fall- und Antwort-Hash. Ändert sich Fixture oder Wortlaut, wird sie automatisch `review_stale`; alte Zustimmung kann also keine neue Antwort absegnen.

## Die Fälle

### 01-gruss-ohne-technikrest · Ein natürlicher Gruß

Eine soziale Geste soll warm beantwortet werden, ohne technischen Nachspann.

**Zug 1 · Frage**

> Moin, schön dich zu sehen!

**Zug 1 · GENUS**

```text
Hallo! Schön, dass du da bist. Was beschäftigt dich gerade?
```

Struktur: `outcome=answered` · `readings=['gruss']` · `anchor=Moin, schön dich zu sehen!`

**Automatische Verträge**

- ✅ **Bekannte Alltagsreibungen:** Der Gruß wird sozial beantwortet.
- ✅ **Bekannte Alltagsreibungen:** Kein Technikrest und keine falsche Fähigkeitslücke.
- ✅ **Modelltransparenz:** Die strukturelle Lesart bleibt sichtbar.
- ✅ **Nichtwissen und Unsicherheit:** Der Zug ist als beantwortet eingeordnet.
- ✅ **Datensparsamkeit:** Kein synthetischer Dialogrohtext gelangt ins Ledger.

**Menschliche Prüffrage:** Klingt dieser Einstieg wie ein warmer, unaufdringlicher GENUS-Gruß?

Status: `accepted` · Fall `02aae5803c26` · Antwort `cd6161b6d420`

<details>
<summary>Bewertungsvorlage mit vollständigen Hashes</summary>

```json
{
  "case_id": "01-gruss-ohne-technikrest",
  "case_fingerprint": "02aae5803c26ca717dbacc6ea948d94c0bc56c2a89e856831c50096cf5e3b2d7",
  "response_sha256": "cd6161b6d420ebedb7eb84fe145a55bc4839503c27f2592c8cddcb33a40c1029",
  "ton": "traegt",
  "nutzen": "traegt",
  "reviewer": "ronny",
  "reviewed_at": "YYYY-MM-DDTHH:MM:SS+02:00",
  "note": ""
}
```

</details>

Wertung von `ronny`: Ton `traegt`, Nutzen `traegt`. ok

### 02-definition-hund · Belegte Alltagsdefinition

Eine bekannte Bedeutung und ihr Elternbegriff müssen vollständig erhalten bleiben.

**Zug 1 · Frage**

> Was ist ein Hund?

**Zug 1 · GENUS**

```text
»Hund« bedeutet hier: ein Haustier, dessen Vorfahre der Wolf ist. Dabei zählt »Hund« zu »Haustier«.
```

Struktur: `outcome=answered` · `readings=['definition']` · `anchor=Was ist ein Hund?`

**Automatische Verträge**

- ✅ **Fakten- und Richtungstreue:** Die Bedeutung ist ein strukturierter Claim.
- ✅ **Fakten- und Richtungstreue:** Der belegte Elternbegriff bleibt erhalten.
- ✅ **Herkunft und Nachvollziehbarkeit:** Bedeutung und Hierarchie tragen ihre Quellen.
- ✅ **Fakten- und Richtungstreue:** Die Antwort spricht alle tragenden Begriffe aus.
- ✅ **Bekannte Alltagsreibungen:** Interne IDs und CLI-Anweisungen bleiben aus dem Dialog.
- ✅ **Nichtwissen und Unsicherheit:** Die Definition ist beantwortet.
- ✅ **Datensparsamkeit:** Kein synthetischer Dialogrohtext gelangt ins Ledger.

**Menschliche Prüffrage:** Erklärt GENUS den Begriff direkt, klar und ohne Lexikon- oder CLI-Gefühl?

Status: `accepted` · Fall `94316ce8d810` · Antwort `74bd178ac90f`

<details>
<summary>Bewertungsvorlage mit vollständigen Hashes</summary>

```json
{
  "case_id": "02-definition-hund",
  "case_fingerprint": "94316ce8d8102e5a0dd5a1648c1887f131abb53310fea76392f8476e3503778d",
  "response_sha256": "74bd178ac90f07fc23d02e2ab656f538db29585a0c21765400c0f91ef5b2b252",
  "ton": "traegt",
  "nutzen": "traegt",
  "reviewer": "ronny",
  "reviewed_at": "YYYY-MM-DDTHH:MM:SS+02:00",
  "note": ""
}
```

</details>

Wertung von `ronny`: Ton `traegt`, Nutzen `traegt`. ok

### 03-definition-schwach · Schwach belegte Bedeutung

Eine Modellbrücke darf ihre geringe Sicherheit auch in kurzer Form nie verstecken.

**Zug 1 · Frage**

> Was ist Blub?

**Zug 1 · GENUS**

```text
»Blub« bedeutet hier: ein kaum belegter Testbegriff. Bei dieser Bedeutung bin ich noch vorsichtig: Sie ist erst schwach belegt.
```

Struktur: `outcome=answered` · `readings=['definition']` · `anchor=Was ist Blub?`

**Automatische Verträge**

- ✅ **Fakten- und Richtungstreue:** Der schwache Claim bleibt strukturell greifbar.
- ✅ **Nichtwissen und Unsicherheit:** Unsicherheit wird unmissverständlich ausgesprochen.
- ✅ **Nichtwissen und Unsicherheit:** Unsichere Antwort ist nicht mit Nichtverstehen vermischt.
- ✅ **Datensparsamkeit:** Kein synthetischer Dialogrohtext gelangt ins Ledger.

**Menschliche Prüffrage:** Ist die Unsicherheit klar, ohne dass die Antwort defensiv oder mechanisch klingt?

Status: `accepted` · Fall `7a5e0e0d0a4e` · Antwort `d9d788bdfab4`

<details>
<summary>Bewertungsvorlage mit vollständigen Hashes</summary>

```json
{
  "case_id": "03-definition-schwach",
  "case_fingerprint": "7a5e0e0d0a4e20a5185ec5a2d03d407d3c2497ea928fe7915748bab05060a6e4",
  "response_sha256": "d9d788bdfab43e824794f7e3def0def859d58ff251b5f79da31ec7d5c3cfd6f5",
  "ton": "traegt",
  "nutzen": "traegt",
  "reviewer": "ronny",
  "reviewed_at": "YYYY-MM-DDTHH:MM:SS+02:00",
  "note": ""
}
```

</details>

Wertung von `ronny`: Ton `traegt`, Nutzen `traegt`. ok

### 04-definition-korroboriert · Unabhängig bestätigte Bedeutung

Zwei unabhängige Quellen sollen als Korroboration und nicht als Doppelzählung erscheinen.

**Zug 1 · Frage**

> Was ist Blub?

**Zug 1 · GENUS**

```text
»Blub« bedeutet hier: ein gemeinsam belegter Testbegriff. Diese Bedeutung ist mehrfach unabhängig belegt.
```

Struktur: `outcome=answered` · `readings=['definition']` · `anchor=Was ist Blub?`

**Automatische Verträge**

- ✅ **Herkunft und Nachvollziehbarkeit:** Beide unabhängigen Quellen stehen am Claim.
- ✅ **Herkunft und Nachvollziehbarkeit:** Die Korroboration wird verständlich benannt.
- ✅ **Nichtwissen und Unsicherheit:** Die Bedeutung ist beantwortet.
- ✅ **Datensparsamkeit:** Kein synthetischer Dialogrohtext gelangt ins Ledger.

**Menschliche Prüffrage:** Wirkt der Vertrauenshinweis hilfreich oder unterbricht er den natürlichen Fluss?

Status: `accepted` · Fall `6de03f424a0b` · Antwort `eb8d42e5a8d3`

<details>
<summary>Bewertungsvorlage mit vollständigen Hashes</summary>

```json
{
  "case_id": "04-definition-korroboriert",
  "case_fingerprint": "6de03f424a0b148e4dd4c73874cc0a494e65899f41122cae8438c90324257945",
  "response_sha256": "eb8d42e5a8d3254d8c0cf29436d2dd1244f1fa9860b0fb86da71b87345d0a341",
  "ton": "traegt",
  "nutzen": "traegt",
  "reviewer": "ronny",
  "reviewed_at": "YYYY-MM-DDTHH:MM:SS+02:00",
  "note": ""
}
```

</details>

Wertung von `ronny`: Ton `traegt`, Nutzen `traegt`. ok

### 05-beziehung-direkt · Direkte gerichtete Beziehung

Subjekt, Objekt und Richtung dürfen in einer natürlichen Kurzantwort nie kippen.

**Zug 1 · Frage**

> Ist ein Hund ein Haustier?

**Zug 1 · GENUS**

```text
Ja — »Hund« zählt zu »Haustier«.
```

Struktur: `outcome=answered` · `readings=['beziehung']` · `anchor=Ist ein Hund ein Haustier?`

**Automatische Verträge**

- ✅ **Fakten- und Richtungstreue:** Die gerichtete Kante ist ein Claim.
- ✅ **Fakten- und Richtungstreue:** Der unveränderliche Richtungskern steht in der Antwort.
- ✅ **Fakten- und Richtungstreue:** Subjekt steht vor Objekt.
- ✅ **Bekannte Alltagsreibungen:** Die direkte Antwort trägt keinen ungefragten Auditvortrag.
- ✅ **Nichtwissen und Unsicherheit:** Die bekannte Verbindung ist beantwortet.
- ✅ **Datensparsamkeit:** Kein synthetischer Dialogrohtext gelangt ins Ledger.

**Menschliche Prüffrage:** Ist die Antwort so direkt, wie du sie in einem echten Gespräch erwartest?

Status: `review_pending` · Fall `687e758e29e4` · Antwort `ab09b8f189b1`

<details>
<summary>Bewertungsvorlage mit vollständigen Hashes</summary>

```json
{
  "case_id": "05-beziehung-direkt",
  "case_fingerprint": "687e758e29e4d70bc98cb644185640e75b24cdfe9bc122faa19fb308a4172d62",
  "response_sha256": "ab09b8f189b10b0064e36eeaad7e7d49af9b5406a359327ed9d89448e1a7ce51",
  "ton": "traegt",
  "nutzen": "traegt",
  "reviewer": "ronny",
  "reviewed_at": "YYYY-MM-DDTHH:MM:SS+02:00",
  "note": ""
}
```

</details>

### 06-beziehung-transitiv · Mehrstufige Herleitung

Eine transitive Antwort muss den belegten Zwischenweg bewahren.

**Zug 1 · Frage**

> Ist ein Hund ein Säugetier?

**Zug 1 · GENUS**

```text
Ja, klar — »Hund« zählt zu »Säugetier«. Der Weg dahin: »Hund« → »Haustier« → »Säugetier«.
```

Struktur: `outcome=answered` · `readings=['beziehung']` · `anchor=Ist ein Hund ein Säugetier?`

**Automatische Verträge**

- ✅ **Fakten- und Richtungstreue:** Die abgeleitete Zielbeziehung bleibt explizit.
- ✅ **Fakten- und Richtungstreue:** Die vollständige Kette erscheint sichtbar in der Antwort.
- ✅ **Herkunft und Nachvollziehbarkeit:** Die Herleitung trägt ihre Quelle.
- ✅ **Bekannte Alltagsreibungen:** Der Gesprächspfad zeigt Begriffe statt interner IDs oder Auditjargon.
- ✅ **Nichtwissen und Unsicherheit:** Die herleitbare Beziehung ist beantwortet.
- ✅ **Datensparsamkeit:** Kein synthetischer Dialogrohtext gelangt ins Ledger.

**Menschliche Prüffrage:** Ist der sichtbare Weg hilfreich, oder sollte GENUS ihn erst auf Nachfrage zeigen?

Status: `review_pending` · Fall `fa7a6a41ee8b` · Antwort `92e735fcbb4e`

<details>
<summary>Bewertungsvorlage mit vollständigen Hashes</summary>

```json
{
  "case_id": "06-beziehung-transitiv",
  "case_fingerprint": "fa7a6a41ee8be34874dccf4b2b4ca2bafda89d407db6d73a892ac01c6a544d74",
  "response_sha256": "92e735fcbb4e19ed647144e2e1b0c191c8bad44690b7cbc9a869a42a96dbce96",
  "ton": "traegt",
  "nutzen": "traegt",
  "reviewer": "ronny",
  "reviewed_at": "YYYY-MM-DDTHH:MM:SS+02:00",
  "note": ""
}
```

</details>

### 07-beziehung-offen · Offene Welt statt falsches Nein

Eine fehlende Kante ist Nichtwissen und niemals ein negativer Fakt.

**Zug 1 · Frage**

> Ist ein Hund ein Reptil?

**Zug 1 · GENUS**

```text
Eine is_a-Verbindung von »Hund« zu »Reptil« finde ich derzeit nicht. Das heißt: unbekannt, nicht widerlegt.
```

Struktur: `outcome=understood_unknown` · `readings=['beziehung']` · `anchor=Ist ein Hund ein Reptil?`

**Automatische Verträge**

- ✅ **Nichtwissen und Unsicherheit:** Der Draft unterscheidet Nichtwissen von einer Antwort.
- ✅ **Nichtwissen und Unsicherheit:** Aus einem fehlenden Pfad entsteht kein negativer Claim.
- ✅ **Nichtwissen und Unsicherheit:** Die offene Welt wird in Alltagssprache erklärt.
- ✅ **Fakten- und Richtungstreue:** Die Antwort behauptet keine Widerlegung.
- ✅ **Nichtwissen und Unsicherheit:** Das Outcome bleibt ehrlich offen.
- ✅ **Datensparsamkeit:** Kein synthetischer Dialogrohtext gelangt ins Ledger.

**Menschliche Prüffrage:** Ist diese Enthaltung klar genug, ohne ausweichend zu wirken?

Status: `review_pending` · Fall `0b780c9dc055` · Antwort `3611007a75b0`

<details>
<summary>Bewertungsvorlage mit vollständigen Hashes</summary>

```json
{
  "case_id": "07-beziehung-offen",
  "case_fingerprint": "0b780c9dc0557629ceefec408ba0ffddfa55ef380dcc4e42eb331fc7bea3ef35",
  "response_sha256": "3611007a75b0136b62dec2ed11b283696583045c54ae38a7a7d0c1745a9d42c4",
  "ton": "traegt",
  "nutzen": "traegt",
  "reviewer": "ronny",
  "reviewed_at": "YYYY-MM-DDTHH:MM:SS+02:00",
  "note": ""
}
```

</details>

### 08-deuter-leer · Ehrliches Nichtverstehen

Ein gelaufener Deuter ohne Lesart darf nicht in einen gierigen Wortfund ausweichen.

**Zug 1 · Frage**

> Okay prima, frobniziere das mal.

**Zug 1 · GENUS**

```text
Das habe ich nicht sicher verstanden. Sag mir bitte kurz, worum es geht und was du von mir brauchst.
```

Struktur: `outcome=fallback` · `readings=[]` · `anchor=Okay prima, frobniziere das mal.`

**Automatische Verträge**

- ✅ **Nichtwissen und Unsicherheit:** Der leere Deuter-Lauf endet im Fallback.
- ✅ **Nichtwissen und Unsicherheit:** GENUS benennt das Nichtverstehen und fragt nach Ziel und Kontext.
- ✅ **Fakten- und Richtungstreue:** Es wird kein zufällig bekanntes Wort erklärt.
- ✅ **Datensparsamkeit:** Kein synthetischer Dialogrohtext gelangt ins Ledger.

**Menschliche Prüffrage:** Hilft die Rückfrage beim Weitermachen, oder bleibt sie zu flach?

Status: `review_pending` · Fall `bd580b0a5eae` · Antwort `091e67d91c5f`

<details>
<summary>Bewertungsvorlage mit vollständigen Hashes</summary>

```json
{
  "case_id": "08-deuter-leer",
  "case_fingerprint": "bd580b0a5eae856747b107f52d0fcff6588f32894c46e890a3247085251fb1f8",
  "response_sha256": "091e67d91c5fbf0d44a954155bdc7e9c126dc4755baed8a7c7f888d22bbb8817",
  "ton": "traegt",
  "nutzen": "traegt",
  "reviewer": "ronny",
  "reviewed_at": "YYYY-MM-DDTHH:MM:SS+02:00",
  "note": ""
}
```

</details>

### 09-pflichtslot-fehlt · Unvollständige Beziehung

Eine erkannte Beziehung ohne Ziel darf keine Kante erfinden.

**Zug 1 · Frage**

> Ist Hund?

**Zug 1 · GENUS**

```text
Ich habe verstanden, dass es um eine Beziehung mit »Hund« geht, aber mir fehlt das Ziel. Wozu möchtest du »Hund« in Beziehung setzen?
```

Struktur: `outcome=invalid_slots` · `readings=['beziehung']` · `anchor=Ist Hund?`

**Automatische Verträge**

- ✅ **Nichtwissen und Unsicherheit:** Der fehlende Pflichtslot bleibt sichtbar.
- ✅ **Modelltransparenz:** Die erkannte Absicht geht nicht verloren.
- ✅ **Dialoganschluss:** Die Rückfrage benennt konkret den fehlenden Teil.
- ✅ **Fakten- und Richtungstreue:** GENUS vervollständigt die Beziehung nicht aus eigenem Antrieb.
- ✅ **Datensparsamkeit:** Kein synthetischer Dialogrohtext gelangt ins Ledger.

**Menschliche Prüffrage:** Führt die Antwort konkret genug zu einer besseren Frage zurück?

Status: `review_pending` · Fall `831582ccf4e9` · Antwort `a62b0b48ccaf`

<details>
<summary>Bewertungsvorlage mit vollständigen Hashes</summary>

```json
{
  "case_id": "09-pflichtslot-fehlt",
  "case_fingerprint": "831582ccf4e9ec93fbc9f1a9260dad787b50ce5f790044cdfd31a636b33ccb85",
  "response_sha256": "a62b0b48ccaf913ced40d585845301093cf6355230c837c82703e515192d65c8",
  "ton": "traegt",
  "nutzen": "traegt",
  "reviewer": "ronny",
  "reviewed_at": "YYYY-MM-DDTHH:MM:SS+02:00",
  "note": ""
}
```

</details>

### 10-freie-definition · Freie Formulierung, graphgeprüft

Eine Modell-Lesart darf nur zu graphbelegtem Inhalt führen und wird genau einmal offengelegt.

**Zug 1 · Frage**

> Sag mal, was steckt eigentlich hinter wuffwuff?

**Zug 1 · GENUS**

```text
»Hund« bedeutet hier: ein Haustier, dessen Vorfahre der Wolf ist. Dabei zählt »Hund« zu »Haustier«. (Frage vom Sprachmodell gedeutet.)
```

Struktur: `outcome=answered` · `readings=['definition']` · `anchor=Sag mal, was steckt eigentlich hinter wuffwuff?`

**Automatische Verträge**

- ✅ **Fakten- und Richtungstreue:** Die freie Formulierung landet beim belegten Claim.
- ✅ **Modelltransparenz:** Der Draft kennt die Herkunft der Lesart.
- ✅ **Modelltransparenz:** Modellhilfe wird genau einmal, nicht geräuschvoll mehrfach offengelegt.
- ✅ **Nichtwissen und Unsicherheit:** Die belegte Definition ist beantwortet.
- ✅ **Datensparsamkeit:** Kein synthetischer Dialogrohtext gelangt ins Ledger.

**Menschliche Prüffrage:** Wirkt die Offenlegung passend dosiert, während die Antwort selbst natürlich bleibt?

Status: `review_pending` · Fall `aa252936364a` · Antwort `ed8ea16ffc00`

<details>
<summary>Bewertungsvorlage mit vollständigen Hashes</summary>

```json
{
  "case_id": "10-freie-definition",
  "case_fingerprint": "aa252936364ab5f23043384f8b108467ba56e588a81a673e3f87e1d660768eb6",
  "response_sha256": "ed8ea16ffc008078421578774864f6cb713bd76952cc985cf2a49d8977098734",
  "ton": "traegt",
  "nutzen": "traegt",
  "reviewer": "ronny",
  "reviewed_at": "YYYY-MM-DDTHH:MM:SS+02:00",
  "note": ""
}
```

</details>

### 11-empfehlung-noch-nicht · Verstandene, noch nicht beherrschte Bitte

Eine bekannte Absicht ohne Werkzeug wird benannt, nicht als Inhalt halluziniert.

**Zug 1 · Frage**

> Welches Haustier würde zu mir passen?

**Zug 1 · GENUS**

```text
Ich lese das als eine Bitte um Empfehlung — das kann ich noch nicht. Ich habe es mir als Lücke gemerkt.
```

Struktur: `outcome=understood_unknown` · `readings=['empfehlungsfrage']` · `anchor=Welches Haustier würde zu mir passen?`

**Automatische Verträge**

- ✅ **Nichtwissen und Unsicherheit:** Verstanden und noch nicht beherrscht bleibt eine eigene Kategorie.
- ✅ **Nichtwissen und Unsicherheit:** GENUS benennt Absicht und Grenze.
- ✅ **Fakten- und Richtungstreue:** Es wird keine Empfehlung erfunden.
- ✅ **Datensparsamkeit:** Kein synthetischer Dialogrohtext gelangt ins Ledger.

**Menschliche Prüffrage:** Ist die Grenze brauchbar formuliert und bietet sie einen sinnvollen nächsten Schritt?

Status: `review_pending` · Fall `75b0ba3c947a` · Antwort `4364c8ffbacf`

<details>
<summary>Bewertungsvorlage mit vollständigen Hashes</summary>

```json
{
  "case_id": "11-empfehlung-noch-nicht",
  "case_fingerprint": "75b0ba3c947a94cf96cd122fe63d862e579c189908badaad680be35caafe39ae",
  "response_sha256": "4364c8ffbacf692d5d90c1a4ac5b38f731a4a542d28e623706967b356622e1fe",
  "ton": "traegt",
  "nutzen": "traegt",
  "reviewer": "ronny",
  "reviewed_at": "YYYY-MM-DDTHH:MM:SS+02:00",
  "note": ""
}
```

</details>

### 12-warum-rueckbezug · Warum bleibt am Thema

Eine knappe Warum-Frage muss die vorige Beziehung mit Quelle und Vertrauen nachzeichnen.

**Zug 1 · Frage**

> Ist ein Hund ein Haustier?

**Zug 1 · GENUS**

```text
Ja — »Hund« zählt zu »Haustier«.
```

Struktur: `outcome=answered` · `readings=['beziehung']` · `anchor=Ist ein Hund ein Haustier?`

**Zug 2 · Frage**

> warum?

**Zug 2 · GENUS**

```text
Die Herleitung von »Hund« zu »Haustier«:
  Hund@de —expresses→ Q144 (Hund)   ← wikidata (Vertrauen 0.50)
  Q144 (Hund) —is_a→ Q1001 (Haustier)   ← wikidata (Vertrauen 0.50)
```

Struktur: `outcome=answered` · `readings=[]` · `anchor=Ist ein Hund ein Haustier?`

Hinweis: Dieser Legacy-Zweig lieferte `outcome`, `gelesen` noch nicht explizit; die Probe normalisiert ihn sichtbar.

**Automatische Verträge**

- ✅ **Dialoganschluss:** Die Folgefrage bleibt am ursprünglichen Sachthema.
- ✅ **Herkunft und Nachvollziehbarkeit:** Die Belegspur wird auf Nachfrage sichtbar.
- ✅ **Nichtwissen und Unsicherheit:** Die Herkunftsfrage wird beantwortet.
- ✅ **Datensparsamkeit:** Kein synthetischer Dialogrohtext gelangt ins Ledger.

**Menschliche Prüffrage:** Ist die Herleitung lesbar genug, um Vertrauen zu schaffen statt nur Technik zu zeigen?

Status: `review_pending` · Fall `83d16a51cd0d` · Antwort `2baa42cb91a0`

<details>
<summary>Bewertungsvorlage mit vollständigen Hashes</summary>

```json
{
  "case_id": "12-warum-rueckbezug",
  "case_fingerprint": "83d16a51cd0d9522172aa95efd71b0e0322820616295196f055b8b8654a8bf07",
  "response_sha256": "2baa42cb91a09f8bed7878a5d4edb885bb59d7f898a6290e05b65dd3795fc271",
  "ton": "traegt",
  "nutzen": "traegt",
  "reviewer": "ronny",
  "reviewed_at": "YYYY-MM-DDTHH:MM:SS+02:00",
  "note": ""
}
```

</details>

### 13-anschluss-ja · Ein angebotenes Thema wird eingelöst

Ein knappes Ja beantwortet exakt das verifizierte Angebot und startet keine Endlosschleife.

**Zug 1 · Frage**

> Was ist ein Vulkan?

**Zug 1 · GENUS**

```text
»Vulkan« bedeutet hier: eine Öffnung in der Erdkruste. Wenn du magst, erkläre ich dir noch, was »Ausbruch« ist.
```

Struktur: `outcome=answered` · `readings=['definition']` · `anchor=Was ist ein Vulkan?`

**Zug 2 · Frage**

> ja

**Zug 2 · GENUS**

```text
Unter »Ausbruch« versteht GENUS: eine Entladung von Magma.
```

Struktur: `outcome=answered` · `readings=[]` · `anchor=Was ist Ausbruch?`

Hinweis: Dieser Legacy-Zweig lieferte `outcome` noch nicht explizit; die Probe normalisiert ihn sichtbar.

**Automatische Verträge**

- ✅ **Dialoganschluss:** Der erste Zug trägt sein echtes Angebot.
- ✅ **Dialoganschluss:** Das Angebot ist im ersten Zug sichtbar.
- ✅ **Dialoganschluss:** Das Ja wird auf das angebotene Thema aufgelöst.
- ✅ **Fakten- und Richtungstreue:** Die Einlösung nutzt nur die belegte Bedeutung.
- ✅ **Dialoganschluss:** Die Einlösung erzeugt keinen neuen Sog.
- ✅ **Datensparsamkeit:** Kein synthetischer Dialogrohtext gelangt ins Ledger.

**Menschliche Prüffrage:** Fühlt sich Angebot plus Einlösung wie ein zusammenhängendes Gespräch an?

Status: `review_pending` · Fall `feeccca09e86` · Antwort `628e9ee54bbd`

<details>
<summary>Bewertungsvorlage mit vollständigen Hashes</summary>

```json
{
  "case_id": "13-anschluss-ja",
  "case_fingerprint": "feeccca09e860a7c72e7d61e814a64e64b0e514866f36bc3ff704b5293643d59",
  "response_sha256": "628e9ee54bbd57daecf9d216321f2f04aafb478561c342723de672b13c4f1c57",
  "ton": "traegt",
  "nutzen": "traegt",
  "reviewer": "ronny",
  "reviewed_at": "YYYY-MM-DDTHH:MM:SS+02:00",
  "note": ""
}
```

</details>

### 14-von-vorhin · Rückbezug über eine Floskel hinweg

Ein Sachthema darf nach einem Gruß nicht aus dem kleinen Dialograhmen fallen.

**Zug 1 · Frage**

> Was ist ein Fahrrad?

**Zug 1 · GENUS**

```text
»Fahrrad« bedeutet hier: ein Zweirad zum Fahren.
```

Struktur: `outcome=answered` · `readings=['definition']` · `anchor=Was ist ein Fahrrad?`

**Zug 2 · Frage**

> Moin!

**Zug 2 · GENUS**

```text
Hallo! Schön, dass du da bist. Was beschäftigt dich gerade?
```

Struktur: `outcome=answered` · `readings=['gruss']` · `anchor=Moin!`

**Zug 3 · Frage**

> Was war das nochmal von vorhin?

**Zug 3 · GENUS**

```text
Unter »Fahrrad« versteht GENUS: ein Zweirad zum Fahren. (Bezogen auf deine frühere Frage „Was ist ein Fahrrad?“.)
```

Struktur: `outcome=answered` · `readings=[]` · `anchor=Was ist ein Fahrrad?`

Hinweis: Dieser Legacy-Zweig lieferte `outcome`, `gelesen` noch nicht explizit; die Probe normalisiert ihn sichtbar.

**Automatische Verträge**

- ✅ **Dialoganschluss:** Der Rückbezug findet das Sachthema wieder.
- ✅ **Dialoganschluss:** Antwort und sichtbarer Rückbezug passen zusammen.
- ✅ **Fakten- und Richtungstreue:** Die Floskel wird nicht zum Sachthema gemacht.
- ✅ **Datensparsamkeit:** Kein synthetischer Dialogrohtext gelangt ins Ledger.

**Menschliche Prüffrage:** Ist der Rückbezug hilfreich, ohne den Dialog mit Metatext zu überladen?

Status: `review_pending` · Fall `69ce15785a9f` · Antwort `bdf1ffaf60ee`

<details>
<summary>Bewertungsvorlage mit vollständigen Hashes</summary>

```json
{
  "case_id": "14-von-vorhin",
  "case_fingerprint": "69ce15785a9f13024a42553e660ec5e887f4a48cd2fbf58c666cbe14d8c5ba01",
  "response_sha256": "bdf1ffaf60ee6b7eb1328d254d59849786476714f6bbcb17a974b6a22bff9603",
  "ton": "traegt",
  "nutzen": "traegt",
  "reviewer": "ronny",
  "reviewed_at": "YYYY-MM-DDTHH:MM:SS+02:00",
  "note": ""
}
```

</details>

### 15-mehrsegment · Gruß, Frage und Dank in einer Nachricht

Mehrere Sprechhandlungen müssen gemeinsam aufgelöst und ruhig komponiert werden.

**Zug 1 · Frage**

> Hallo! Was ist ein Hund? Danke dir.

**Zug 1 · GENUS**

```text
Hallo! Schön, dass du da bist. »Hund« bedeutet hier: ein Haustier, dessen Vorfahre der Wolf ist. Dabei zählt »Hund« zu »Haustier«. (Frage vom Sprachmodell gedeutet.) Gern geschehen!
```

Struktur: `outcome=answered` · `readings=['gruss', 'definition', 'dank']` · `anchor=Hallo! Was ist ein Hund? Danke dir.`

**Automatische Verträge**

- ✅ **Mehrteilige Antworten:** Alle drei Lesarten bleiben erhalten.
- ✅ **Mehrteilige Antworten:** Jede Sprechhandlung trägt eine sichtbare Teilwirkung.
- ✅ **Bekannte Alltagsreibungen:** Der Gruß stellt keine Gegenfrage, wenn die Nachricht schon ein Anliegen enthält.
- ✅ **Modelltransparenz:** Der gemeinsame Modellhinweis erscheint höchstens einmal.
- ✅ **Nichtwissen und Unsicherheit:** Die gesamte Nachricht ist beantwortet.
- ✅ **Datensparsamkeit:** Kein synthetischer Dialogrohtext gelangt ins Ledger.

**Menschliche Prüffrage:** Liest sich die zusammengesetzte Antwort wie ein Zug statt wie drei Textbausteine?

Status: `review_pending` · Fall `272dd4ae28ed` · Antwort `354208b8a5e3`

<details>
<summary>Bewertungsvorlage mit vollständigen Hashes</summary>

```json
{
  "case_id": "15-mehrsegment",
  "case_fingerprint": "272dd4ae28ed3420a1531b80ce6ce43ba85d1d855e9d6ccd3eaee860067289e8",
  "response_sha256": "354208b8a5e300b86a2443e3c706be6f224940cbeecd6721b2074d5f76604fa0",
  "ton": "traegt",
  "nutzen": "traegt",
  "reviewer": "ronny",
  "reviewed_at": "YYYY-MM-DDTHH:MM:SS+02:00",
  "note": ""
}
```

</details>

### 16-mehrsegment-mit-luecke · Gruß plus unvollständige Frage

Eine freundliche Teilantwort darf die ungelöste Sachfrage nicht als Erfolg verdecken.

**Zug 1 · Frage**

> Hallo, ist Hund?

**Zug 1 · GENUS**

```text
Hallo! Schön, dass du da bist. Ich habe verstanden, dass es um eine Beziehung mit »Hund« geht, aber mir fehlt das Ziel. Wozu möchtest du »Hund« in Beziehung setzen?
```

Struktur: `outcome=invalid_slots` · `readings=['gruss', 'beziehung']` · `anchor=Hallo, ist Hund?`

**Automatische Verträge**

- ✅ **Mehrteilige Antworten:** Der lösbare soziale Teil bleibt erhalten.
- ✅ **Dialoganschluss:** Der offene Sachteil erhält eine konkrete Klärungsfrage.
- ✅ **Nichtwissen und Unsicherheit:** Die Sachlücke bestimmt konservativ das Gesamtoutcome.
- ✅ **Fakten- und Richtungstreue:** Die fehlende Beziehung wird nicht ergänzt.
- ✅ **Datensparsamkeit:** Kein synthetischer Dialogrohtext gelangt ins Ledger.

**Menschliche Prüffrage:** Macht GENUS deutlich genug, welcher Teil noch offen ist?

Status: `review_pending` · Fall `d59fca2ce0ce` · Antwort `780f2cbf3025`

<details>
<summary>Bewertungsvorlage mit vollständigen Hashes</summary>

```json
{
  "case_id": "16-mehrsegment-mit-luecke",
  "case_fingerprint": "d59fca2ce0cec5e4e3244a623379ed4a89bd866483c360d3360cb89792b0990a",
  "response_sha256": "780f2cbf30256e9bd0d4507e42dcbf7316c4ba26c0ad668d1a3edb76b6b8af02",
  "ton": "traegt",
  "nutzen": "traegt",
  "reviewer": "ronny",
  "reviewed_at": "YYYY-MM-DDTHH:MM:SS+02:00",
  "note": ""
}
```

</details>

### 17-enge-korrektur · Eine Lesart wird gezielt korrigiert

Die Korrektur bezieht sich auf die letzte strukturelle Lesart, nicht auf gespeicherten Rohtext.

**Zug 1 · Frage**

> Gehört so ein Wuff eigentlich zu Haustieren?

**Zug 1 · GENUS**

```text
Ja — »Hund« zählt zu »Haustier«. (Frage vom Sprachmodell gedeutet.)
```

Struktur: `outcome=answered` · `readings=['beziehung']` · `anchor=Gehört so ein Wuff eigentlich zu Haustieren?`

**Zug 2 · Frage**

> falsch verstanden: definition

**Zug 2 · GENUS**

```text
Danke für die Korrektur — ich hatte das als „beziehung“ gelesen. Den Fehlgriff habe ich mir gemerkt. Gemeint war „definition“ — auch das habe ich festgehalten.
```

Struktur: `outcome=answered` · `readings=[]` · `anchor=Gehört so ein Wuff eigentlich zu Haustieren?`

**Automatische Verträge**

- ✅ **Dialoganschluss:** Fehlgriff und gemeinte Lesart werden nachvollziehbar bestätigt.
- ✅ **Dialoganschluss:** Die Korrektur bleibt am korrigierten Zug verankert.
- ✅ **Nichtwissen und Unsicherheit:** Die enge Korrektur wurde angenommen.
- ✅ **Datensparsamkeit:** Kein synthetischer Dialogrohtext gelangt ins Ledger.

**Menschliche Prüffrage:** Fühlt sich die Korrekturbestätigung klar und nicht übertechnisch an?

Status: `review_pending` · Fall `cc42002a0679` · Antwort `a12a2e49dbf3`

<details>
<summary>Bewertungsvorlage mit vollständigen Hashes</summary>

```json
{
  "case_id": "17-enge-korrektur",
  "case_fingerprint": "cc42002a0679be1c0f2d317fef8d5862388f6e1387a70701d765f73cf26e2e3a",
  "response_sha256": "a12a2e49dbf34204cba08cac81cda0deda8f7319c81d40d67ba970ecac92b7e0",
  "ton": "traegt",
  "nutzen": "traegt",
  "reviewer": "ronny",
  "reviewed_at": "YYYY-MM-DDTHH:MM:SS+02:00",
  "note": ""
}
```

</details>

---

- Erzeugen: `genus alltagsprobe --markdown`
- Automatisches Gate: `genus alltagsprobe --contracts-only`
- Lesbare Einzelansicht: `genus alltagsprobe --details`
