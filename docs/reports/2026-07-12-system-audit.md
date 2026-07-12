# GENUS Systemaudit · Morphologie und SWOT

> **Status:** datierter Befund · **Build-Autorität:** keine
> **Auditdatum:** 2026-07-12 · **Pi-Härtungsbasis:** `2e59b39`
> **Repo-Nachtrag:** neuer Dokumentationskanon und read-only Anchor-Diagnose
> **Zweck:** den Gesamtzustand verdichten, Spannungen sichtbar machen und die
> nächsten Entscheidungen begründen

## Urteil vorweg

GENUS ist kein unfertiger Chatbot, sondern bereits ein ungewöhnlich belastbarer
**epistemischer Organismus**: Ereignisse, Herkunft, Unsicherheit, Replay und
menschliche Freigabe bilden einen echten Kern. Der Raspberry Pi ist dabei nicht
nur Demo-Hardware, sondern ein dauerhaft beobachteter Lebensraum.

Die zentrale Schwäche liegt nicht mehr im Fundament. Sie liegt im Übergang von
**vorhandener Mechanik** zu **spürbar generalisierendem Können**. GENUS kann viel
belegen, einordnen und absichern; der vollständige Kreis von erkannter Lücke über
Werkzeugbau bis zur gemessenen Live-Wirkung ist noch nicht allgemein geschlossen.

Die strategische Folgerung lautet deshalb:

> Nicht mehr Breite anbauen. Erst den Wachstumsloop an wenigen verschiedenartigen
> Aufgaben vollständig schließen und seine Wirkung im Dauerbetrieb messen.

## Evidenzbasis und Grenzen

| Quelle | Was sie belegt | Grenze |
|---|---|---|
| Code und Tests | Kernverträge, Router, Replay, Gates und Regressionen | Tests beweisen nur explizit modellierte Eigenschaften |
| [Härtungsaudit](2026-07-12-hardening-audit.md) | Repo-/Pi-Grenzen, Ledger, Siegel, Root/User, Live-Dienste | datierter Snapshot, kein Kernel- oder Hardware-Pentest |
| [NOW](../NOW.md) | verifizierter Ausgangspunkt und aktive Prioritäten | Live-Zahlen werden nicht automatisch aktualisiert |
| [Architektur](../ARCHITECTURE.md) | heutige Invarianten und Abhängigkeiten | Vertrag, kein Messbericht |
| [Wachstumsaudit](2026-07-03-growth-audit.md) | Diagnose des früheren Spezialfall-Wachstums | historischer Stand vor der Härtungsrunde |
| Raspberry-Pi-Prüfung | 1.253 Linux-Tests, Replay, Integrität, Siegel und Dienste | genau der geprüfte Pi-Stand, keine allgemeine Plattformgarantie |

Nach der Dokumentationsneuordnung und Anchor-Nachhärtung liefen lokal 1.257 Tests;
darunter sind sechs neue Prüfungen gegen Dokumentations-/Event-Vertragsdrift sowie
eine neue Anchor-Diagnose-Regression. Diese Windows-Zahl ist nicht direkt mit dem
datierten Linux-Nachweis gleichzusetzen.

Die Dokumentationsprüfung deckte nach der Pi-Baseline noch eine Restnaht auf:
`genus ledger anchor verify` verwendete den schreibfähigen statt des diagnostischen
DB-Connectors und konnte bei einem falschen Pfad eine Streu-Datenbank anlegen. Der
aktuelle Repo-Nachtrag öffnet diesen Befehl strikt read-only und testet, dass ein
fehlender Pfad keine Datei erzeugt. Die Pi-Zahlen in diesem Report bleiben bewusst
der unveränderte Baseline-Snapshot.

## Morphologische Analyse I · der Systemkörper

Eine morphologische Analyse zerlegt GENUS in voneinander unterscheidbare Achsen.
Erst das Kreuzprodukt zeigt, ob eine scheinbar starke Eigenschaft nur in einer
Ecke gilt.

