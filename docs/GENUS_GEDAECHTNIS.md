# GENUS-Gedächtnis — das Konzept

**Nachricht rein → GENUS → Nachricht raus: was muss intern passieren?**
Ronnys Leitfragen (2026-07-03), die dieses Konzept beantwortet:

1. An welchen Stellen wird Erinnerung / Wissen in die Verarbeitung hineingegeben?
2. Wann wird aus Nachrichten neues Wissen / neue Erinnerung?
3. Wie werden Wissen und Erinnerung gespeichert — und gibt es einen Unterschied?
4. Wie sind Erinnerungen untereinander vernetzt? Wie ist Wissen vernetzt?
5. Wie greift GENUS darauf für die aktuelle Betrachtung zu?
6. Tagesrhythmus: behält GENUS einen Tag im Kontext und arbeitet ihn nachts in
   Erinnerungen bzw. Wissen ein?

Anlass: das Gespräch fühlt sich trotz aller Vermittlungs-Arbeit (Würfel, Deuter, Stimme)
inhaltlich dumm an, und als Nächstes soll gezielt Fachwissen aufgebaut werden. Bevor Wissen
eingefüllt wird, muss geklärt sein, wohin es fließt und wie es beim Antworten wieder
herauskommt — sonst füllen wir einen Speicher, den das Gespräch nie anfasst.

---

## 1 · Der Ist-Zustand, ehrlich

Was heute mit einer Telegram-Nachricht passiert, Station für Station:

| # | Station | Existiert? | Wo Wissen/Erinnerung einfließt |
|---|---------|-----------|-------------------------------|
| 1 | **Ankommen** (Membran, `telegram_bot.py`) | ✅ | Session-Zustand: NUR der letzte Zug (`last_question`, `last_answer`), im Prozess, weg beim Neustart |
| 2 | **Einordnen** (Zwicky-Würfel: Rituale → Muster → Deuter-Segmente) | ✅ | das Absichts-Raster selbst IST Wissen (Teilgraph `absicht:*`/`zelle:*`); das Blatt-Angebot an den Deuter kommt aus dem Graphen |
| 3 | **Erinnern / Abrufen** | ⚠️ rudimentär | nur `_notiz_bezug`: eine Notiz wird angehängt, wenn ein Wort ≥4 Zeichen wörtlich überschneidet — kein echter Abruf |
| 4 | **Lösen** (Zellen-Handler) | ✅ | die Handler lesen den Wissensgraphen (`relation_projection`, `infer_lexeme`) — die EINZIGE Stelle, an der Wissen substanziell einfließt |
| 5 | **Komponieren** (`_komponiere`) | ✅ v1 | — (reine Aneinanderreihung) |
| 6 | **Sprechen** (Stimme, Anker-geprüft) | ✅ | — (formuliert nur um) |
| 7 | **Merken** | ⚠️ zwei Pfade | „merke dir: …" (voll vertraut) und die `tatsache`-Zelle (gedeckelt) — beides landet als flacher Text unter `genus:notizen` |
| 8 | **Mitschreiben** (Tagespuffer) | ❌ | existiert nicht — nach dem Zug ist das Gespräch weg |
| 9 | **Konsolidieren** (nachts) | ❌ | existiert nicht |

**Die ehrlichen Lücken:**

