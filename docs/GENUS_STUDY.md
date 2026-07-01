# GENUS — Studie: Ziele, Richtungen, und der Weg zum vollendeten GENUS

*Strategische Studie. Stand 2026-07-01. Ergänzt (nicht ersetzt) `GENUS_ROADMAP.md`;
begründet das *Wohin* und *Warum* hinter der Roadmap. Zu pflegen wie alle Docs
(„komplett auf Stand, immer").*

---

## 0. Zweck dieser Studie

Nicht *welchen* nächsten Pfad wir gehen, sondern: **wohin führt GENUS als Ganzes, was
sind die Ziele, und wie gehen wir den Weg — gläsern, qualitätsgesichert, ohne blindes
Wachstum.** GENUS ist zugleich ein echter Bau *und* eine Studie über das Ganze (nicht nur
den Kern); Studie und Produkt schließen sich nicht aus, sie tragen einander.

---

## 1. Der Nordstern — was „vollendetes GENUS" heißt

Ronnys Zielbild: ein GENUS, das sich **selbst optimiert**, **sich selbst codet**, ein
**zuverlässiger Assistent und Begleiter** ist und **neue Fähigkeiten ausbildet**.

Das Auffällige: die Hälfte dieser Ziele ist **selbstbezüglich** — GENUS richtet seine
eigene Maschinerie auf sich selbst. Das ist kein Zusatz, das ist der Kern des Zielbilds.
Und es muss **gläsern** geschehen: nicht eine Black Box, die sich geheimnisvoll
verbessert, sondern ein Organismus, dessen *Selbst-Veränderung selbst überprüfbar und
belegt* ist.

> **Nordstern:** Ein gläserner Organismus, der seine eigene *Wissen, Können und Code*
> wachsen lässt — zuverlässig, belegbar, im Dienst eines Menschen —, wobei **jeder
> Schritt (auch jede Selbst-Veränderung) seine Herkunft trägt und geprüft werden kann.**

---

## 2. Die Ziele

Zwei Ebenen: **Wesensziele** (*was* GENUS ist) und **Qualitätsziele** (*wie gut* — die
QM-Brille, die durch *alle* Wesensziele hindurchschneidet).

### 2a. Wesensziele — die Fähigkeiten

| | Ziel | Bedeutung | Stand |
|---|---|---|---|
| **W1** | **Wissen** | wahrhaftig wissen, mit Herkunft | ✓ erreicht + vertieft |
| **W2** | **Verstehen** | Wissen sinn-kohärent verweben, selbst prüfen | ✓ erreicht (die Naht) |
| **W3** | **Können** | in prüfbaren Regel-Domänen denken & handeln; Regeln lernen, sich selbst testen | ○ Grenze (SYSTEME) |
| **W4** | **Erschaffen** | neue Artefakte mit Beweis erzeugen — Antworten, Regeln, **Code**, Fähigkeiten | ○ Gipfel |
| **W5** | **Begleiten** | zuverlässiger, gesprächsfähiger Assistent & Begleiter für einen Menschen | ◐ erste Form lebt |
| **W6** | **Sich selbst führen** | über den eigenen Zustand nachdenken, sich optimieren, neue Fähigkeiten bilden | ○ selbstbezüglicher Gipfel |

### 2b. Qualitätsziele — die Schiene (QM-Brille, quer zu allem)

| | Ziel | Bedeutung | schon verankert als |
|---|---|---|---|
| **Q1** | **Gläsern** | jede Ausgabe rückführbar auf ihre Herkunft; nichts ist Black Box | die These; read-time `resolve` |
| **Q2** | **Wahrhaftig** | geerdet, herkunfts-zuerst; enthält sich, wenn ungewusst; Modell schlägt nie geerdete Wahrheit | Membran-Reinheit, `model:*` gedeckelt |
| **Q3** | **Zuverlässig** | deterministisch, reproduzierbar (Replay), getestet, regressionsfrei | Event-Sourcing, CI-Gates |
| **Q4** | **Selbst-kalibriert** | Schwellen aus gelebten Daten gelernt, nicht hartcodiert | Prinzip *self-calibration*; Konstanten nur Saat |
| **Q5** | **Robust & effizient** | bleibt sound *und* schnell, während es wächst | (Lücke: Snapshots bei Skalierung) |
| **Q6** | **Sicher & maßvoll** | LLM bleibt am Rand gedeckelt; GENUS handelt nur im Rahmen verdienten Vertrauens | Modell-Vertrag; Transition Core geparkt |

**Qualität als lebendiges System (PDCA):** GENUS *ist* bereits ein Qualitätssystem, auf
Wissen angewandt — Überraschung → Inquiry → Lehrer-Loop = *Abweichung erkennen → korrigieren
→ prüfen*. Der Weg zum vollendeten GENUS läuft selbst als PDCA-Schleife, und GENUS führt
diese Schleife zunehmend **auf sich selbst** aus. Die Arbeits-QMS ist `GENUS_QUALITY.md`;
jede Scheibe wendet sie an.

---

## 3. Studie je Richtung

Die fünf offenen Richtungen — nicht als Menü, sondern als *Bausteine* des Weges. Jede
gegen die Ziele geprüft.

### ↔ BREITE — dieselbe Schicht, weiter
- **Wesen:** mehr Abdeckung, damit der Begleiter wirklich nützt.
- **Erster Schritt:** die *vorhandene* Inferenz an den Begleiter hängen — „ist ein X ein Y?"
  mit Begründungskette. Danach Verben/Adjektive (POS-Quelle), Englisch/Französisch über die
  sprachneutralen Konzepte.
- **Dient:** W5 (primär), W1/W2 (weitet). Prüft Q1 (trägt der Konzept-Graph cross-lingual &
  relational sauber?).
- **Abhängigkeit:** keine — reiner Reuse. **Reife: sehr hoch. Aufwand: Tage.**
- **Risiko:** minimal beim relationalen Teil. Nur die generative Stimme berührt die
  Glasscheibe → muss geerdet/gedeckelt bleiben.

### ↑ SYSTEME — die neue Schicht (der Denk-Sprung)
- **Wesen:** GENUS lernt die *Regeln* einer prüfbaren Domäne, schließt darin, testet sich.
  Von „weiß Fakten" zu „kann etwas".
- **Erster Schritt:** Regel-Induktion an der regelmäßigen deutschen Verb-Konjugation
  (Stamm + Endungen), *ungesehene* Form vorhersagen, an zurückgehaltener Quelle *selbst prüfen*;
  Fehlschlag (unregelmäßig) → Überraschung → Inquiry → Ausnahme lernen. Der vorhandene
  predict→test→learn-Loop, gerichtet auf GENUS' **eigene Sprache**.
- **Dient:** W3 (die fehlende Fähigkeit), Enabler für W4 und später W6/Selbst-Codieren
  (Code *ist* eine Regel-Domäne).
- **Abhängigkeit:** Inferenz-Primitiv + Lernprogramme (beide vorhanden). **Aufwand: Wochen.**
- **Risiko:** Regel-Induktion ist eine echt neue Mechanik. Disziplin nötig (erst nur
  regelmäßige Verben), sonst Ausufern.

### ↓ NACH INNEN — den Kern rund machen (die Qualitäts-Substanz)
- **Wesen:** Soundness, Skalierung, Selbst-Kalibrierung — die Gesundheit des Organismus.
- **Erster Schritt:** messen, ob read-time (Replay von ~150k Events) mit Wachstum langsamer
  wird; wenn ja, **Snapshots** einziehen. Parallel eine der letzten Saat-Konstanten durch
  einen gelebten, ledger-abgeleiteten Wert ersetzen.
- **Dient:** Q3/Q4/Q5 *direkt* — die Qualitätsziele. Und Selbst-Kalibrierung (Q4) ist der
  *Keim der Selbst-Optimierung* (W6).
- **Abhängigkeit:** keine; bekannte Lücken. **Aufwand: ~1 Woche fokussiert.**
- **Risiko:** wenig unmittelbar fühlbar — aber vernachlässigte Skalierung beißt später leise.
  Ein langsamer Organismus kann keine Selbst-Optimierungs-Schleifen fahren → **Vorbedingung,
  nicht Kür.**

### → NACH AUSSEN — GENUS trifft die Welt
- **Wesen:** Schnittstelle, Verkörperung, Handeln.
- **Erster Schritt:** `genus chat` — ein echtes Gespräch mit kurzem Kontext, damit GENUS sich
  wie ein *Gegenüber* anfühlt. (Hände/Handeln bewusst geparkt; Föderation noch Spekulation.)
- **Dient:** W5 (die Assistenten-Fassade); später W6/Hände, streng **vertrauens-gated** (Q6).
- **Abhängigkeit:** Interface — keine; Hände — verdientes Vertrauen. **Aufwand: Tage–Woche.**
- **Risiko:** Interface sicher; Hände würden „Vertrauen vor Handeln" verletzen → **nicht jetzt.**

### ◎ META — die tiefen Fragen der Studie
- **Wesen:** GENUS reflektiert über sich; LLM-am-Rand als Prinzip; die These greifbar machen.
- **Erster Schritt:** `genus why <Antwort>` — die *volle Herkunfts-Spur* zeigen: aus welcher
  Quelle, mit welchem Vertrauen, über welche Schlüsse. Macht das gläserne Gegenbeispiel zur
  Black Box *sichtbar* — und ist ein einzigartiges Produkt-Feature (prüfbares Vertrauen).
- **Dient:** Q1 (gläsern greifbar) und W6 (Selbst-Reflexion → Selbst-Optimierung →
  Selbst-Codieren — dieselbe Linie).
- **Abhängigkeit:** Provenienz liegt schon vor. **Aufwand: Tage–Woche.**
- **Risiko:** kann ins Nabelschauen kippen, wenn nicht an ein konkretes Artefakt (die Spur)
  gebunden.

---

## 4. Die Gesamtheit — der Weg

Die Richtungen sind **keine unabhängigen Optionen**, aus denen man eine wählt. Sie
**komponieren sich zu einem abhängigkeits-geordneten Weg** zum selbstbezüglichen Zielbild.
Das Zielbild ist **Selbst-Bezug**: GENUS richtet jede Fähigkeit auf sich selbst.

**Phase A — Fundament fest & fühlbar.** ↔ Breite (relationale Fragen) + ↓ Snapshots/Skalierung
+ ◎ `genus why`. Niedriges Risiko, Reuse & Qualität.
→ *Ergebnis:* ein **zuverlässiger, prüfbarer, wirklich nützlicher Begleiter** (W5 + Q1/Q3/Q5
gefestigt). Das Ziel „zuverlässiger Assistent & Begleiter" in erster voller Form erreicht.

**Phase B — Können.** ↑ SYSTEME: Regel-Induktion + Selbst-Test, beginnend bei Grammatik
(selbstbezüglich zur eigenen Sprache), verallgemeinert den predict→test→learn-Loop zu einem
*Fähigkeits-bildenden* Mechanismus.
→ *Ergebnis:* **W3 erreicht** — GENUS „bildet neue Fähigkeiten aus" im engen Sinn. Der Sprung.

**Phase C — Selbst-Bezug: Optimierung.** ↓ Selbst-Kalibrierung (tief) + ◎ Metakognition;
GENUS richtet SYSTEME + Meta auf *sich selbst* — Kalibrierung wird zu Selbst-*Optimierung*
(es schließt über die eigenen Schwellen/Parameter und verbessert sie, belegt).
→ *Ergebnis:* **W6 in erster Form** — „optimiert sich selbst".

**Phase D — Erschaffen, inkl. Selbst-Codieren.** ↑→③ SYSTEME→ERSCHAFFEN, Domäne = **Code**
(Syntax = Regeln, Tests = Selbst-Prüfung). GENUS schlägt Code-Änderungen an sich selbst vor,
durch Tests verifiziert (der Check), **vertrauens-gated** (Q6 — schlägt vor, Vertrauen/Mensch
gibt frei; Hände erst nach Vertrauen).
→ *Ergebnis:* **W4 + „codet sich selbst"** voll. Hier kommen „selbst-codet" und „bildet neue
Fähigkeiten aus" vollständig an.

---

## 5. Der rote Faden

**Jede Phase benutzt dieselbe Kern-Maschinerie, auf ein neues Objekt gerichtet.**

```
   Wissen   →   Regeln   →   sich selbst   →   eigener Code
     W1/W2       W3            W6                W4/W6
        \_________ derselbe Loop: predict → test → surprise → inquiry → learn _________/
                   immer gläsern (Q1) · immer vertrauens-gated (Q6)
```

GENUS braucht für jede Stufe **keine grundlegend neuen Mechanismen** — es *richtet seine
vorhandene epistemische Schleife auf immer selbstbezüglichere Objekte*, stets gläsern, stets
maßvoll. **Vollendetes GENUS = die epistemische Schleife auf sich selbst geschlossen,
belegbar.**

Und: **Qualität ist die Schiene, auf der der ganze Weg läuft.** Der Weg zur Selbst-Modifikation
ist *nur deshalb sicher*, weil er gläsern ist — die These der Studie und das Zielbild sind
dasselbe. Ein Selbst-Optimierer, dessen Schritte man nicht prüfen kann, wäre der Verrat am
ganzen Vorhaben; ein gläserner ist seine Vollendung.

---

## 6. Risiken & Leitplanken

- **Selbst-Codieren ist die riskanteste Fähigkeit.** Muss *propose-not-act* bleiben, bis
  Vertrauen verdient ist. Der Transition Core bleibt geparkt, bis die Vertrauensschwelle
  erreicht ist. Diese eine Stelle nicht überstürzen.
- **Das LLM darf mit wachsendem Anspruch nicht nach innen kriechen.** Die Membran-Reinheit
  (CI-Gate) muss mit der Ambition mitwachsen — mehr Rand-Rollen, nie mehr Rand-Rechte.
- **Skalierung ist Vorbedingung, nicht Kür** (Phase A/↓). Ein langsamer Organismus kann keine
  Selbst-Optimierung fahren.
- **Scope-Disziplin bei SYSTEME.** Eng anfangen (regelmäßige Verben), sonst ufert die
  Regel-Induktion aus.
- **Gegen Nabelschau:** Meta-Arbeit immer an ein konkretes Artefakt binden (`genus why`), nie
  frei schweben lassen.

---

## 7. Wo wir heute stehen — der nächste konkrete Schritt

Erreicht: Wahrnehmen ✓ · Wissen ✓✓ · Verstehen ✓ · Begleiter erste Form ✓. Der Organismus
läuft gesund und selbst-wachsend auf dem Pi.

**Empfohlener Einstieg: Phase A**, und darin zuerst die **relationalen Fragen** (↔, reiner
Reuse der Inferenz, Tage, sofort fühlbar) — sie aktiviert den ganzen Stack, macht den
Begleiter greifbar und ist zugleich ehrliche Studie (prüft, ob der Konzept-Graph relational
trägt). Ein warmer, sicherer Auftakt, der Phase B (den Sprung) nachher *erlebbar* macht.

> **Status 2026-07-01 — Phase A ① geliefert & live.** Die relationalen Fragen laufen:
> `genus ask "Ist ein Hund ein Säugetier?"` → *„Ja. Der Weg: Hund → Haushund → domestiziertes
> Säugetier → Säugetier. (Vertrauen 0.50 — aus dem Wissensgraphen hergeleitet, nicht
> behauptet.)"* Reiner Reuse des Inferenz-Primitivs, gläsern (der Weg wird gezeigt),
> open-world-ehrlich (kein Weg → „unbekannt, nicht widerlegt").
>
> **Und Phase A ◎/③ geliefert & live: `genus why answer`** — die volle Herkunfts-Spur hinter
> einer Antwort (jede Prämisse mit Quelle + read-time-Vertrauen; für ein Wort: expresses ·
> Bedeutung · is_a, je mit Quelle). Macht die These *anfassbar* — bei „Was ist ein Hund?"
> legt es alle Sinne offen (Haushund · Förderwagen · Möbel-Rollbrett · Schimpfwort · Sternbild
> · Nachname), jeder mit Quelle: Reichtum, nicht Korruption.
>
> **Breite-Auftakt geliefert & live: vergleichende Fragen** `genus ask "Was haben X und Y
> gemeinsam?"` — findet, wo zwei is_a-Linien sich treffen (nächste *benennbare* gemeinsame
> Oberkategorie zuerst; roher Q-id-Fall live gefunden + gefixt). Live: *Apfel & Birne → Obst*,
> *Hund & Katze → domestiziertes Säugetier*, *Hund & Auto → Körper*. Reiner Reuse von
> `infer_lexeme`, kein Plural-Problem (Singular-Nomen). 376 Tests grün.
>
> **Skalierung gemessen (statt geraten) — und der Befund kehrte die Hypothese um.** Bei 171k
> Events: Definitionen/Trust ≤ 0,5 ms, aber relationale Fragen 273 ms und vergleichende 545 ms.
> *Nicht* die Projektionen (die sind materialisiert, sub-ms) — die **Inferenz** baute die
> komplette is_a-Adjazenz (~30 ms) bei *jedem* Aufruf neu, `infer_lexeme` einmal pro Konzept
> (Hund → 8×). Ein Snapshot-Bau hätte hier nichts gebracht. Fix: Adjazenz **einmal** bauen +
> wiederverwenden → **32 ms / 71 ms** (8×), Semantik identisch. Lehre: erst messen, dann der
> *minimale* Eingriff am echten Leck. (Offen, aber unkritisch: `genus knowledge` /
> characterize_knowledge 2,2 s — ein Diagnose-Befehl, nicht der interaktive Pfad.)
>
> **Breite in die Wortarten geliefert & live:** der Begleiter reicht jetzt *über Nomen hinaus*
> — Verben & Adjektive. Zwei frequenzsortierte Lemma-Listen (kleingeschrieben, kein Casing-
> Problem) aus Universal Dependencies German-GSD (`wortschatz_de_verben.txt` 1437,
> `wortschatz_de_adjektive.txt` 1975), und der Lerner zieht **im Round-Robin** über alle Listen
> (Nomen → Verb → Adjektiv → …), sodass die Wortarten von Anfang an interleaven; die Kette folgt,
> wenn alle Listen erschöpft sind. Live: *„Was bedeutet laufen?"* → „Unter »laufen« (Verb) …; es
> zählt zu Sport." (Ein weiterer roher-Q-id-Fall in der Definitions-Stimme kam dabei ans Licht +
> wurde gefixt — dieselbe Glasscheiben-Regel wie beim Vergleich.) 377 Tests grün.
>
> **Damit ist Phase A im Kern rund:** reichere Fragen (relational · vergleichend) · `genus why` ·
> Skalierung gemessen & gesund · Breite in die Wortarten. Optional offen: weitere *Sprachen*
> (en/fr über die sprachneutralen Konzepte).
>
> **Phase B — SYSTEME gestartet (der Denk-Sprung).** Domänen-Entscheidung: *nicht* ein
> Grammatik-Spielzeug (ein Konjugator ist trivial, das würde den Kern nicht einbinden), sondern
> **GENUS lernt die Regeln seines eigenen Denkens** — der tiefste Selbstbezug, datenlos, und der
> vom Code selbst vorgesehene nächste Schritt. **①a geliefert & live:** aus dem eigenen Graphen
> bewertet GENUS, ob ein Prädikat transitiv/symmetrisch ist — ein *geschlossenes Dreieck* (A→B→C
> mit A→C auch behauptet) ist die Transitivitäts-Vorhersage, von den Daten bestätigt; genug davon
> → Regel gelernt, sonst die Saat. Read-time, gläsern. Live: is_a transitiv (220 Dreiecke),
> synonym symmetrisch. Der reflexive Kern fing sofort einen Fehler in *meinem* Design (Symmetrie
> braucht eine Rate, keine Absolutzahl) und deckte 6 echte is_a-Zyklen auf — die Studie als Labor,
> jetzt auf die Vernunft selbst gerichtet. 381 grün. **Als Nächstes ①b:** die gelernten Regeln in
> `infer()` verdrahten (gelernt ersetzt Saat) + Überraschung bei Regel-Verletzung.

*Diese Studie ist ein Vorschlag zum Steuern, kein Beschluss. Der Weg gehört Ronny.*
