# GENUS · Roadmap

> **Status:** aktuelle Zukunftsplanung
>
> **Stand:** 13. Juli 2026
>
> **Enthält:** Reihenfolge, Abhängigkeiten und Definition of Done – keine
> Bauchronik und keine flüchtigen Live-Zahlen

Die Roadmap führt vom gehärteten Kern zum persönlichen, lernenden Begleiter.
Der aktuelle Ausgangspunkt steht in [NOW.md](NOW.md), ausgelieferte Etappen im
[history/BUILD_JOURNAL.md](history/BUILD_JOURNAL.md).

## Nordstern

GENUS wächst vom Wahrnehmen über Wissen und Verstehen zum Können und Erschaffen –
und wendet diese Fähigkeiten schließlich kontrolliert auf sich selbst an. Jede
Erkenntnis und jede Veränderung bleibt belegbar, prüfbar und im Dienst des
Menschen.

## So wird diese Karte benutzt

1. Es gibt genau **einen aktiven Entwicklungsschritt**. Reine Mess- und
   Sicherungsarbeiten dürfen daneben laufen, solange sie den Zustand nicht
   konkurrierend verändern.
2. Ein Schritt beginnt mit Material, Ereignisvertrag, Risiko und Messplan.
3. Er endet erst, wenn seine Definition of Done im Repo **und** auf dem Pi gilt.
4. Neue Erkenntnis darf die Route ändern. Die Leitplanken ändern sich nicht
   stillschweigend.

## Die Abhängigkeiten

```text
H0 Betriebsbeweis ──┬──> H1 Begleiter ──> H2 Fähigkeitsloop ──> H3 Erschaffen
                    │                              │
                    └──> externer Anker            └──> H4 Markt-Membran

H3 + geklärte Isolation/Löschung/Governance ─────────> H5 Föderation
```

Die Horizonte sind keine Versionsnummern. Ein später Horizont darf erforscht,
aber nicht als Produktpfad geöffnet werden, bevor seine Abhängigkeiten grün sind.

## H0 · Betrieb beweisen

**Ziel:** Der gehärtete Kern zeigt unter realer Last, dass Ereignisfluss, Wahrheit und
Betriebsgrenzen beobachtbar bleiben.

### H0.1 · 24/48/72-Stunden-Betriebs- und Ereignisprofil

**Abhängigkeit:** keine.

**Arbeit:** Ledger-, DB- und WAL-Veränderung pro Ereignistyp, kontrollierter Herkunftsfamilie und
aus dem Ereignistyp abgeleitetem Produzenten-Proxy messen; neue Evidenz,
notwendige Betriebsspur und vermeidbare Wiederholung unterscheiden; alte Flutfenster vom neuen
Normalbetrieb trennen; Budget und Alarmgrenzen ableiten. Das Ledger soll nicht um seiner selbst
willen wachsen.

**Definition of Done**

- drei vergleichbare Messpunkte mit gleicher Methodik
- Top-Verursacher nach Ereignistyp und Quelle ausgewiesen
- Eventrate, Dateiwachstum und flüchtige WAL-Dateiallokation getrennt
- jeder wesentliche Zuwachs als Erkenntnis, notwendige Betriebsspur oder vermeidbare Last bewertet
- begründetes Tagesbudget plus Warn- und Eingriffsschwelle dokumentiert
- Messung verändert weder Ledger noch Projektionen
- Leitmaß ist mehr belegbares Können pro gespeichertem Ereignis, nicht eine höhere Ereigniszahl

### H0.2 · Externen Anker etablieren

**Abhängigkeit:** gültiger lokaler Anker.

**Arbeit:** Anker außerhalb des Pi verwahren und die Prüfung vom externen Zeugen
bis zum lokalen Siegelkopf üben.

**Definition of Done**

- mindestens eine getrennte, zugriffsgeschützte Verwahrung
- Hash, `core_id`, Eventposition und Siegelkopf read-only verifiziert
- Abruf- und Prüfablauf dokumentiert und einmal erfolgreich geprobt
- Rotation erzeugt keine Ereignisse im Produkt-Ledger

### H0.3 · Umstrittenen `system.load`-Belief klären

**Abhängigkeit:** ausreichend Beobachtungsmaterial aus H0.1.

**Arbeit:** Stütz- und Gegenbelege, Zeitfenster, Sensordefinition und Schwellen
untersuchen; Semantik korrigieren oder bewusst Enthaltung erhalten.

