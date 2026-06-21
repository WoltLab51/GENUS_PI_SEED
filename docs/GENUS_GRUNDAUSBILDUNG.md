# GENUS GRUNDAUSBILDUNG

> Welches Material GENUS' Erkenntnis-Mechanik übt — und welche
> Erkenntnisform jeder Sensor fordert. Die Materialplanung vor v0.6.

---

## Das Prinzip

Mehr Sensoren machen GENUS nicht klüger. Die **richtigen** Sensoren machen es
klüger. Ein Sensor ist gut, wenn er eine Erkenntnisform fordert, die GENUS
noch nicht beherrscht — Rhythmus, Trend, Korrelation, Seltenheit. Material,
dessen Werte rauschen oder konstant sind, ist totes Material.

Deshalb wird die Grundausbildung nicht nach Menge geplant, sondern nach
**Erkenntnisform**: jeder Sensor lehrt etwas Anderes. Fünf gut gewählte
Sensoren sind reicher als zwanzig, die alle dasselbe üben.

Alles hier ist **lokal, offline, eindeutig** — System und Software, Maschine
beobachtet Maschine. Kein Bild, kein Ton, nichts Privates. Genau richtig, um
die Mechanik zu üben, wo die Wahrheit immer eindeutig ist.

---

## Die Sensoren und was sie üben

### CPU · Memory — *Schwellwert + Revision* (vorhanden)
Wert kommt, über/unter Schwelle, Belief, Revision bei Widerspruch.
Die Grundform. Beherrscht GENUS seit v0.5.

### Aktiv/Idle — *Rhythmus*
Ist der Rechner gerade in Benutzung? Der musterreichste Sensor: klarer
Tag-Nacht- und Wochenrhythmus. **Übt Experience** — daran lernt GENUS, was
"regelmäßig" überhaupt bedeutet.
*Besonderheit:* binär und zeitlich, passt **nicht** ins high/normal-Schema.
Der Wert liegt im Muster über Stunden, nicht im Moment. Zwingt GENUS zu einer
zweiten Belief-Art. Gewollt.

### Disk — *Trend*
Füllstand wächst langsam und monoton, mit gelegentlichen Sprüngen (Backups,
Downloads). **Übt einen neuen Belief-Typ:** nicht "high/normal", sondern
"steigt / stabil / fällt". Eine ganz andere Erkenntnisform als Schwellwert.
**Stand heute (verifiziert):** Disk läuft noch über die *Threshold*-Regel
(`system.disk = high/normal`), exakt wie CPU. Der Trend-Belief ist **noch nicht
gebaut** — die Trend-Erkenntnisform ist offen.

### Temperatur — *Korrelation + Widerspruch*
Hängt meist mit CPU zusammen — aber nicht immer. Temp hoch *ohne* CPU-Last ist
eine echte Auffälligkeit. **Übt State** (zwei Sensoren ergeben einen
Gesamtzustand) **und Widerspruch** (der einen Proposal verdient). Lehrt GENUS,
in Beziehungen statt in isolierten Werten zu denken.
**Stand heute (verifiziert):** Temperatur läuft ebenfalls nur über die
*Threshold*-Regel (`system.temperature = high/normal`). Die CPU-Temp-**Korrelation**
(Temp hoch ohne CPU = Auffälligkeit) ist **noch nicht gebaut** — die
Korrelations-Erkenntnisform ist offen.

### Prozess-Ereignisse — *Seltenheit / diskrete Ereignisse*
Ein Prozess startet, stürzt ab, ein Gerät wird verbunden, Hoch-/Runterfahren.
Selten und diskret, kein kontinuierlicher Wert. **Übt Seltenheit** — wertvoll
für Governance ("was ist normal?"), sprengt aber das "3 Messungen über
Schwelle"-Schema. Forderndes Material.

### Selbstbeobachtung — *alle Formen + Grundlage für Selbstreflexion*
GENUS beobachtet seinen eigenen Ledger: Events pro Tag, wächst die Zahl der
Beliefs, wie viele Proposals offen, wie viele Widersprüche. Material, das nur
GENUS haben kann — kein anderes System beobachtet sich so. Übt mehrere Formen
zugleich (Rhythmus der Aktivität, Trend des Wachstums) und ist die Grundlage
dafür, dass GENUS irgendwann über sich selbst nachdenkt.
**Stand heute (verifiziert):** **noch nicht gebaut.** Die Self-Operation-Checks
(`network.gateway`, `clock.sync`) prüfen *Betrieb*, nicht das eigene Erkennen —
das ist etwas anderes als Selbstreflexion über den Ledger.

---

## Seit dem Urplan dazugekommen (nicht in der Materialplanung von v0.6)

Diese Sensoren existieren live, gehörten aber nicht zur ursprünglichen
Grundausbildung — und der zweite Block sprengt sogar ihre Rahmen-Annahme
("Maschine beobachtet Maschine, nichts Privates"):

### Self-Operation — *GENUS beobachtet seinen Betrieb*
`network.gateway → system.network` (v1.3) und `clock.sync → system.clock`. Echte
rebuildbare Beliefs aus deterministischen Betriebs-Checks. Erkenntnisform:
Schwellwert/binär — also schon abgedeckt, aber neues *Subjekt* (der eigene
Betrieb).

