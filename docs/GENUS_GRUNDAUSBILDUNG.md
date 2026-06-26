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
**Stand heute (verifiziert):** **gebaut.** Disk speist jetzt *zwei* Beliefs:
weiterhin `system.disk = high/normal` (Threshold) **und** neu
`disk.trend = rising/stable/falling` (Trend über ein Fenster, `rule:disk_trend_v1`).
Erste Form jenseits high/normal — genau die vom Material erzwungene Bereicherung.
Die Schwelle für „echte Bewegung" ist **self-kalibriert**: relativ zur eigenen
Streuung des Pi über das Fenster, keine Vorgabe-ε.

### Temperatur — *Korrelation + Widerspruch*
Hängt meist mit CPU zusammen — aber nicht immer. Temp hoch *ohne* CPU-Last ist
eine echte Auffälligkeit. **Übt State** (zwei Sensoren ergeben einen
Gesamtzustand) **und Widerspruch** (der einen Proposal verdient). Lehrt GENUS,
in Beziehungen statt in isolierten Werten zu denken.
**Stand heute (verifiziert):** **gebaut.** Neben dem Threshold-Belief
(`system.temperature = high/normal`) gibt es jetzt `system.thermal = anomalous/normal`
(`rule:thermal_correlation_v1`): „Temp hoch *während* CPU *nicht* hoch" = Anomalie.
**Self-kalibriert** — beide „hoch"-Schwellen sind die eigenen Perzentile des Pi,
keine Vorgabe. Erster kreuz-metrischer Belief (liest Temp *und* CPU).

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
`repo.lines_changed_per_day → repo.churn` (binär, Intensität — **self-kalibriert**:
„heavy" relativ zur *eigenen* Churn-Verteilung des Pi, keine Vorgabe-Zahl).
**Neue Kategorie:** erstmals beobachtet GENUS *dich*, nicht die Maschine.
Gemessen wird jetzt von der **immer-an Membran auf dem Pi**, die den
veröffentlichten Remote (`origin/main`) zählt — robust und X1-unabhängig (die
frühere X1-Membran verhungerte, sobald die Workstation aus war). Damit beobachtet
GENUS faktisch seine *eigene publizierte Entwicklung*. **Privacy-Grenze:** nur
**Zähler & Rhythmen**, nie Inhalte (keine Commit-Texte, Diffs, Dateinamen).
Erkenntnisform: Rhythmus — also bereits abgedeckt; der Wert liegt im neuen
Subjekt, nicht in einer neuen Form.

### Wetter — *erstes externes Material* (die „erst lokal"-Grenze bewusst überschritten)
`weather.temp_outside → weather.trend` (rising/stable/falling,
`rule:weather_trend_v1`, **self-kalibriert** wie `disk.trend`: die eigene Streuung
filtert die Tagesschwankung, nur ein anhaltendes Mehr-Tage-Erwärmen/Abkühlen
zählt als Trend). **Der erste Sensor, der ins Internet greift** — über die Membran
auf dem Pi (Open-Meteo, kein API-Key). HTTP lebt am Rand, `genus/` bleibt
grep-leer. **Privacy-Grenze:** der Standort (Lat/Lon) steht nur in der
Membran-Config, *nie* im Ledger; nur die Zahl + Quelle reisen.
**Warum vorgezogen** — vor der noch offenen Form *Seltenheit* und vor *Markt*: das
lokale Material eines idle Pi ist zu dünn, um die Mechanik zu fordern; Wetter
fließt reich und dir-unabhängig, ist eine *eindeutige Zahl* (gut zum Üben), und es
ist die **fehlende Variable** für `system.thermal` — „heiß bei idle CPU" ist an
einem 34-°C-Tag das Wetter, kein Fehler. Ein bewusster Override der eigenen
„erst lokal"-Reihenfolge, kein Reinrutschen. **Nächster Schritt:** die Korrelation
Pi-Temp ↔ Außen-Temp, die genau diese Anomalie auflöst.

---

## Überblick

| Sensor | geplante Erkenntnisform | Stand heute (verifiziert) |
| --- | --- | --- |
| CPU, Memory (`system.load`, `system.memory`) | Schwellwert + Revision | ✅ geübt |
| Aktiv/Idle (`system.activity`) | Rhythmus | ✅ geübt (Experience-Detektor) |
| Disk (`system.disk`, `disk.trend`) | Trend (steigt/fällt/stabil) | ✅ **geübt** (`disk.trend`, neben dem Threshold-Belief) |
| Temperatur (`system.temperature`, `system.thermal`) | Korrelation + Widerspruch | ✅ **geübt** (`system.thermal`, self-kalibriert) |
| Prozess-Ereignisse | Seltenheit / diskret | ❌ **nicht gebaut** |
| Selbstbeobachtung (Ledger) | Selbstreflexion | ❌ **nicht gebaut** |
| `system.network`, `system.clock` | Self-Operation (Schwellwert/binär) | ✅ gebaut (seit Urplan) |
| `repo.activity`, `repo.churn` | Rhythmus/Intensität (deine Arbeit) | ✅ gebaut (neue Kategorie) |
| `weather.trend` | Trend auf **externem** Material | ✅ gebaut (erster Internet-Sensor, Membran) |

**Ehrliche Bilanz:** Geübt sind heute **Schwellwert**, **Rhythmus**, **Trend**
(`disk.trend`, jetzt auch `weather.trend`) und **Korrelation** (`system.thermal`),
auf mehreren Subjekten (Maschine, Betrieb, deine Arbeit, und neu: die Welt).
**Noch offen: nur Seltenheit** (diskrete Ereignisse). Der ursprüngliche Satz
„decken jede deterministische Erkenntnisform ab" war Plan, nicht Stand — jetzt
fehlt zum Abschluss nur noch *eine* Form. Die Schwellen sind self-kalibriert
(eigene Perzentile/Streuung, keine Vorgabe). **Nicht mehr alles offline:** mit
`weather.trend` fließt erstmals ein Internet-Wert — aber nur über die Membran,
nur eine Zahl, der Kern bleibt rein.

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

**Erst lokal komplett, dann nach außen — bewusst übersteuert.** Die
Grundausbildung ist über die *Erkenntnisformen* definiert, nicht über eine feste
Sensor-Zahl. Lokal fehlt nur noch **Seltenheit** (Trend seit `disk.trend`,
Korrelation seit `system.thermal`). Der Urplan sah den ersten externen Sensor
*nach* dieser letzten Form vor — und als naheliegenden nicht Wetter, sondern
**Markt** (er läuft direkt auf Antizipation/Trading zu). Wir sind die Tür
trotzdem **bewusst früher** durchgegangen: mit **Wetter**, eine lokale Form noch
offen. Grund: das Material eines idle Pi ist zu dünn, um die Mechanik weiter zu
fordern, Wetter ist eine eindeutige Zahl (gut zum Üben) und die fehlende Variable
für `system.thermal`. **Markt bleibt bewusst der *nächste* externe Schritt** —
mit der harten Leitplanke: Beobachtung/Belief ja, **niemals Auto-Trade** auf
Backtest-Konfidenz.

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
- *Markt* — extern (HTTP) und Antizipation/Trading. Bewusst der nächste externe
  Schritt, mit Anti-Auto-Trade-Leitplanke. (*Wetter* ist seit `weather.trend` das
  erste externe Material — siehe oben.)
- *Text, Sprache, Bild-Bedeutung* — brauchen ein Modell. Model Era.

---

*Langweilig im Inhalt, perfekt im Lehrwert: Die Wahrheit ist immer eindeutig,
also sieht man, ob die Mechanik wirklich funktioniert.* 🧬
