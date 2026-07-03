# GENUS — Ziel-Architektur & Stand-Audit

Stand: 2026-07-04, Version 2. Abgeleitet aus: der vollständigen Mechanismus-Analyse
aller 45 Quelldateien, dem Audit (`GENUS_AUDIT_2026_07.md`), zehn Angriffs-Runden
gegen den ersten Entwurf (drei Revisionen haben überlebt, siehe §2–§4), zwei
geprüften Ideen von Ronny (die Grenze §5, der Lernkreis §6) und einer ehrlichen
Nähte-Inventur (§8). Kein Rewrite-Plan — das konsequente Zu-Ende-Denken des
bereits Gesunden.

---

## 1. Das eine Prinzip — eine Substanz

GENUS erfindet keine neuen Arten von Ding. Es gibt **eine Substanz** und **drei
Arten von Ding** darauf:

- **Ein Prozess ist ein Event.** Jedes Geschehen wird zuerst als unveränderliches,
  hash-versiegeltes Event geschrieben (`ledger.append`). Die einzige echte
  Speicherung.
- **Alles Abgeleitete ist eine Projektion.** Beliefs, Relationen, Ziele, Fragen,
  Regeln — per Replay aus den Events neu berechenbar, ohne Informationsverlust.
- **Jedes Verhalten ist ein registrierter Eintrag** — und die Registrierungs-
  *Entscheidung* ist selbst ein Event (§4). Damit ist auch die Menge der
  Verhalten eine Projektion.

Diese Gleichheit ist die Stärke: „gleiches gleich, ungleiches ungleich" — zu Ende
gedacht. Wer sie nicht durchhält, baut vier Dispatch-Stile (der reale Befund, §10).

---

## 2. Zwei Kern-Primitive in Reihe: Deuten → Register

*(Revision 1 der Selbst-Diskussion: es ist nicht EIN Primitiv — es sind zwei.)*

Die fünf Dispatch-Stellen im Code sind nicht gleich. Drei sind exakte
Schlüssel-Treffer, zwei sind Klassifikation unscharfer Eingaben. Sie in ein
Primitiv zu pressen, wäre falsche Gleichmacherei. Die saubere Form ist eine
**Kette**:

```
Signal ──► DEUTEN ──► ein bekannter Schlüssel ──► REGISTER ──► geprüftes Verhalten
        (unscharf → Schlüssel)                (nachschlagen · prüfen · gaten)
```