**Definition of Done**

- der Widerspruch ist mit reproduzierbarer Abfrage erklärt
- Entscheidung beruht auf Evidenz, nicht auf gewünschtem Zustand
- Regressionstest deckt Stützung, Widerspruch und Unsicherheit ab
- Replay bleibt event- und projektionsstabil

### H0.4 · Gesprächsdateien und historische Logs bewusst behandeln

**Abhängigkeit:** keine; Löschung braucht eine ausdrückliche Betriebsentscheidung.

**Arbeit:** Umfang und Alter alter Telegram-Journal-/Legacy-Logs sowie der aktuellen begrenzten
Korrektur- und optionalen Wortlern-Dateien nur über Metadaten erfassen, Retention/Opt-in
entscheiden und anschließend gezielt löschen oder geschützt archivieren.

**Definition of Done**

- Bestandsaufnahme nennt Pfadklasse, Zeitraum, Größe und Rechte, nicht den Gesprächsinhalt
- Ronny entscheidet Retention, Löschung oder geschützte Archivierung ausdrücklich
- Ausführung ist protokolliert und anschließend read-only verifiziert
- neue Telegram-Journalzeilen enthalten weiterhin nur Betriebsmetadaten, insbesondere Länge
  und Fehlerklasse — keinen Text und keine Nutzer-ID

## H1 · Der alltagstaugliche Begleiter

**Abhängigkeit:** H0 ohne unkontrolliertes Wachstum oder ungeklärte
Betriebsgefährdung.

**Ziel:** Antworten fühlen sich persönlich und zusammenhängend an, ohne die
epistemischen Grenzen zu verwischen.

### H1.1 · Kontextgedächtnis

- relevanten statt nur ähnlichen Kontext auswählen
- Zeit, Quelle, Beziehung, Aktualität und Unsicherheit gemeinsam gewichten
- Privates nicht über Gesprächs- oder Nutzergrenzen tragen
- persönliche Inhalte aus dem append-only Ledger in einen isolierten, exportierbaren und
  tatsächlich löschbaren Memory-Vault überführen
- `vergiss`, Retention und Löschbestätigung als einen gemeinsamen Vertrag bauen

### H1.2 · Seele der Antworten

- Antwortbogen aus Absicht, belegtem Kontext, Unsicherheit und hilfreichem
  nächsten Schritt bilden
- Persönlichkeit als kontrollierte Darstellungsschicht halten
- Modellformulierungen niemals als neue Evidenz zurückschreiben

**Pilotstand:** Der erste geschlossene Vertikalschnitt ist gebaut. Definitionen und
Beziehungen tragen `AnswerDraft` mit Claims und vorhandener Provenienz; ein kleiner
`DialogueFrame` führt Absicht, strukturelle Ankerkontinuität und kontrollierte
Würfel-Belegung in den treuen
Renderer. Telegram erzeugt erst nach belegter Zustellung ein typisiertes
`ResponseOutcome`; reine 👍-/👎-Nachrichten und enge Intent-Korrekturen werden über die
Response-ID replaybar verknüpft.

Das ist bewusst noch nicht H1-fertig: Die übrigen Handler liefern weiter Legacy-Strings,
ein vollständiger Diskursplan fehlt, Feedback ändert keine Strategie automatisch und der
Telegram-Bezug zur letzten Response-ID überlebt keinen Prozessneustart. Der löschbare
Memory-Vault bleibt Teil von H1.1. Ebenso fehlt noch eine löschbare Edge-Outbox: Scheitert
die Outcome-Persistenz erst nach einer belegten Zustellung, bleibt diese Antwort im Pilot
zugestellt, aber ungemessen.

**Definition of Done für H1**

- ein kuratiertes Set realer Alltagssituationen ist wiederholbar bewertet
- jede Tatsachenbehauptung ist belegt oder ausdrücklich als unsicher erkennbar
- Korrekturen wirken im nächsten passenden Dialog und sind replaybar
- sensible oder irrelevante Erinnerungen werden nachweislich nicht eingeblendet
- persönliche Episoden können exportiert und physisch gelöscht werden; eine Retraktion allein
  gilt nicht als „vergessen“
- Ronny bestätigt, dass Ton und Nützlichkeit im Alltag tragen

## H2 · Der generalisierende Fähigkeitsloop

