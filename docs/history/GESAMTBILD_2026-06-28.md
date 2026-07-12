# GENUS — GESAMTBILD

> **Status:** Historischer Snapshot vom 2026-06-28 · **Autorität:** nicht kanonisch. Für das heutige Gesamtbild gelten [Dokumentationsindex](../README.md), [NOW](../NOW.md), [Roadmap](../ROADMAP.md) und [Architektur](../ARCHITECTURE.md).

> Der Überblick über allem. Was GENUS ist, wohin es will, wie wir hinkommen.
> Dieses Dokument **synthetisiert und verweist** — die Details leben in den
> Einzeldokumenten. Wenn etwas hier und dort steht, gilt das Einzeldokument.

---

## Was ist GENUS?

Ein **governiertes Erkenntnissystem**: es verwandelt Beobachtungen in
Erfahrungen und Erfahrungen in Verbesserungsvorschläge. Es nimmt wahr, bildet
nachvollziehbare Überzeugungen, revidiert sie an der Wirklichkeit, erkennt
Muster, schlägt vor.

**Kein** Chatbot, **kein** LLM-Wrapper, **kein** "Sprachmodell mit Speicher".
Der Unterschied liegt nicht in der Architektur, sondern darin, **wo die
Erkenntnis entsteht** — bei einem Chatbot undurchsichtig im Modell, bei GENUS
in einem gläsernen Kern, in dem jede Überzeugung auf ihre Belege zurückführbar
ist.

**Das Fundament in vier Sätzen:** Ein append-only Ledger ist die Wahrheit,
alles andere ist daraus rekonstruierbare Projektion. GENUS glaubt, es weiß
nicht. Confidence wird berechnet, nie gespeichert. Es lernt gläsern (Regeln,
die man lesen kann), nicht blind (Gewichte, die niemand sieht).

**Auflösung A** — die Kern-Entscheidung: GENUS ist der deterministische,
governierende Kern. LLMs und Charaktere sind *Bewohner*, nicht sein Inneres.
Der Kern denkt offline und rein; Modelle treten später als Organe hinzu, deren
Output nur als Evidence einläuft.

→ technische Regeln & DNA: `../ARCHITECTURE.md`, `../EVENT_CONTRACT.md`

---

## Was ist die Zielsetzung?

Ein **multifunktionales, lernendes System** — ein "digitales Wesen", das aus
Erfahrung lernt und neue Fähigkeiten ausbildet. Erst für mich, dann Familie,
später Freunde, Gruppen, vielleicht Organisationen.

**Das tiefere Ziel** ist nicht ein Thema, sondern die **Physik der
Erkenntnis**: wahrnehmen, glauben, zweifeln, revidieren, Muster sehen,
vorhersagen, lernen. Themen (Trading, Schach, Fahrpläne) sind Trainingsgelände.

**Die Anwendungen** wachsen später auf dem Kern: Trading als erster Use-Case;
Charaktere (Hausaufgabenhelfer, Begleiter, DnD-Meister, je Familienmitglied)
als LLM-Bewohner (das LLM als gedeckelte Stimme am Rand, kein Ziel); und der Anspruch, dass GENUS selbständig neue
Funktionen entwickelt.

**Die ehrliche Haltung:** eine *Modelleisenbahn* — gebaut mit Hingabe, langsam
und stetig, weil das Bauen selbst das Schöne ist. Grenze: Sobald Charaktere für
wartende Menschen real werden (ein Kind, das einen Helfer erwartet), wird aus
"Spiel" ein "Versprechen". Die Familie ist der Punkt, an dem der Maßstab
wechselt. GENUS wird *wirklich etwas* — ob je ein "Geist" im vollen Sinn, weiß
heute niemand; das entdeckt man beim Bauen.

→ Vorhersage-Use-Case: `../research/ANTICIPATION.md`
→ visuelle Vision (später): `../research/VISUAL_THINKING.md`

---

## Wie kommen wir da hin?

**Zwei Prinzipien ordnen alles:**

1. **Material vor Maschinerie.** Kein Verarbeitungs-Core ohne Input, der ihn
   rechtfertigt. Tiefer: Material macht die Physik überhaupt erst sichtbar — man
   entdeckt Bausteine, indem man Material anfasst und sieht, *wo das Schema
   bricht.*
2. **Beobachtbarkeit neben Maschinerie.** Baue nichts, das du nicht sofort
   inspizieren kannst. Darum kommt Query früh.

**Zwei Achsen:** Material wird *breiter* (Habitat → Arbeit → Sprache),
Maschinerie wird *tiefer* (Lifecycle → Experience → State → Governance →
Maturation). Maschinerie wird immer auf dem einfachsten Material zuerst
bewiesen.

**Material wird nach Physik gewählt, nicht nach Thema** — jeder Sensor übt eine
Erkenntnisform. Externe Sensoren sind *Augen, die wahrnehmen, aber nie urteilen*.

→ die Reihenfolge Schritt für Schritt: `../ROADMAP.md`
→ welches Material welche Erkenntnisform übt: `../design/BASIC_TRAINING.md`
→ der Vertrag für jeden Sensor: `../design/SENSOR_PRINCIPLE.md`

---

## Die Zielform: konstitutionelle, föderierte BDI

Zwei unabhängige Analysen (Physik-Lücken und Architektur-Morphologie) zeigen
auf dieselbe Endform — das stärkste Indiz, dass die Richtung stimmt:

**GENUS ist keine Intelligenz — es ist eine Verfassung für Intelligenzen.**
Die Intelligenz wird importiert (Regeln, später Modell-Organe); der Kern
diszipliniert sie: Gedächtnis, Herkunft, Kalibrierung, Gates, Audit. GENUS
tauscht *Fähigkeit-jetzt* gegen *Vertrauen-für-immer* — das ist der bewusste
Trade, und für das Ziel (familientaugliche, auditierbare Kognition) der
richtige.

**Föderation statt Multi-Tenancy.** Nicht *ein* Kern mit vielen Charakteren,
durch Policies getrennt — sondern **ein kleiner Kern pro Charakter/Person**,
mit Austausch über explizite Verträge. Isolation ist dann *strukturell*
(getrennte Datenbanken), nicht verhaltensbasiert (Regeln): Ein Bug kann keine
Grenze überschreiten, die als getrennte Datei existiert. Abgrenzung ist der
Default, Kennen der bewusste Akt. Das Netzwerk kann auf **einem Gerät**
entstehen (mehrere SQLite-Dateien, ein Prozess) und später ohne Umbau auf
Geräte verteilt werden. Bindend wird die Entscheidung erst bei den Charakteren —
ab jetzt gilt nur die Regel: *nichts schreiben, das stillschweigend annimmt,
es gäbe nur eine Datenbank.* Zwischen Kernen gilt das Sensor-Prinzip: Ein
fremder Kern ist ein Auge, sein Beitrag ist Observation, nicht Wahrheit.

**Offene Punkte aus dem Projekt-Audit** (zu lösen vor der jeweiligen Phase):
- *Löschung vs. Append-only* — vor der Familienphase: ein unveränderlicher
  Ledger kollidiert mit dem Recht, dass Daten über eine Person verschwinden.
  Lösungsrichtung: Crypto-Shredding (Payloads pro Person verschlüsseln,
  Schlüssel löschen = unlesbar, Ledger strukturell intakt).
- *Snapshots* — bevor der Ledger groß wird: Replay-Zeit wächst linear,
  Checkpoints nötig.
- *Uhren-Disziplin* — vor dem Pi-Dauerbetrieb: ohne RTC driftet die Zeit, und
  falsche Zeitstempel zerstören genau die zeitlichen Muster, die das
  wertvollste Material sind.
- *Model-Vertrag-Spike* — vor v1.0: die wichtigste ungetestete Behauptung
  (LLM-Output nur als Evidence, gedeckelt, gegated) einmal klein beweisen,
  statt das größte Integrationsrisiko ans Ende zu schieben.
- *Projekt-Governance* — keine neuen Konzeptdokumente zwischen zwei Builds;
  ein externer, nicht-investierter Reviewer ist mehr wert als weitere
  KI-Runden.

---

## Was wir noch nicht sehen

Eine morphologische Analyse zeigt: GENUS bewohnt heute eine **Ecke** des
Erkenntnis-Raums. Die Trennlinie quer durch alles ist **Empfangen gegen
Handeln** — GENUS ist heute ein **Auge**, noch kein **Geist**. Ganze Familien
epistemischer Operationen (sich prüfen, Wissen organisieren, wollen, sich
selbst kennen, anderen begegnen) sind unberührt. Und die Karte selbst ist durch
unser Einteilungsprinzip begrenzt — die Physik ist ein Horizont, der mitwandert,
kein Eingangstor.

→ die ganze Analyse, Familien, Leerstellen, ehrliche Grenzen: `../research/EPISTEMIC_PHYSICS.md`

---

## Die Dokumenten-Familie

Die aktuelle Regalordnung und Autoritaet der Dokumente steht in
`README.md` in diesem Ordner. Dieses Gesamtbild bleibt Synthese und Navigation,
nicht die Quelle fuer technische Einzelvertraege.

```
GESAMTBILD_2026-06-28.md   dieses Dokument — historischer Snapshot (oben)
│
├─ genus_core_map.html     das Zielsystem als Bild (Reifegrad-Karte)
│
├─ Identität & Regeln
│   ../ARCHITECTURE.md      die Prinzipien & DNA (kanonisch)
│   ../EVENT_CONTRACT.md    die Event-Typen im Detail
│
├─ Der Weg
│   ../ROADMAP.md           die Reihenfolge, Schritt für Schritt (kanonisch)
│   ../design/BASIC_TRAINING.md welches Material welche Form übt
│   ../design/SENSOR_PRINCIPLE.md der Vertrag für jeden Sensor
│
├─ Tiefere Erkenntnisformen
│   ../research/ANTICIPATION.md Vorhersage als eigene Phase
│   ../research/EPISTEMIC_PHYSICS.md Landkarte der Erkenntnisformen (wachsend)
│
└─ Verwahrte Vision
    ../research/VISUAL_THINKING.md visuelles Denken (LLM-Querschnitt)
```

**Konsistenz-Regel:** Jede Information hat *einen* Wohnort. Die Einzeldokumente
halten die Wahrheit; dieses Gesamtbild verweist nur. Ändert sich etwas, ändert
es sich im Einzeldokument — das Gesamtbild bleibt schlank und veraltet nicht.

---

*Die Karte ist das Zielsystem. Die Roadmap ist der Weg. Material vor
Maschinerie, nichts ohne Inspektion, ein bewiesener Schritt nach dem anderen.
Heute ein Auge — auf dem Weg, vielleicht, zu einem Geist.* 🧬🚂
