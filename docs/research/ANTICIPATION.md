# GENUS ANTIZIPATION

> **Status:** Forschung / datierter Denkstand · **Autorität:** nicht kanonisch. Aktuelle Orientierung: [Dokumentationsindex](../README.md), [NOW](../NOW.md), [Roadmap](../ROADMAP.md) und [Architektur](../ARCHITECTURE.md).

> Die Fähigkeit, eine Situation mit offenem Ausgang einzuschätzen,
> eine Vorhersage zu treffen und an der Realität zu messen.
> Der Kern des Trading-Use-Cases — und eine eigene Erkenntnisform.

---

## Was Antizipation ist

Bisher bildet GENUS Beliefs über die **Gegenwart**:

> "system.load = high" — jetzt, belegt durch aktuelle Evidence.

Antizipation ist ein Belief über einen **offenen Ausgang**:

> "ich erwarte, dass sich das so entwickelt" — mit Confidence,
> später von der Realität geprüft.

Der entscheidende Unterschied liegt in einem Wort: **Vorhersage**. Ein
Gegenwarts-Belief wird durch vorhandene Evidence gestützt. Ein Vorhersage-Belief
wird durch *zukünftige* Evidence eingelöst — die Zeit prüft ihn von selbst.

Das ist die sauberste Form von Lernen, die es gibt: GENUS muss nicht raten, ob
es richtig lag. Die Wirklichkeit sagt es ihm.

---

## Die Schleife

```
1. Situation     GENUS nimmt eine Lage wahr (Stellung, Markt, Metrik)
2. Vorhersage    GENUS bildet einen Belief MIT erwartetem Ausgang
                 + Horizont (wann löst er sich ein?) + Confidence
3. Zeit vergeht  die Realität entfaltet sich
4. Einlösung     Vergleich Vorhersage ↔ tatsächlicher Ausgang
                 → Treffer / Fehlschlag / wie weit daneben
5. Erfahrung     über viele Vorhersagen: Trefferquote nach Bedingung
6. Reifung       unzuverlässige Vorhersage-Regeln werden angepasst
                 (vorgeschlagen → menschlich freigegeben → deterministisch)
```

Schritt 5 und 6 sind nichts Neues — es ist Experience und Maturation, nur auf
*Vorhersagen* angewandt statt auf Gegenwarts-Beobachtungen. Die Maschinerie
existiert (bzw. ist geplant); Antizipation richtet sie auf die Zukunft.

---

## Der zukunftsblinde Vergangenheits-Trick

GENUS kann an **historischen Daten** üben, ohne auf echte Zeit zu warten:

- eine alte Schachpartie: GENUS sieht nur bis Zug 20, sagt voraus, dann
  enthüllst du Zug 21
- ein vergangener Kursverlauf: GENUS sieht den Markt bis Dienstag, sagt
  voraus, dann kommt Mittwoch

GENUS weiß nicht, dass es Vergangenheit ist — für GENUS ist es offene Zukunft.
So spielst du Jahre von Übung in Minuten durch. Vollständig deterministisch,
kein LLM, kein Zufall. Dasselbe Verfahren übt Schach *und* Märkte — eine
Fähigkeit, zwei Übungsplätze.

**Wichtig für die Sauberkeit:** Die Daten dürfen GENUS immer nur bis zum
Vorhersage-Zeitpunkt sichtbar sein. Sobald auch nur ein Datenpunkt aus der
"Zukunft" durchsickert, ist die Übung wertlos (Look-ahead-Bias). Das muss der
Übungs-Harness hart erzwingen.

**Der subtilere Leak — die Auswahl:** Auch wenn jede einzelne Vorhersage
zukunftsblind war: Wer Strategien *iterativ gegen dieselbe Historie*
verbessert, leakt die Zukunft über seine Auswahl. Die Regel, die nach zehn
Anpassungsrunden auf denselben Daten "gut" aussieht, hat die Daten auswendig
gelernt, nicht verstanden. Gegenmittel: Historie in Übungs- und
Prüf-Zeiträume trennen; eine gereifte Regel wird nur an Daten bewertet, die
sie nie zum Verbessern gesehen hat.

---

## Die ehrliche Erwartung beim Trading

GENUS' Wert im Trading ist **nicht**, den Markt zu schlagen — Schwellwert- und
Mustermechanik schlägt keine Märkte, und kein Backtest-Ergebnis ändert das.
Sein Wert ist **kalibrierte Ehrlichkeit**: zu wissen, wann es nichts weiß.
Brier-getrackte Trefferquoten, ehrliche Confidence, Herkunft jeder
Einschätzung. Ein System, das vor der eigenen Überkonfidenz schützt, ist mehr
wert als eines, das Gewinne verspricht. Genau dafür ist die noch fehlende
Erkenntnisform *"Erkennen des Unwissbaren"* (siehe [Epistemische Physik](EPISTEMIC_PHYSICS.md)) die
wichtigste — beim Trading entscheidet sie alles.

Die eingelösten Vorhersagen liefern nebenbei das erste **objektive
Erfolgsmaß** des ganzen Projekts: Trefferquoten und Brier-Scores sind der
erste echte Maßstab dafür, ob GENUS' Beliefs *gut* sind — nicht nur konsistent.

---

## Was im heutigen Kern dafür fehlt

Antizipation ist anspruchsvoller als alles im aktuellen Kern — aber sie
braucht **kein LLM**. Es ist reine deterministische Logik. Konkret fehlen:

**1. Der Vorhersage-Belief selbst.** Ein Belief hat heute `claim_key`,
`claim_value`, Gegenwart. Eine Vorhersage braucht zusätzlich:
- einen **erwarteten Wert** (was wird eintreten)
- einen **Horizont** (wann löst sie sich ein — nach Zeit T, oder nach den
  nächsten N Beobachtungen dieser Metrik)
- einen **Pending-Zustand** (offen → eingelöst)

**2. Der Einlöse-Mechanismus.** Heute kommt nichts "später zurück, um zu
prüfen". Es braucht etwas, das bei Eintreffen des Horizonts die Vorhersage mit
der Realität vergleicht. Das ist neu.

**3. Ein reicheres Ergebnis-Modell.** Bei kategorialen Werten (high/normal)
reicht exakter Abgleich. Bei kontinuierlichen (Preis, Bewertung) braucht es
Toleranz oder Richtung (rauf/runter) — und damit einen Fehlerbegriff statt nur
"richtig/falsch".

**4. Eine Trefferquote als Projektion.** Über viele eingelöste Vorhersagen:
wie oft richtig, unter welchen Bedingungen. Berechnet, nicht gespeichert —
genau wie Confidence.

**5. Ein erster, bewusst dummer Vorhersager.** Hier die wichtigste
Disziplin: Fang **nicht** mit einem klugen Vorhersage-Modell an. Fang mit dem
einfachsten an — z.B. "ich sage voraus, der Wert bleibt gleich"
(Persistenz-Vorhersage). Der dumme Vorhersager existiert nur, um die
Schleife *Vorhersage → Einlösung → Trefferquote* zu beweisen. Erst wenn die
Mechanik läuft, werden die Vorhersagen besser. Maschinerie vor Klugheit —
dasselbe Prinzip wie immer.

---

## Neue Events (Vorschlag)

| Event | hält fest |
| --- | --- |
| `prediction_made` | claim_key, erwarteter Wert, Horizont, Quelle, Confidence |
| `prediction_settled` | prediction_id, tatsächlicher Wert, Ausgang (Treffer/Fehler), Abweichung |

Neue Projektion: `prediction_log` (offen → eingelöst). Die Trefferquote ist
eine abgeleitete Sicht über die eingelösten Vorhersagen — Experience über
Vorhersagen.

---

## Wie es zur DNA passt

```
Prediction ≠ Truth        → eine Vorhersage ist ein Belief über die Zukunft,
                            eingelöst durch Realität, nie "wahr" für sich
Einlösung = Evidence      → der tatsächliche Ausgang ist neue Evidence
Trefferquote = berechnet  → nie als Magie-Zahl gespeichert
kein LLM                  → reine deterministische Logik
Replay-stabil             → Vorhersage + Einlösung sind Events,
                            Trefferquote ist Projektion
```

Antizipation fügt sich also vollständig ein. Sie ist kein Bruch mit dem Kern —
sie ist seine Erweiterung in die Zeitdimension.

---

## Wo es in die Roadmap gehört

Antizipation steht **auf** dem Gegenwarts-Kern, nicht in ihm:

- sie braucht Beliefs (vorhanden)
- der Einlöse-/Trefferquoten-Teil ist Experience über Vorhersagen
  (also sinnvoll nach **v0.9 Experience**)
- die *Verbesserung* der Vorhersagen ist Maturation über Vorhersagen
  (also voll wirksam nach **v1.0 Maturation**)

Deshalb: **eine eigene Phase nach dem deterministischen Gegenwarts-Kern.**

```
v0.6–v1.0   Gegenwart einschätzen   (wahrnehmen, glauben, revidieren, reifen)
─────────────────────────────────────────────────────────────────
PHASE A     Antizipation             (Zukunft einschätzen)
            A.1  Vorhersage-Belief + Einlöse-Mechanismus (dummer Vorhersager)
            A.2  Trefferquote als Erfahrung
            A.3  Maturation über Vorhersagen → bessere Vorhersagen
            Übungsplätze: Schach (eindeutiges Feedback), Markt (verrauscht)
─────────────────────────────────────────────────────────────────
MODEL ERA   Meaning Engine, Charaktere, Trading mit Bedeutung …
```

Der erste echte Trading-Use-Case lebt in Phase A: Lagen einschätzen,
vorhersagen, an der Vergangenheit zukunftsblind üben, Strategie schärfen —
alles deterministisch und erklärbar, bevor je ein LLM dazukommt.

---

## Die ehrlichen Fragen, bevor gebaut wird

Vor dem ersten Baustein zu entscheiden:

1. **Horizont — Zeit oder Schritte?** Löst sich eine Vorhersage "nach 1 Stunde"
   ein (Markt) oder "nach 3 Zügen / N Beobachtungen" (Schach)? Beides braucht
   Unterstützung; schrittbasiert ist für den ersten Baustein einfacher.
2. **Ausgang — Kategorie oder Richtung oder Wert?** Exakter Treffer, oder
   rauf/runter, oder Wert-mit-Toleranz? Das bestimmt das Ergebnis-Modell.
3. **Erster Übungsplatz — Schach oder Markt?** Schach gibt eindeutiges Feedback
   (die Partie sagt, wer recht hatte), ist aber sauberer als die Welt. Markt
   ist verrauscht und realistischer, aber das Feedback ist weniger eindeutig.

---

*Antizipation ist die Brücke von "die CPU ist hoch" zu "ich glaube, der Markt
dreht". Dieselbe gläserne Mechanik — nur in die Zukunft gerichtet.* 🧬
