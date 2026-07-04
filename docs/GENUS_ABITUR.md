# GENUS und das Abitur

## 1 · Das Ziel, in Ronnys eigenen Worten (2026-07-03)

Nach dem Fachwissen-Fahrplan aus `docs/GENUS_GEDAECHTNIS.md` (Punkt 3) begann ich einen
Fachwortschatz zu bauen — Ronny stoppte das sofort:

> "ich meine nicht die Wörter kennen. GENUS soll die Aufgaben einer Abiturprüfung schaffen.
> also inhaltlich und selbstverständlich auch sprachlich."

Und, davor, allgemeiner:

> "GENUS muss genau das lernen, sich Dinge zu beschaffen, die es braucht, und dann so zu
> nutzen, wie es sie braucht — nach einem zielgerichteten Plan, den es selbst hat (und sich
> sicher ist) oder ich mit ihm entwickle. Bring GENUS dazu, das Abitur zu bestehen. Das ist
> jetzt das nächste Ziel."

**Der Unterschied ist entscheidend:** eine Fachliste (Begriffe kennen: "was ist eine
Ableitung?") ist eine Wissensfrage — genau das, was der Begleiter schon kann. "Bestimme die
Ableitung von f(x) = 3x² + 2x" ist keine Wissensfrage, sondern eine RECHNUNG. Wortschatz allein
löst sie nicht.

## 2 · Warum das eine echte neue Fähigkeitsklasse ist

Mathematik ist exakt — ein Sprachmodell ist es nicht. LLMs rechnen nachweislich unzuverlässig
(Vorzeichenfehler, falsch angewandte Regeln, überzeugend falsche Ergebnisse). Das ist kein
Vorwand, das Deuter/Stimme-Prinzip aufzuweichen, sondern seine konsequente Anwendung auf ein
Gebiet, das GENAU SO funktioniert: eine Ableitung hat ein einziges richtiges Ergebnis, das man
nachrechnen kann — keine Quelle, der man vertrauen muss, sondern eine Berechnung, die man
PRÜFEN kann. Deshalb rechnet `genus/mathematik.py` über **sympy**, eine echte Computer-Algebra-
Bibliothek: deterministisch, exakt, jeder Schritt reproduzierbar. Das ist GENUS' **erste
externe Kern-Abhängigkeit** überhaupt (bisher nur click+psutil) — bewusst gewählt, von Ronny
per AskUserQuestion bestätigt, nicht leichtfertig eingeführt.

Rand/Kern-Aufteilung wie überall sonst im Begleiter:

| Schritt | Wer | Wie |
|---|---|---|
| **Parsen** der Aufgabenstellung | Rand (Muster, wie relate/common/gender_question) | feste, deterministische Formulierungen — bisher kein Deuter nötig |
| **Rechnen** | Kern (`genus/mathematik.py`) | exakt über sympy, nie geraten |
| **Formulieren** | Rand (Template, aktuell OHNE Stimme) | deutsche Schulnotation (f'(x) = …) |
| **Prüfen** | noch nicht gebaut | Selbsttest gegen echte, gelöste Abitur-Aufgaben |

**Warum die Stimme hier NICHT mitspricht:** ein Formel-Ergebnis darf nie umformuliert werden
(dieselbe Korruptionsklasse wie "Kernobst"→"Kernaubere", nur mit höherem Schaden — eine falsche
Zahl ist schlimmer als ein falsches Wort). Beim Bauen der ersten Rechenzelle fiel auf, dass die
Muster-Zellen (`beziehung`/`vergleich`/`grammatik`) bislang UNGEPRÜFT durch die Stimme liefen —
`_STIMME_GEEIGNET` galt nur für den Deuter-Pfad, nie für den Muster-Pfad. Unsichtbar, weil alle
drei bisherigen Muster-Zellen zufällig geeignet waren. Jetzt prüft der Muster-Pfad dieselbe
Menge wie der Deuter-Pfad — ein Fund am Rande, der die neue Rechen-Zelle sofort aufdeckte.

## 3 · Zwei echte Rechenfehler, durch Testen gefangen (nicht geraten)

1. **"e" ist keine Variable.** sympy liest `e` ohne explizite Bindung als freies Symbol, nicht
   als Eulersche Zahl — `d/dx(e^x)` kam als `e^x·log(e)` heraus statt `e^x`. Gefixt durch
   explizite Bindung im Parser (außer die erfragte Variable heißt selbst "e").
2. **Sympys implizite Multiplikation ist zu großzügig.** Ein Buchstaben-Wirrwarr wie "das ist
   kein term" wurde klaglos als Produkt einzelner Symbole (d·a·s·i·s·t·…) geparst — ein
   plausibel aussehendes FALSCHES Ergebnis statt eines ehrlichen Fehlers. Gefixt mit einer
   Vorprüfung: jede alphabetische Zeichenkette im Term muss die erfragte Variable oder ein
   bekannter Funktions-/Konstantenname sein, sonst wird abgelehnt, BEVOR sympy gefragt wird.

## 4 · Stand (2026-07-03)

**Geliefert:**
- `genus/mathematik.py`: `ableitung()` (beliebige Ordnung, Polynome/Exponential-/Winkel-
  funktionen), `extremstellen()` (kritische Punkte über f'=0, klassifiziert über f'', ehrlich
  "unklar", wenn der Test selbst nichts hergibt — z. B. x³/x⁴ bei 0), `stammfunktion()`
  (unbestimmtes Integral inkl. "+ C"), `integral()` (bestimmtes Integral zwischen zwei Grenzen,
  auch symbolische Grenzen wie "pi").
- `companion.py`: vier neue, selbst-prüfende Muster-Zellen ("berechnen") für feste
  Formulierungen ("Bestimme die Ableitung von f(x) = …", "Leite f(x) = … ab", "Bestimme die
  Extremstellen von f(x) = …", "Bestimme eine Stammfunktion von f(x) = …", "Berechne das
  Integral von f(x) = … in den Grenzen von a bis b" / "… zwischen a und b").
- `genus ableitung/extremstellen/stammfunktion/integral` als CLI-Befehle.
- **Ein dritter Rechenfehler gefangen (nach den zwei aus Abschnitt 3):** `sympy.simplify()`
  faktorisiert ein Polynom manchmal um (z. B. `4x³+12x²+8x` → `4x(x²+3x+2)`) — mathematisch
  gleich, aber nicht die erwartete Schul-Normalform. `ableitung()`/`stammfunktion()` nutzen
  jetzt `sympy.expand()`, das live geprüft immer die ausmultiplizierte Form liefert.
- `deploy/fachwissen_abitur_mathematik.txt`: ein Fachwortschatz aus der echten Quelle (KMK,
  *Bildungsstandards Mathematik für die Allgemeine Hochschulreife*, 2012) — bleibt als
  ergänzende SPRACHLICHE Schicht bestehen (Ronny: "auch sprachlich"), ist aber nicht mehr der
  Kern des Ziels. Lernt über `deploy/pi_learn.sh`s neue `learn_fach`-Priorität (vor der
  allgemeinen Breite).

**Bewusst benannt, nicht gebaut:**
- **Selbsttest gegen echte, bereits gelöste Abitur-Aufgaben** — macht "besteht" erst messbar,
  statt nur behauptet. Reusable: derselbe predict→self-test→score-Mechanismus wie
  `genus/learning.py` beim Wetter, hier gegen bekannte richtige Lösungen statt gegen die
  nächste Beobachtung. Braucht eine echte Quelle für Aufgaben+Lösungen (variiert je Bundesland).
- **Weitere Aufgabenarten**: der reine Flächeninhalt (Betrag, braucht vorher die Nullstellen im
  Intervall — anders als das VORZEICHENBEHAFTETE bestimmte Integral, das schon gebaut ist),
  Vektorrechnung/Analytische Geometrie, Stochastik. Erweiterung der Kurvendiskussion um
  Wendepunkte + Monotonie (die Rezept-Form trägt das: zwei weitere Kern-Schritte registrieren,
  zwei Zeilen im Rezept).
- **GEBAUT (2026-07-04): die Kurvendiskussion — das erste echte REZEPT.** Komponiert aus drei
  registrierten Kern-Schritten (Nullstellen → Extremstellen → Grenzverhalten), die Komposition
  ist DATEN (`rezept`-Feld im Werkzeug), die Ausführung der eine generische Kern-Mechanismus
  (`werkzeug.rezept_implementierung`); `pruefen()` verweigert ein Rezept, das auf
  Unregistriertes zeigt. Neue Kern-Schritte `mathematik.nullstellen` und
  `mathematik.verhalten_unendlich` (sin(x) → ehrlich „unbestimmt", nie geraten). Muster-Zelle
  („Führe eine Kurvendiskussion für f(x) = … durch") + `genus kurvendiskussion` als CLI.
- **Freie Deuter-Lesart** für kreativ formulierte Rechenaufgaben — bisher nur die feste
  Musterformulierung erkannt; math. Ausdrücke sind für die Deuter-Subjekt/Objekt-Extraktion
  (auf einzelne Wörter ausgelegt) riskanter als für Begriffs-Fragen.
- **Explizite Ziel-Graph-Repräsentation** (`ziel:abitur -braucht-> fach:mathematik` als echtes,
  abfragbares Wissen) — noch nicht gebaut; heute lebt das Ziel nur in diesem Dokument und in
  Commit-Nachrichten, nicht im Graphen selbst.

## 5 · Umwidmung (2026-07-03, noch am selben Tag)

Ronnys eigene kritische Nachfrage („ist sowas wie Abi als Benchmark-Gate denn wirklich
sinnvoll?") hat dieses Ziel neu gefasst — und die Antwort war ehrlich: **nein, als Gate nicht.**

- **Kategorienfehler:** das Abitur misst Menschen-Schwächen (Gedächtnis, Zeitdruck,
  Flüchtigkeitsfehler). Den Rechenteil besteht sympy heute schon — ein bestandenes Abi würde
  fast nur unseren Aufgaben-Parser messen.
- **Goodhart's Law:** eine Messgröße, die zum Ziel wird, hört auf zu messen. „Besteht das Abi"
  als Gate erzwingt Erkennungs-Shims pro Klausur-Format — exakt die Hand-Aufzählung, die das
  Audit (docs/GENUS_AUDIT_2026_07.md) als Sackgasse benannt hat.
- **Begleiter-Wert ≠ Zeugnis:** niemand schätzt seinen Begleiter fürs Abitur; „Berufe/Studium"
  sind Credentialing-Strukturen für den menschlichen Arbeitsmarkt.

**Was bleibt:** `genus/mathematik.py` voll (wird eines der ersten Werkzeuge im Werkzeugkasten,
Inversion ②); die KMK-Standards als *Landkarte* eines Gebiets; ein kleiner held-out Korpus
echter Abi-Textaufgaben als **Thermometer** für die Sprache→Werkzeug→Verifikation-Pipeline —
abgelesen, nie als Steuergröße optimiert. **Was an seine Stelle trat:** die echten
Begleiter-Ziele im Ziel-Graphen (`genus/ziele.py`, Ronnys sieben Punkte). Der Maßstab eines
Begleiters ist nicht „besteht die Klausur", sondern „kann bei Schulmathe wirklich helfen" —
gemessen an gelebter Nutzung (Belegung, Folge-Signale, Korrekturen).

## 6 · Verwandte Entscheidungen

- Punkt 4 des Gedächtnis-Konzepts (Tagespuffer + Nacht-Konsolidierung + Morgen-Push) wurde
  bewusst zurückgestellt, um sich auf dieses Ziel zu konzentrieren (Ronny, 2026-07-03) — nicht
  vergessen, nur nicht aktiv.
- sympy als erste externe Kern-Abhängigkeit war eine explizit bestätigte Entscheidung
  (AskUserQuestion), kein stiller Import.