| Achse | Mögliche Ausprägungen | GENUS heute | Urteil |
|---|---|---|---|
| Wahrheitsbasis | flüchtiger Kontext · mutable DB · Event-Ledger | append-only Event-Ledger mit Herkunft | stark |
| Zustand | direkt gespeichert · Cache · Projektion | rebuildbare Projektionen | stark |
| epistemischer Status | Fakt · Belief · Inquiry · Proposal | ausdrücklich getrennte Zustände | stark |
| Schlussform | freie Modellantwort · Regel · Beweisgraph | Regeln und nachvollziehbare Ableitungen; Modell am Rand | stark, aber noch begrenzte Reichweite |
| Gedächtnis | Chatverlauf · Episode · Semantik | Graphwissen plus vernetzte Episoden; Tagespuffer in Membran | tragfähig, Relevanzwahl noch unreif |
| Handlungsgrad | lesen · intern schreiben · außen wirken | Lesen und gegatete interne Änderung; Außenwirkung eng begrenzt | absichtlich konservativ |
| Autonomie | autonom · policy-gesteuert · menschlich gegatet | Proposal, Review und Ausführung getrennt | stark für Sicherheit, langsam für Wachstum |
| Lernform | Parametertraining · Musteraddition · Regel-/Werkzeuggewinn | Erfahrung, Proposals, Werkzeuge und Ziele vorhanden | Loop nur teilweise generalisiert |
| Habitat | Prozess · Einzelhost · verteiltes System | lokaler Pi mit begrenzten Membranen | robust lokal, Einzelknotenrisiko |
| Selbstbezug | keine · Statuswissen · Selbständerung | Ziele, Lücken und Werkzeuge sichtbar; Änderungen gegatet | guter Keim, noch keine geschlossene Selbstverbesserung |

### Was das Kreuzprodukt offenlegt

1. **Gläsern ist nicht automatisch klug.** GENUS kann eine enge Operation sehr
   sauber beweisen und trotzdem an einer neuen Aufgabenform scheitern.
2. **Persönlich ist nicht automatisch erinnernd.** Episoden existieren; die
   situationsgerechte Auswahl und Gewichtung entscheidet erst über erlebte Nähe.
3. **Sicher ist nicht automatisch verfügbar.** Ledger und Siegel schützen
   Integrität, aber ein einzelner Pi bleibt ein einzelner Ausfallpunkt.
4. **Selbstwissen ist nicht Selbstumbau.** Ziele und Fähigkeitslücken sind im
   System sichtbar; Werkzeugentwurf, Sandbox, Freigabe und Wirkungsmessung müssen
   noch als allgemeiner Kreis zusammenfinden.

## Morphologische Analyse II · der Wachstumsloop

| Phase | Leitfrage | Stand | Fehlender Beweis |
|---|---|---|---|
| Wahrnehmen | Welches Material ist neu? | gebaut | Produzentenbudget über 24/48/72 Stunden |
| Einordnen | Welche Art Situation liegt vor? | gebaut, teils modellgestützt | robuste Segment- und Relevanzwahl über breitere Fälle |
| Zweifeln | Was fehlt oder widerspricht sich? | gebaut | Priorisierung nach späterem Nutzen statt nur Auftreten |
| Planen | Welche Operation könnte die Lücke schließen? | teilweise | domänenübergreifend wiederverwendbarer Planer |
| Entwerfen | Welches Werkzeug oder Rezept wird gebraucht? | Keime vorhanden | konsistenter allgemeiner Entwurfspfad |
| Prüfen | Ist der Entwurf sicher und wirksam? | starke Einzelgates | feste Sandbox- und Ressourcenverträge für neue Werkzeuge |
| Freigeben | Wer darf die Änderung legitimieren? | gebaut | gute UX für begründete Entscheidungen |
| Ausführen | Wie wirkt die freigegebene Änderung? | eng begrenzt | allgemeiner, rückrollbarer Ausführungspfad |
| Beobachten | Hat sie live geholfen oder geschadet? | teilweise | einheitliche Wirkungsmetriken und Gegenfaktum |
| Behalten | Wird sie bestätigt, verbessert oder entfernt? | konzeptionell vorhanden | wiederholter End-to-End-Nachweis |

Der Engpass liegt damit nicht in einer einzelnen fehlenden Funktion. Er liegt in
den **Übergängen** ab Planen. Genau deshalb priorisiert die [Roadmap](../ROADMAP.md)
zuerst Betriebsbeweis und Begleiter, dann den generalisierenden Fähigkeitsloop.

## SWOT

| Stärken | Schwächen |
|---|---|
| Ledger, Provenienz und Replay sind echte Architektur, keine Präsentationsfolie. | Der allgemeine Fähigkeitsloop ist noch nicht Ende-zu-Ende bewiesen. |
| Unsicherheit, Vorschlag, Entscheidung und Handlung bleiben getrennt. | Viele Fähigkeiten sind historisch aus Einzelproblemen entstanden und noch nicht auf Übertragbarkeit bewertet. |
| Pi-Betrieb, Root/User-Grenze, Siegel und Integrität wurden live geprüft. | Einzelknoten, lokaler Anchor-Tail und Restore-Praxis begrenzen Resilienz. |
| Der Kern ist klein, deterministisch und mit breiter Regression geschützt. | Kontextrelevanz und „Seele der Antworten“ bleiben hinter der Mechanik zurück. |
| Ziele, Lücken und Werkzeuge werden zunehmend selbst zum Material von GENUS. | Doku und Zustandszahlen waren bisher stark handgepflegt und driftanfällig. |