### Struktur-Material — *GENUS beobachtet deine Arbeit*
`repo.commits_per_day → repo.activity` (binär, Rhythmus) und
`repo.lines_changed_per_day → repo.churn` (binär mit Schwelle, Intensität).
**Neue Kategorie:** erstmals beobachtet GENUS *dich*, nicht die Maschine —
gemessen von der Membran auf dem X1, in den Pi-Kern gespeist. **Privacy-Grenze:**
nur **Zähler & Rhythmen**, nie Inhalte (keine Commit-Texte, Diffs, Dateinamen).
Erkenntnisform: Rhythmus — also bereits abgedeckt; der Wert liegt im neuen
Subjekt, nicht in einer neuen Form.

---

## Überblick

| Sensor | geplante Erkenntnisform | Stand heute (verifiziert) |
| --- | --- | --- |
| CPU, Memory (`system.load`, `system.memory`) | Schwellwert + Revision | ✅ geübt |
| Aktiv/Idle (`system.activity`) | Rhythmus | ✅ geübt (Experience-Detektor) |
| Disk (`system.disk`) | Trend (steigt/fällt/stabil) | ⚠️ nur Threshold — **Trend offen** |
| Temperatur (`system.temperature`) | Korrelation + Widerspruch | ⚠️ nur Threshold — **Korrelation offen** |
| Prozess-Ereignisse | Seltenheit / diskret | ❌ **nicht gebaut** |
| Selbstbeobachtung (Ledger) | Selbstreflexion | ❌ **nicht gebaut** |
| `system.network`, `system.clock` | Self-Operation (Schwellwert/binär) | ✅ gebaut (seit Urplan) |
| `repo.activity`, `repo.churn` | Rhythmus/Intensität (deine Arbeit) | ✅ gebaut (neue Kategorie) |

**Ehrliche Bilanz:** Geübt sind heute **Schwellwert** und **Rhythmus** —
gründlich, und auf mehreren Subjekten (Maschine, Betrieb, deine Arbeit). Aber
drei versprochene Formen sind **noch offen: Trend, Korrelation, Seltenheit**.
Der ursprüngliche Satz „decken jede deterministische Erkenntnisform ab" war
Plan, nicht Stand. Diese drei Lücken zu füllen ist die nächste Vertiefungs-Arbeit
— *neue Belief-Typen*, nicht mehr Sensoren —, und zwar einer nach dem anderen.
Alles offline, kein Byte aus dem Internet.

---

## Was die Grundausbildung erzwingt — und das ist gewollt

Drei dieser Sensoren passen **nicht** ins aktuelle high/normal-Schwellwert-Schema:

- **Aktiv/Idle** ist binär-zeitlich
- **Disk** ist ein Trend
- **Prozess-Ereignisse** sind diskrete Ereignisse

Das ist kein Problem, sondern der eigentliche Wert. Genau hier zwingt das
Material die Architektur, reicher zu werden — neue Belief-Typen jenseits von
"high/normal". Das ist echte Reifung durch Material, nicht durch Theorie.

**Die eigentliche Trainingsarbeit** ist deshalb nicht das Bauen der Sensoren,
sondern die Reflexion nach jedem: Was hat dieses Material GENUS abverlangt? Wo
hat das Schema gehalten, wo gebrochen? Einen Sensor nach dem anderen bauen und
fragen — nicht alle auf einmal.

---

## Reihenfolge & Grenzen

**Erst lokal komplett, dann nach außen.** Die Grundausbildung ist über die
*Erkenntnisformen* definiert, nicht über eine feste Sensor-Zahl — und sie ist
**noch nicht abgeschlossen**: Trend, Korrelation und Seltenheit fehlen. Erst wenn
alle deterministischen Erkenntnisformen geübt sind, kommt der erste externe
Sensor — und der naheliegende ist nicht Wetter, sondern **Markt**, weil er direkt
auf Antizipation und Trading zuläuft. Wir stehen also bewusst *vor* dieser Tür.

**Externe Sensoren brechen die HTTP-Regel nicht — sie verlegen sie.** Wenn es
soweit ist, gehört HTTP nicht in den Kern (`genus/`, bleibt für immer
grep-leer), sondern in einen abgegrenzten Sensor-Rand, der genau eine Sache
tut: rohe Daten holen → `observation_created` schreiben → fertig. Er bildet
keine Beliefs, interpretiert nichts. Wie ein Auge: es sieht, aber es denkt
nicht. Der denkende Kern bleibt offline und rein.

**Bewusst nicht in der Grundausbildung:**
- *Kamera / Wohnung* — fühlt sich nach Überwachung an, gestrichen. Falls
  visuelles Material später kommt, dann als Aufgabe (Schachbrett, Chart),
  nicht als Zuhause.
- *Wetter, Markt* — extern (HTTP) bzw. Antizipation. Später, bewusst.
- *Text, Sprache, Bild-Bedeutung* — brauchen ein Modell. Model Era.

---

*Langweilig im Inhalt, perfekt im Lehrwert: Die Wahrheit ist immer eindeutig,
also sieht man, ob die Mechanik wirklich funktioniert.* 🧬
