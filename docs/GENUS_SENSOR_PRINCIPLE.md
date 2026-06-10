# GENUS SENSOR PRINCIPLE

> Der Vertrag für jeden Sensor, den GENUS je bekommt — lokal oder extern.
> Er bewahrt die DNA, gerade wenn GENUS nach außen wächst.

---

## Das Prinzip in einem Satz

**Ein Sensor nimmt wahr. Er urteilt nie.**

Wie ein Auge: es sieht, aber es denkt nicht. Der Sensor holt Material, bringt
es in saubere Form, legt es als Beobachtung hin — und hört genau dort auf. Das
Denken macht der Kern.

---

## Die harte Grenze

Jeder Sensor liefert ausschließlich **Observation**. Niemals Evidence,
niemals Belief, niemals ein Urteil.

```
Observation  ✓  der Sensor darf das    (rohe, eindeutige Wahrnehmung)
Evidence     ✗  macht der Kern
Belief       ✗  macht der Kern
Urteil       ✗  macht der Kern
```

Das ist `Observation ≠ Evidence` aus der DNA, angewandt auf die Außengrenze
von GENUS. Sobald ein Sensor bewertet, vergleicht oder schlussfolgert, hat er
GENUS' Arbeit gestohlen — und GENUS wäre nur noch ein Speicher für fremde
Schlüsse.

---

## Erlaubte vs. verbotene Optimierung

Die feine Grenze, die alles entscheidet:

**Erlaubt — Optimierung der FORM:** rohe Daten holen, säubern, in eine klare
Zahl oder Kategorie gießen.

**Verboten — Optimierung der BEDEUTUNG:** aus der Zahl ein Urteil machen.

### Beispiel Fahrplan

```
✓ richtig:  { soll: "14:03", ist: "14:11", abweichung_min: 8 }
            → rohe, eindeutige Beobachtung. GENUS bildet selbst:
              "8 Min Abweichung → Belief: unpünktlich → Muster über Zeit"

✗ falsch:   { linie: "X", bewertung: "unzuverlässig" }
            → der Sensor hat den Belief gebildet, nicht GENUS.
              Erkenntnis vorweggenommen. Verboten.
```

Die Faustregel: liefert der Sensor etwas, das *messbar und eindeutig* ist —
gut. Liefert er etwas, das *interpretiert oder bewertet* ist — zu weit
gegangen.

---

## Das Herkunfts-Etikett

Jede Observation trägt mit, **woher** sie kommt und **wie** — aber nie eine
Bewertung der Verlässlichkeit. Der Sensor meldet die Fakten der Herkunft,
GENUS entscheidet selbst, wie sehr es der Quelle traut.

```
{
  source:      "bahn-api",
  fetched_at:  "2025-...T14:05Z",
  soll:        "14:03",
  ist:         "14:11"
}
```

Nicht: `"verlässlichkeit": "hoch"` — das wäre wieder ein Urteil. Nur die
nackte Herkunft. Vertrauen ist ein Belief, und Beliefs macht der Kern.

## Quellen-Vertrauen wird berechnet — wie Confidence

Das eigene Confidence-Prinzip, eine Ebene höher: Jede Quelle (Sensor, API,
Modell-Organ, ein anderer GENUS-Kern, auch der Mensch) bekommt eine
**berechnete** Verlässlichkeit aus ihrer Historie — wie oft haben ihre
Beobachtungen zu Beliefs geführt, die sich bestätigt haben? Nie als Zahl
gespeichert, immer aus dem Ledger abgeleitet.

Neue Quellen starten in **Quarantäne**: ihre Observations werden aufgenommen
und etikettiert, aber Beliefs aus ihnen tragen anfangs gedeckelte Confidence,
bis die Quelle sich bewährt hat. So kann eine vergiftete oder fehlerhafte
externe Quelle den Kern nicht sofort fluten.

## Andere GENUS-Kerne sind auch nur Quellen

In der föderierten Zielform (ein Kern pro Charakter/Person) gilt dieses
Prinzip unverändert zwischen Kernen: **Ein fremder Kern ist ein Auge.** Was er
über einen Vertrag teilt, ist aus Sicht des empfangenden Kerns eine Observation
von einer externen Quelle — mit Herkunfts-Etikett, mit berechnetem
Quellen-Vertrauen, niemals direkt Belief. Die "ANDERE"-Familie der Physik
(fremdes Wissen bewerten, vertrauen, abgrenzen) ist technisch nichts weiter als
dieses Sensor-Prinzip, angewandt auf andere Kerne.

---

## Wo Sensoren leben

```
genus/                ← der denkende Kern. grep bleibt hier für immer leer
                        (kein HTTP, kein LLM). denkt offline und rein.

genus_sensors_ext/    ← der wahrnehmende Rand. HIER darf HTTP.
                        jeder Sensor tut genau eine Sache:
                        holen → säubern → observation_created → fertig.
```

Lokale Sensoren (CPU, Memory, Disk …) schreiben direkt Observations in den
Kern, weil sie nichts aus dem Netz brauchen. Externe Sensoren (Fahrplan,
Markt, Wetter …) leben im Rand, berühren das Netz, und reichen nur fertiges
Material nach innen.

Damit bleibt die wichtigste Aussage über GENUS erhalten, egal wie weit es nach
außen wächst: **Der Teil, der denkt, ist offline und rein. Nur der Teil, der
wahrnimmt, berührt die Welt.**

---

## Warum das zählt

GENUS wird viele Augen bekommen — System, Fahrpläne, Märkte, später vielleicht
mehr. Jedes neue Auge ist ein neuer Sensor im Rand. Der Kern bleibt dabei
unberührt und beweisbar rein. Das ist es, was GENUS von "LLM plus Speicher mit
Internetzugang" unterscheidet:

> Nicht das System holt sich die Welt und verarbeitet sie undurchsichtig.
> Klar getrennte Augen reichen rohe Wahrnehmung an einen gläsernen Verstand.

Material wird dabei nach **Physik** gewählt, nicht nach Thema: jeder Sensor
übt eine Erkenntnisform (Rhythmus, Trend, Korrelation, Soll-Ist-Abgleich …).
Das Thema ist Trainingsgelände, die Erkenntnisform ist das Ziel.

---

*Augen, die sehen, aber nicht denken. Ein Verstand, der denkt, aber rein
bleibt. Das ist die Außengrenze von GENUS.* 🧬