| Chancen | Bedrohungen |
|---|---|
| Ein geschlossener Fähigkeitsloop kann viele Spezialpfade durch wenige Operationen ersetzen. | Neue Regexe, Handler und Produzenten könnten wieder lokales Testgrün statt Generalisierung optimieren. |
| Das bestehende Gedächtnis kann zu einem wirklich persönlichen Begleiter werden, ohne Wahrheit zu erfinden. | Ein kompromittierter Nutzer, Pi-Verlust oder ungesicherter Ledger-Tail bleibt trotz lokaler Härtung relevant. |
| Externe Anchors und geübte Restores können Integrität und Verfügbarkeit deutlich stärken. | Modelle oder Netzwerkquellen könnten schleichend Autorität gewinnen, wenn Membrangrenzen verwässern. |
| Generierte Fakten und neue Doku-Drifttests senken die Pflegekosten. | Eventwachstum kann erneut unbemerkt Kosten und Laufzeit dominieren. |
| Die klare Kern-/Membranform erlaubt später Markt- oder Föderationsräume. | Zu frühe Föderation oder Außenhandlung würde Datenschutz, Löschung und Governance überfordern. |

## Die schärfsten Spannungen

### 1. Beweisbarkeit ↔ Nützlichkeit

Die Governance ist eine Stärke. Wenn sie aber nur verhindert und nicht schnell
zu einem überprüften nächsten Schritt führt, erlebt der Nutzer Vorsicht statt
Intelligenz. Das Gegenmittel ist kein lockereres Gate, sondern ein besserer,
kleinerer Weg durch das Gate.

### 2. Gedächtnismenge ↔ passende Erinnerung

Mehr Episoden sind kein besseres Gedächtnis. Relevanz, Zeitpunkt, Quelle,
Beziehung und Privatsphäre müssen gemeinsam entscheiden, ob eine Erinnerung in
diesem Moment hilft.

### 3. Lokale Souveränität ↔ Resilienz

Der Pi bewahrt Nähe und Kontrolle. Externe Bezeugung und getestete Sicherungen
sind trotzdem nötig, damit lokale Souveränität nicht zum einzelnen Verlustpunkt
wird.

### 4. Selbstentwicklung ↔ Selbstbestätigung

GENUS darf eigene Lücken und Entwürfe formulieren. Ob eine Änderung wirklich
trägt, müssen unabhängige Tests, menschliche Entscheidung und beobachtete
Laufzeitwirkung zeigen.

## Prioritäten aus dem Audit

1. **Wachstum messen:** 24/48/72-Stunden-Profil, Produzenten und Budget.
2. **Extern bezeugen:** Anchor getrennt verwahren und Restore-Prüfung üben.
3. **Semantik klären:** den umstrittenen `system.load`-Belief evidenzbasiert
   entscheiden.
4. **Begleiter vertiefen:** Relevanzwahl und Antwortbogen an realen Situationen
   messbar verbessern.
5. **Loop schließen:** drei strukturell verschiedene Aufgaben durch denselben
   Plan-/Werkzeug-/Gate-/Wirkungskreis führen.

## Was ausdrücklich nicht empfohlen wird

- kein Rewrite des gesunden Kerns;
- keine neue Sensor- oder Eventbreite ohne Budget und Verbraucher;
- kein automatisches Mergen oder privilegiertes Ausführen selbst erzeugten Codes;
- keine Vermischung quarantänisierter und produktiver Ledger;
- keine Föderation, bevor Isolation, Einwilligung, Export und Löschung praktisch
  bewiesen sind.

## Schluss

GENUS besitzt bereits etwas Seltenes: eine überprüfbare Haltung zum eigenen
Wissen. Die nächste Reifestufe entsteht nicht durch mehr Behauptungen, sondern
durch einen einzigen wiederverwendbaren Kreislauf, der **Lücke, Entwurf,
Freigabe, Wirkung und Lernen** zuverlässig verbindet.

Der operative Startpunkt bleibt [H0 in der Roadmap](../ROADMAP.md#h0--betrieb-beweisen).
Die Zielsetzung selbst bleibt im [Charter](../CHARTER.md) stabil.