- **Deuten**: unscharfe Eingabe (Freitext, Frage) → ein Schlüssel aus einem
  endlichen, bekannten Raum. Darf ein Modell nutzen (Organ), muss aber ehrlich
  scheitern können („off-grid"). `verstehen`/Deuter machen das heute schon richtig.
- **Register**: exakter Schlüssel → registrierter, beim Eintragen geprüfter,
  zur Laufzeit gegateter Eintrag. `werkzeug.py` (registrieren → prüfen →
  nachschlagen) ist der Prototyp.

`query.ask` vermischt heute beides in einer if/elif-Kette — das ist der
eigentliche Konstruktionsfehler dort, nicht die Kette an sich.

---

## 3. Die Grenzregel Kern/Hülle — durch die Module, nicht zwischen ihnen

*(Revision 2: pro Bürger schneiden, nicht pro Datei.)*

Eine einzige, maschinell prüfbare Frage zieht den Strich:

> **Muss das stimmen, *egal was registriert wird*? → Kern.**
> **Ist das *ein bestimmtes Verhalten*? → Hülle.**

Die Linie läuft **durch** Module: `governance` trennt heute schon
Kernel-Constraints (harte Invarianten → Kern) von Policies (weich, überstimmbar →
Hülle). `rules` trennt heute schon die Reaktor-Maschine (→ Kern) von den einzelnen
Regel-Dicts (→ Hülle). Die Architektur zwingt dem Code nichts Fremdes auf — sie
benennt einen Schnitt, nach dem der Code schon greift.

**Kern (gehärtet — klein, dicht, voll getestet, ändert sich fast nie):**
Ledger · Versiegelung · Replay-Determinismus · Vertrauens-Auflösung (`sources`) ·
reine Schluss-Algorithmen (`inference`, `confidence`) · Selbst-Kalibrierung ·
die zwei Primitive selbst · Fundament (`db`, `constants`, `proposal_types`).

**Hülle (offen — wächst, jedes Stück ein geprüfter Eintrag):**
Projektoren · Reaktoren · Detektoren · Fähigkeiten/Werkzeuge · Gesprächszellen ·
Policies · Regel-Einträge.

Was im Kern steht, MUSS stimmen — egal was die Hülle registriert. Das macht den
Kern *hart*: kein Hüllen-Eintrag kann ihn brechen, weil er jeden Eintrag beim
Registrieren prüft und zur Laufzeit gated.

---

## 4. Die Hülle als Projektion — und die Bootstrap-Naht

*(Revision 3: „Prozesse sind alles Ledger" stimmt — mit einer sichtbaren Naht.)*

Naiv entsteht ein Henne-Ei: Replay braucht Projektoren, aber Projektoren sind
selbst per Event registriert. Auflösung:

- Die **Entscheidung** zu registrieren ist ein Event — prüfbar, gegated, replaybar.
- Die **Dispatch-Tabelle zur Laufzeit** wird beim Start aus Code + diesen
  Entscheidungen neu aufgebaut.
- Ein kleiner, **fixer Satz Kern-Projektoren bootstrappt** das Replay; alles
  darüber ist registriert.

Die heutige In-Memory-`werkzeug.REGISTRY` ist die noch nicht zu Ende geführte
Vorstufe, kein anderer Entwurf. Der Ledger-Weg wird real, sobald Selbst-Codieren
Einträge anlegt (Phase 3, §9).

---

## 5. Die Grenze — constrained decoding härtet das Deuten

*(Ronnys Geistesblitz 2026-07-04: „nächstes Wort darf nur innerhalb der Grenze sein.")*

Heute: das Organ generiert frei, danach prüfen Guards (Anker-Check der Stimme,
`_looks_like_question` des Deuters). Das ist „verify-after" — funktioniert, wirft
aber ganze Generierungen weg.

Ziel: die Grenze ist **Vorbedingung**. Beim Deuten ist der gültige Schlüsselraum
endlich und bekannt → eine Grammatik (GBNF, `llama.cpp` kann das nativ, schon im
Stack) maskiert pro Token die erlaubten Fortsetzungen. Das Modell **kann keine
Kategorie erfinden, die es nicht gibt** — die Live-Fehlgriff-Klasse
(„Hallo"→kuerzer) wird strukturell unmöglich statt per Few-shot gehofft.
„Organ, nicht Orakel" — bis auf die Token-Ebene.

**Skalierung**: Die Beschränkung ist pro Token, der Aufruf bleibt EIN
Generierungslauf (keine N Mini-Requests — die wären auf dem Pi langsamer). Die
Grammatik wird **aus der Registry abgeleitet**: wächst die Hülle, wächst der
erlaubte Ausgaberaum automatisch mit. Kein Prompt-Tuning, kein Nachpflegen.

**Ehrliche Grenzen** (§8, Nähte 2 und 5): garantiert *wohlgeformt und im Raum*,
nicht *richtig* — der falsche gültige Schlüssel bleibt möglich; der ehrliche
Off-grid-Ausweg muss Teil der Grammatik sein und bleibt Modell-Qualität; die
Grammatik muss als Daten über die Membran (Drift-Risiko der Defaults in
`deuter.py` wird dadurch ernster, nicht harmloser).

---

## 6. Lernen = erinnern + neu rechnen — die dritte Instanz derselben Form

*(Ronnys Frage: „dann macht GENUS Fehler. kann es lernen? aber bleibt es leicht?")*

Ein falscher-aber-gültiger Griff ist ein **Widerspruch** zwischen Deutung und
Meinung — und für Widersprüche existiert die Lehrer-Schleife bereits. Die
Korrektur wird ein provenienziertes Event (Quelle = Mensch, Mensch-Vertrauen);
die Deutung selbst wird heute schon protokolliert (`record_reading`).

Der leichte Weg (kein Training, kein Prompt-Wachstum): korrigierte Paare
(Text → Schlüssel) sind Futter für den **Embedder, der auf dem Pi schon läuft**
(~100 MB, 14 ms). Nächste ähnliche Nachricht → Cosine-Vergleich gegen korrigierte
Beispiele → Schlüssel kippt in die richtige Richtung. Zum dritten Mal dieselbe
Form:

| was | wird zur Lesezeit neu gerechnet aus |
|---|---|
| Vertrauen (`sources`) | allen Belegen |
| Schwellen (`self_calibration`) | der gelebten Historie |
| Klassifikation (Ziel) | korrigierten Beispielen |

**GENUS lernt, indem es sich erinnert und neu rechnet — nicht indem es
trainiert.** Und richtig gemacht wird es *leichter* mit jedem Lernen: jede
Korrektur ist eine Nachricht mehr, die der billige Embedder allein erkennt,
ohne das große Modell zu wecken. Das LLM wird Rückfall für das echt Neue.

**Ehrliche Grenzen** (§8, Nähte 1, 4, 6): das Korrektursignal an der Membran ist
selbst eine unscharfe Nachricht; die Embedder↔LLM-Schwelle ist eine weitere zu
kalibrierende Grenze; Cosine-über-alles skaliert nicht ewig auf append-only.

---

## 7. Die sechs Schichten — Abhängigkeit nur nach unten

```
Membran            cli · telegram_bot · deuter · stimme      (nur Ein-/Ausgänge)
Verstehen & Können verstehen · dispatcher · werkzeug · query · mathematik
Selbst-Bezug&Gates experience · maturation · proposals · governance · inquiries · operation
Wissen & Schluss   inference · rules · learning · gender_rule · confidence · state
Speicher           ledger · event_router(→Registry) · projection · sources
Fundament          db · sealing · constants · self_calibration · proposal_types
```

Maschinell prüfbar — `doctor.py` bewacht heute schon verbotene LLM-Importe;
eine Schicht-Verletzung ließe sich genauso prüfen. Aus Konvention wird Gate.

---

## 8. Die offenen Nähte — ehrlich, nach Ernst geordnet

1. **Der Lernkreis ist am Ort des Fehlers nicht geschlossen.** Der saubere
   Lehrer-Loop sitzt am Terminal (`genus teach`); die Fehlgriffe passieren an
   der Membran, wo die Korrektur selbst wieder unscharf gedeutet werden muss.
   Verlässliches Lernen auf einem Klassifikator, der seine eigenen Fehler
   erkennen soll, ist zirkulär. → Design-Aufgabe: ein *enger, fast
   deutungsfreier* Korrektur-Kanal an der Membran (z. B. exakte Kurzform oder
   Rückfrage-Knopf), nicht „Korrektur als Freitext raten".
2. **Der Off-grid-Ausweg lässt sich nicht durch die Grenze härten.** Ehrliches
   „dafür habe ich keine Zelle" ist das Gegenteil einer Beschränkung — er muss
   erlaubter Ausgang der Grammatik sein, und ihn *richtig zu wählen* bleibt
   Modell-Qualität. Der wichtigste Fall bleibt der ungehärtete.
3. **Der echte Wächter der Router-Migration ist der Registry-Vertragstest,
   nicht der Replay-Test.** Replay-Determinismus fängt eine verpfuschte
   Migration; eine später *vergessene* Registrierung fehlt auf beiden Seiten →
   grün, obwohl falsch. Nötig: CI-Gate „jeder je gesendete Event-Typ hat einen
   registrierten Projektor".
4. **Die Embedder↔LLM-Schwelle ist ungeeicht.** „Bekannt genug" ist eine
   Cosine-Marge, die selbst kalibriert werden muss (aus gelebten Treffern) —
   passt zur Philosophie, ist aber eine Naht, keine geschenkte.
5. **Die Grammatik erbt die Membran-Drift.** Sie muss als Daten übergeben
   werden; die bekannte Drift-Stelle (`deuter.py`-Defaults vs. lebender Graph)
   wird mit einer zwingenden Grenze gefährlicher. → Default abschaffen oder
   beim Start gegen den Graphen verifizieren.
6. **„Wird leichter" hat einen Schwanz.** Cosine über Jahre append-only
   gewachsener Beispiele braucht irgendwann Index oder Beschneidung — Teil der
   nie nachgemessenen Ledger-Wachstumsfrage.

**Die Gate-Politik (entschieden von Ronny, 2026-07-04: „entwickelt sich"):**
Die Politik für selbst-vorgeschlagene Fähigkeiten ist keine Konstante, sondern
selbst gelebt-kalibriert — mit zwei harten Kanten:
1. **Startpunkt ist der strengste:** jede selbst-vorgeschlagene Fähigkeit braucht
   Freigabe pro Stück. Lockerung erst bei echter Erfolgsbilanz aus der gelebten
   Historie.
2. **Eine Lockerung ist selbst ein Proposal durchs Gate** — GENUS lockert seine
   Gates nie einseitig; jede Entwicklungsstufe der Politik wird freigegeben.
3. **Ein Boden entwickelt sich nie** (Kernel-Constraint, nicht Policy):
   schreibende Werkzeuge mit Außenwirkung (Geld, Nachrichten an Dritte,
   Systemeingriffe) bleiben immer freigabepflichtig.

Die Unterscheidung existiert in `governance.py` wörtlich: Kernel-Constraints
(hart) vs. Policies (weich). „Entwickelt sich" heißt: Policies kalibrieren sich
aus der Bilanz, Constraints nie — dieselbe Regel wie überall (relativ zur eigenen
Historie → kalibriert; absolut → fix).

---

## 9. Der Weg — Strangler, grüne Tests nach jedem Schritt

**Phase 0 — Boden (klein, risikoarm):**
Text→Konzept aus `companion` nach `sources` (löst die verkehrten Kopplungen von
`erinnerung`/`experience`) · `telegram_bot` auf `genus.db.connect` ·
Belief-Zustandsmaschine teilen (heute 5× kopiert) · Seed-Helfer · Anker-Prüfung
teilen · `deploy/_edge_common`.

**Phase 1 — Register (der eine große Umbau im Speicher):**
`event_router.apply_event` → Registry; **zuerst den Registry-Vertragstest**
(Naht 3), dann migrieren. Danach `maturation` auf das Detector-Muster.

**Phase 2 — Deuten härten:**
Grammatik aus der Registry ableiten, über die Membran reichen (Drift-Stelle
schließen, Naht 5), Off-grid als erlaubter Ausgang, Belegung zählt weiter.

**Phase 3 — Hülle auf den Ledger + Lernkreis:**
Registrierungs-Entscheidung als Event (mit Bootstrap-Satz, §4) ·
`_HANDELBAR`-Zellen einzeln in die Registry (Strangler, Mathe ist drin) ·
enger Korrektur-Kanal an der Membran (Naht 1) · Embedder-Lernkreis mit
selbst kalibrierter Schwelle (Naht 4).

**Phase 4 — Selbst-Codieren schließt den Kreis:**
Genehmigter Lücken-Vorschlag → Werkzeugbauer legt Hüllen-Eintrag an (Gate-Politik:
siehe §8 — startet strengst, entwickelt sich nur durchs Gate, mit fixem Boden).
Der Kreis „spüren → vorschlagen → bauen" endet nicht mehr an der Freigabe.

---

## 10. Stand-Audit — heute gegen das Ziel

Legende: ✅ steht · ◐ teilweise/Prototyp · ✗ fehlt

| Baustein | Stand | Beleg |
|---|---|---|
| Substanz: Ledger, versiegelt, replaybar | ✅ | `ledger.append` einziger Schreibpfad; `integrity.check` beweist Replay-Determinismus, läuft täglich |
| Projektionen | ✅ / ◐ | Mechanik steht; Schreiblogik dupliziert (Belief-Maschine 5×: `rules`×3, `operation`) |
| Register-Primitiv | ◐ | Prototyp `werkzeug.py` (4 Mathe-Werkzeuge, geprüft); daneben 4 Alt-Stile: `event_router` if/elif ~19 Zweige, `_HANDELBAR` ~22 Zellen, `query.ask` ~8, `maturation` ohne Registry |
| Deuten-Primitiv | ◐ | lebt real (Deuter→Zellen, Segmentierung, Off-grid-Ausweg), aber dreifach gebaut (`query.ask`, `companion`-Muster, Deuter) und nie als Primitiv benannt |
| Registrierung als Event | ✗ | Registry nur In-Memory, beim Start aus Code |
| Die Grenze (constrained decoding) | ✗ | nicht gebaut; `llama.cpp`/GBNF im Stack vorhanden; Drift-Stelle `deuter.py`-Defaults bekannt |
| Lernkreis Klassifikation | ✗ | alle Teile live (Embedder auf dem Pi, `record_reading`, teach-Muster) — nicht verdrahtet; Naht 1 ungelöst |
| Schichtung | ◐ | ~90 % sauber; 2 verkehrte Kopplungen (`erinnerung`/`experience` → `companion`-Private); `telegram_bot` roher `sqlite3.connect` |
| Gates | ◐ | Governance-Gates real (Proposals, Regel-Aktivierung, Recovery), aber 3× duplizierte `evaluate_*`; Gate-Politik entschieden (§8: startet strengst, entwickelt sich nur durchs Gate), noch nicht als Constraint/Policy kodiert |
| Selbst-Codieren-Kreis | ◐ | Stufe 0 live (Lücke → Proposal → Frage); „bauen" nach Freigabe fehlt |
| Wächter | ◐ | `doctor` prüft LLM-/Netz-Importe; Schicht-Gate ✗; Registry-Vertragstest ✗ (Naht 3) |
| Membran-Reinheit | ✅ | alle Edge-Skripte: kein `genus`-Import, lesend rohe SQL, schreibend nur via CLI-Subprozess |

Das Muster des Audits: **die Substanz und die Reinheit stehen; die Primitive
existieren als Prototypen neben ihren Alt-Formen; alles Neue (Grenze, Lernkreis,
Ledger-Registry) ist Verdrahtung von Vorhandenem, kein schwerer Neubau.**

---

## 11. Was das nicht ist

Kein Rewrite. Kern gesund (Audit + Detailanalyse). Eine Umsortierung um ein
Prinzip, das Zu-Ende-Führen eines Registry-Gedankens, der in `werkzeug.py`,
`rules.py`, `experience.py` schon lebt — plus zwei geprüfte neue Ideen mit offen
benannten Nähten. Die einzige echte Gefahr bleibt, den Strich falsch zu ziehen
(zu viel in den Kern → starr; eine Invariante in die Hülle → unsicher) — dagegen
steht die eine Frage aus §3. Und: die Primitive bleiben langweilig und klein
(~`werkzeug.py`-Größe). Sobald eins ein Framework braucht, ist die Linie falsch
gezogen.