**Abhängigkeit:** H1 liefert verständliche Rückfragen, Kontext und Feedback.

**Ziel:** GENUS schließt wiederkehrende Fähigkeitslücken durch geprüfte,
übertragbare Werkzeuge – nicht durch eine Sammlung von Sonderfällen.

```text
Lücke → Inquiry → Plan → Vorschlag → Sandbox → Test → Freigabe
      → Ausführung → Wirkungsmessung → behalten, verbessern oder zurückrollen
```

**Definition of Done**

- jeder Übergang besitzt ein definiertes Ereignis oder eine abgeleitete Projektion
- Vorschlag, menschliche Entscheidung und Ausführung sind technisch getrennt
- Sandbox hat feste Zeit-, Speicher-, Netzwerk- und Dateigrenzen
- mindestens drei strukturell verschiedene Aufgaben nutzen denselben Loop
- Erfolg misst Generalisierung und Laufzeitwirkung, nicht nur Testgrün
- Fehlschlag und Rollback sind absichtlich getestet und vollständig nachvollziehbar
- kein selbst erzeugter Code wird automatisch gemergt oder privilegiert ausgeführt

## H3 · Erschaffen mit Beweis

**Abhängigkeit:** H2 ist über mehrere Aufgaben stabil.

**Ziel:** GENUS erzeugt Werkzeuge, Erklärungen und Code, deren Zweck, Grenzen und
Wirksamkeit er selbst prüfen kann.

**Definition of Done**

- jedes Artefakt hat Bedarf, Herkunft, Prüfkriterien und Besitzer
- deterministische Prüfer bewerten, was deterministisch prüfbar ist
- offene Qualitätsfragen werden dem Menschen sichtbar übergeben
- Live-Wirkung fließt als Evidenz zurück, nicht als selbsterteiltes Lob
- veraltete Fähigkeiten lassen sich deaktivieren und reproduzierbar ersetzen

## H4 · Markt- und Außenwelt-Membran

**Abhängigkeit:** H0-Ereignisbudget und H2-Governance sind belastbar.

**Ziel:** externe Signale beobachten und Entscheidungen simulieren, ohne Wahrheit,
Interesse und Handlung zu vermischen.

**Definition of Done**

- Quellenvertrag, Provenienz, Aktualität und Ausfallverhalten sind explizit
- Simulation und echte Handlung sind strukturell getrennt
- Bilanz berücksichtigt Kosten, Unsicherheit und Gegenfaktum
- kein echtes Geld wird automatisch bewegt
- Membranverlust beeinträchtigt weder Replay noch lokalen Kernbetrieb

## H5 · Föderation

**Abhängigkeit:** H3 ist stabil; Isolation, Einwilligung, Export und Löschung sind
vorher gelöst.

**Ziel:** ein getrennt verantwortbarer Kern pro Person oder Charakter – ohne
unbeabsichtigtes gemeinsames Gedächtnis.

**Definition of Done**

- Daten, Schlüssel, Prozesse und Sicherungen sind strukturell isoliert
- Einwilligung, Export, Widerruf und Löschung sind praktisch getestet
- Austausch erfolgt nur über explizite, belegte Protokolle
- Ausfall oder Kompromittierung eines Kerns greift nicht auf andere über
- besondere Schutzregeln für Kinder sind technisch erzwungen, nicht nur versprochen

## Das Gate vor jedem Merge

Jeder Roadmap-Schritt beantwortet vor seiner Freigabe:

- Welches Material rechtfertigt ihn?
- Welches Ereignis hält Input oder Transition fest?
- Ist der abgeleitete Zustand vollständig rebuildbar?
- Bleibt Replay ohne neue Events und ohne Drift?
- Wird Confidence berechnet statt als Wahrheit gespeichert?
- Sind Root, User, Modell, Netzwerk und Sandbox sauber begrenzt?
- Welche Metrik zeigt Nutzen, Wachstum und möglichen Schaden?
- Wie wird gestoppt oder zurückgerollt?
- Welche Dokumente und Tests machen die Änderung verständlich?

Wenn eine Antwort fehlt, ist der Schritt nicht klein genug oder noch nicht reif.

---

**Aktive Baulinie:** H1.2 vom Vertikalschnitt zum kuratierten Alltagstest reifen.
Die read-only H0.1-Messreihe darf nach Regel 1 parallel weiterlaufen; sie öffnet keinen
zweiten verändernden Produktpfad.