- **Kein echter Abruf.** GENUS beantwortet jede Frage isoliert. Sein Wissen fließt nur ein,
  wenn die Frage *direkt* danach fragt („Was ist ein Hund?") — es bringt nie von sich aus
  Zusammenhänge, Erinnerungen oder Fachwissen in das Gespräch ein. Genau deshalb wirkt das
  Gespräch dumm, selbst wenn der Graph voll wäre.
- **Erinnerungen sind ein Stern, kein Netz.** Alle Notizen hängen an EINEM Knoten
  (`genus:notizen`), als bloßer Text, ohne Zeitanker, ohne Verbindung zu den Begriffen, die
  sie erwähnen. Zwei Notizen über Hunde wissen nichts voneinander und nichts vom
  Hund-Konzept im Graphen.
- **Arbeitsgedächtnis = 1 Zug.** „Kürzer!" funktioniert; „wie hieß das Tier, über das wir
  vor fünf Minuten sprachen?" ist unmöglich.
- **Kein Vergessen, keine Verdichtung.** Was gemerkt wird, bleibt roh und für immer; was
  nicht explizit gemerkt wird, ist sofort weg. Es gibt nichts dazwischen.

---

## 2 · Die wissenschaftliche Landkarte

Nicht Namedropping — jeder Anker unten erzwingt eine konkrete Designentscheidung.

**Tulving (1972): episodisches vs. semantisches Gedächtnis.**
*Episodisch* = an Zeit, Ort und Sprecher gebundene Ereignisse („Ronny erzählte mir am
3. Juli, dass er zwei Hunde hat"). *Semantisch* = zeitloses Allgemeinwissen („Hunde sind
Säugetiere"). → **Erinnerung und Wissen sind zwei verschiedene Formen** — GENUS braucht
beide, getrennt gespeichert, aber mit derselben Maschinerie (Relationen + Herkunft).

**Komplementäre Lernsysteme (McClelland, McNaughton & O'Reilly 1995).**
Das Gehirn hat ein *schnelles* System (Hippocampus: Einzelepisoden sofort speichern) und
ein *langsames* (Neokortex: verallgemeinertes Wissen, nur durch Wiederholung). Schlaf
überspielt vom schnellen ins langsame System (Systemkonsolidierung). → Das IST bereits
GENUS' Bauform: Notizen schnell + gedeckelt, der Graph langsam + korroboriert. Was fehlt,
ist **die Brücke: die nächtliche Konsolidierung.**

**Baddeley: Arbeitsgedächtnis ≠ Langzeitgedächtnis.**
Der laufende Gesprächskontext ist ein eigener, flüchtiger Speicher — kein Langzeitwissen.
→ Bestätigt GENUS' DNA-Regel **Ledger ≠ Memory**: die Session gehört in die Membran, nicht
in den Ledger. Sie darf aber deutlich länger sein als ein Zug.

**Aktivierungsausbreitung (Collins & Loftus 1975).**
Menschlicher Abruf läuft über gemeinsame Begriffe: „Hund" aktiviert Haustier, Wolf, die
Erinnerung an Nachbars Dackel. → GENUS' Abruf soll **deterministisch über den
Begriffsgraphen** laufen (Frage erwähnt Hund → aktiviere Hund-Knoten → finde angebundene
Episoden + Nachbarwissen). Kein Embedding-Index nötig, solange das Volumen klein ist —
und glasklar nachvollziehbar, warum etwas einfiel.

**Ebbinghaus: Vergessen ist eine Funktion, kein Fehler.**
Fast alles Erlebte wird vergessen; nur Wiederholtes/Bedeutsames bleibt. → Der Tagespuffer
**verfällt**. Nur was die Konsolidierung als merkwürdig erkennt, überlebt die Nacht.

**Vollständigkeit:** die Kognitionswissenschaft kennt drei Langzeit-Formen — episodisch,
semantisch, **prozedural** (Können). GENUS hat alle drei Formen bereits angelegt:
Notizen (episodisch, unfertig), Graph (semantisch, gut), Erfahrungen/Regel-Kalibrierungen
(`experience_log` — prozedural: was GENUS über sein eigenes Schließen gelernt hat). Das
Konzept muss also nichts erfinden, sondern die episodische Seite fertig bauen und die
Brücken ziehen.

---

## 3 · Erinnerung vs. Wissen in GENUS — die Unterscheidung

| | **Erinnerung (Episode)** | **Wissen (Graph)** |
|---|---|---|
| Zeitanker | JA — „am 3. Juli" gehört dazu | nein — zeitlos |
| Sprecher | JA — wer es sagte, gehört dazu | nur als Quelle/Herkunft |
| Wahrheitsanspruch | keiner — es WURDE gesagt, das ist der Fakt | korroborierbar, anfechtbar, Widerspruch → Inquiry |
| Einmaligkeit | jede Episode ist einzigartig | dieselbe Aussage von zwei Quellen = EIN Fakt, doppelt belegt |
| Vernetzung | über die **erwähnten Begriffe** | direkt (is_a, expresses, …) |
| Beispiel | „Ronny erwähnte, dass er zwei Hunde hat (3.7., Telegram)" | „Hund is_a Säugetier (wikidata, dbnary)" |

**Die Episodenform (Soll):** eine Erinnerung ist ein eigener Knoten mit genau vier Kanten —
keine weitere auf Vorrat (Merkmal-Disziplin: erst bei erkannter Notwendigkeit):

```
erinnerung:<id>  —inhalt→   "ich habe zwei Hunde"        (der Wortlaut der Klausel)
erinnerung:<id>  —von→      ronny                         (die Quelle, wie überall)
erinnerung:<id>  —am→       2026-07-03                    (der Zeitanker)
erinnerung:<id>  —erwähnt→  Hund@de                       (0..n Kanten zu Graph-Begriffen)
```

Damit sind Erinnerungen **durch das Wissen** vernetzt, nicht aneinander: zwei Episoden über
Hunde treffen sich am Knoten `Hund@de` — exakt wie beim Menschen. Direkte
Episode-zu-Episode-Kanten gibt es bewusst nicht, bis ein echter Bedarf sie erzwingt.

**Der Übergang (Semantisierung):** wiederholte, konsistente Episoden kondensieren zu
Wissen. Sagt Ronny dreimal über Wochen, er habe zwei Hunde, wird daraus ein gedeckelter
Fakt-Kandidat — und die BESTEHENDE Korroborations- und Inquiry-Maschinerie entscheidet, ob
er zum vollwertigen Wissen wird (ggf. per Rückfrage: „Du erwähnst öfter zwei Hunde — soll
ich das fest wissen?"). Kein neuer Mechanismus; der Lehrer-Loop bekommt nur eine neue
Zubringerstraße.

---

## 4 · Die Soll-Pipeline

```
Nachricht
  → (1) ANKOMMEN        Membran; Arbeitsgedächtnis = die bisherigen Züge der Session
  → (2) EINORDNEN       Zwicky-Würfel (existiert): Segmente × Zellen
  → (3) ERINNERN        NEU: erwähnte Begriffe aktivieren → passende Episoden (1 Hop)
                        + Nachbarwissen (is_a-Umgebung) in den Antwort-Kontext holen
  → (4) LÖSEN           Zellen-Handler auf dem Graphen (existiert)
  → (5) KOMPONIEREN     Antwort-Würfel (existiert als v1)
  → (6) SPRECHEN        Stimme, Anker-geprüft (existiert)
  → (7) MERKEN          explizit = voll · beiläufig (tatsache-Zelle) = gedeckelt
                        NEU: beides als Episode (vernetzt), nicht mehr als flacher Text
  → (8) MITSCHREIBEN    NEU: der Zug wandert in den Tagespuffer (Membran-Datei, verfällt)
Antwort raus

nachts:
  → (9) KONSOLIDIEREN   NEU: der Scan liest den Tagespuffer und produziert:
                        · Episoden-Kandidaten (gedeckelt) für Wiederkehrendes
                        · Wissens-Kandidaten → Korroboration oder Rückfrage (Inquiry)
                        · Kennzahlen: Treffer-Quote je Zelle aus Folge-Signalen
                          („warum?" direkt nach einer Antwort = Beleg, dass der Weg
                          hätte dabei sein sollen — die offene Antwort-Würfel-Kennzahl)
                        · VERGESSEN: der Puffer wird geleert
```

Antwort auf Leitfrage 1 (wo fließt Wissen ein): an **drei** Stellen — beim Einordnen (das
Raster ist Wissen), beim Erinnern (neu: Episoden + Nachbarwissen), beim Lösen (die Handler).
Antwort auf Leitfrage 2 (wann wird aus Nachrichten Wissen/Erinnerung): an **drei** Stellen
mit klaren Vertrauensstufen — sofort explizit (voll), sofort beiläufig (gedeckelt), nachts
konsolidiert (gedeckelt oder als Rückfrage). Nie als Rohtext in den Ledger.

---

## 5 · Die drei Speicher

| Speicher | Ort | Lebensdauer | Form | Analogie |
|---|---|---|---|---|
| **Arbeitsgedächtnis** | Membran (`telegram_bot.py`, in-process) | Session / Tag | Liste der Züge (Frage, Antwort, Zelle) | Baddeley |
| **Tagespuffer** | Membran-Datei (`~/.genus/chat_tag.jsonl`), rotierend | bis zur nächtlichen Konsolidierung, dann geleert | Züge als Zeilen | Hippocampus |
| **Episoden + Wissen** | Ledger (event-sourced, für immer, provenanced) | dauerhaft | Relationen wie alles andere | Neokortex |

Der Tagespuffer ist die eine echte Neuerung mit einer Grundsatzfrage: Rohtext des Gesprächs
liegt dann bis zur Nacht in einer lokalen Datei auf dem Pi. **Ledger ≠ Memory bleibt
gewahrt** (der Ledger sieht nie Rohtext), aber die Membran hält ihn vorübergehend — wie der
Lerner seine `learn.gap_attempts`-Datei hält. Alles lokal, nichts verlässt den Pi, die Datei
verfällt. Ob das so sein darf, ist Ronnys Entscheidung (siehe §8).

**Abruf (Leitfrage 5):** deterministisch, zweistufig, glasklar erklärbar:
1. Begriffe der Frage im Graphen auflösen (das kann GENUS schon: `_last_known_word` & Co.).
2. Von diesen Knoten: angebundene Episoden (`erwähnt`-Kanten rückwärts, 1 Hop) und
   Nachbarwissen (direkte is_a-Umgebung) einsammeln, nach Nähe und Frische ordnen, die
   besten 1–3 in den Antwort-Kontext geben.
Ein Embedding-Index als ZWEITER Abrufpfad („bedeutungsähnlich, nicht wortgleich") bleibt
benannt, aber ungebaut, bis das Episoden-Volumen ihn rechtfertigt (Selbst-Kalibrierung:
erst bei echtem Bedarf).

---

## 6 · Der Tagesrhythmus (Leitfrage 6, direkt beantwortet)

**Nein** — GENUS soll nicht den ganzen Tag „im Kontext" eines Sprachmodells halten. Das
wäre beim 1,5B-Modell (2k-Fenster) physisch unmöglich und wäre auch mit einem großen Modell
architektonisch falsch: Kontextfenster sind flüchtig und ungeprüft — genau das Gegenteil
dessen, was GENUS ausmacht.

**Stattdessen, dem Gehirn nachempfunden:**
- **Tagsüber**: Arbeitsgedächtnis (die Session, strukturiert, Membran) + sofortiges Merken
  der zwei expliziten Pfade + Mitschreiben in den Tagespuffer.
- **Nachts**: die Konsolidierung (ein Scan-Lauf, wie der Lerner nachts lernt) liest den
  Puffer EINMAL, destilliert Episoden-/Wissens-Kandidaten und Kennzahlen heraus — und
  vergisst den Rest. Der Deuter darf dabei offline helfen (Muster im Tag erkennen), aber
  alles, was er vorschlägt, bleibt gedeckelt oder wird zur Rückfrage — dieselbe Leine wie
  live.
- **Morgens**: GENUS kann von sich aus einen Satz sagen können („Mir ist von gestern
  hängengeblieben: … — stimmt das so?") — der Lehrer-Loop als Frühstücksgespräch. Das ist
  der erste legitime PUSH-Anlass für die bisher bewusst rein reaktive Membran, und bleibt
  eine eigene Entscheidung.

Die Infrastruktur dafür existiert vollständig: Watchdog/Timer, Scan-Muster, Inquiries,
Lehrer-Loop, Korroboration. Die Nacht-Konsolidierung ist eine neue Zubringerstraße in
bestehende Maschinen, kein neues Organ.

---

## 7 · Leitplanken (DNA-Abgleich)

- **Ledger ≠ Memory, präzisiert:** Rohtext nur in der Membran (flüchtig, verfällt);
  in den Ledger nur Struktur (Episoden mit ihren vier Kanten, Kennzahlen, Kandidaten).
- **Modelle bleiben am Rand:** Deuter/Stimme unverändert; die Nacht-Konsolidierung nutzt
  den Deuter als Leser, nie als Autor — jeder Vorschlag gedeckelt (`model:*`) oder Inquiry.
- **Kein Merkmal auf Vorrat:** die Episode hat vier Kanten. Ort, Stimmung, Themenfäden —
  alles erst, wenn eine konkrete Fähigkeit ohne sie nachweislich nicht baubar ist.
- **Föderation:** ein Kern pro Person; „von → ronny" ist die bestehende Quellen-Semantik,
  kein Multi-User-Feature.
- **Privatsphäre:** alles auf dem Pi; der Tagespuffer ist lokal und selbstlöschend.

---

## 8 · Der Weg (Scheiben) und die offenen Entscheidungen

Jede Scheibe klein, einzeln testbar, einzeln live nachweisbar:

1. **Episoden statt flacher Notizen** — neue Form (vier Kanten), Migration der bestehenden
   `genus:notizen` (sie bekommen `am` = Migrationsdatum und `erwähnt`-Kanten, soweit
   Begriffe auflösbar), `merke dir` + `tatsache`-Zelle schreiben ab sofort Episoden.
2. **Abruf über den Graphen** — ersetzt die Wort-Überschneidung; Episoden UND Nachbarwissen
   fließen in die Antwort ein. *Ab hier fühlt sich das Gespräch zum ersten Mal „wissend" an,
   und ab hier lohnt sich das Fachwissen-Einfüllen richtig.*
3. **Arbeitsgedächtnis über mehrere Züge** — Session-Liste statt Ein-Zug-Paar; „das Tier von
   vorhin" wird auflösbar.
4. **Tagespuffer + Nacht-Konsolidierung** — inkl. Vergessen und der Treffer-Quote-Kennzahl.
5. **Semantisierung** — wiederkehrende Episoden → Wissens-Kandidaten → Korroboration/Inquiry.

Das Fachwissen-Ziel (Ronnys Wahl von heute) dockt am Wissensgraphen an (Lerner gezielt auf
ein Gebiet ansetzen) und ist von diesen Scheiben unabhängig startbar — aber erst Scheibe 2
macht es im Gespräch ERLEBBAR. Empfehlung daher: ① und ② zuerst, dann Fachwissen einfüllen,
dann ③–⑤.

**Entschieden (Ronny, 2026-07-03):**
- **(A) Tagespuffer: JA** — Roh-Gesprächstext darf bis zur Nacht in der lokalen,
  selbstlöschenden Membran-Datei liegen; der Ledger sieht nie Rohtext.
- **(B) Konsolidierungs-Stil: still merken, morgens berichten** — nächtliche Funde werden
  gedeckelt gespeichert (wie tatsache-Notizen); GENUS erzählt morgens, was hängengeblieben
  ist, und Ronny korrigiert bei Bedarf (Rücknahme = bestehende retract-Maschinerie).
- **(C) Morgen-Push: JA, genau eine Nachricht** — der erste bewusste Push-Anlass für die
  bisher rein reaktive Membran; nur wenn die Nacht tatsächlich etwas ergab.
