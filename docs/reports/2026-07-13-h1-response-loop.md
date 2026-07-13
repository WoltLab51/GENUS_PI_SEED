# GENUS H1 · Erster geschlossener Antwortkreis

> **Status:** implementierter Repo-Pilot · noch kein abgeschlossenes H1
>
> **Stand:** 13. Juli 2026
>
> **Besitzt:** Vertikalschnitt, Datenschutzgrenze, Abnahme und offene Reifekanten

## Das Ergebnis in einem Bild

```text
belegtes Wissen
      ↓
AnswerDraft ── Claims · Evidence · Unsicherheit · treuer Fallback
      +
DialogueFrame ── Absicht · Ankerkontinuität · kontrollierte Darstellung
      ↓
deterministischer Renderer → optionale Stimme → Telegram
                                             ↓ nur mit Send/Edit-Beleg
ResponseOutcome + stabile Response-ID ← explizites Feedback
                                             ↓
                               replaybare Messfläche
                               keine automatische Selbstbelohnung
```

## Was der Pilot wirklich schließt

| Naht | Jetzt belegt | Absichtliche Grenze |
|---|---|---|
| Antwortsubstanz | Definitionen und Beziehungen tragen `AnswerDraft`; `understood_unknown` erzeugt keinen negativen Schein-Claim. | Die übrigen Handler liefern weiter kompatible Strings. |
| Darstellung | `DialogueFrame` und Renderer halten Anker sowie gerichteten Kern fest und fallen bei Treuebruch zurück. | Ein vollständiger, intentübergreifender Diskursplan fehlt. |
| Zustellung | Outcome und ein bestätigter Dialogzug entstehen erst nach gültigem Telegram-Send/Edit-Beleg. | Transportausfälle werden nicht als Antworterfolg gezählt. |
| Messung | `answered`, `invalid_slots`, `understood_unknown`, `fallback`, Lesarten und Modus sind replaybar. | Es werden keine Qualitätsurteile aus einer gelesenen Absicht geraten. |
| Feedback | Reine 👍-/👎-Nachrichten und enge Korrektur-Cues verweisen auf eine feedbackfähige Response-ID. | Freies, nur modellgedeutetes Lob/Kritik ist kein Feedbacksignal. |
| Lernen | Intent-Korrekturen können weiterhin über die gedeckelte Edge-Datei den Deuter-Prompt stützen. | Positiv/negativ gewichtet keine Strategie und trainiert kein Modell. |

## Datenschutzvertrag

`response_outcome_recorded` und `response_feedback_recorded` akzeptieren exakt ihre
strukturellen Felder. Nicht gespeichert werden:

- Frage oder Antwort,
- freie Slots oder Gesprächsauszüge,
- Chat- und Nutzerkennung,
- Telegram-`message_id`,
- Modellbegründungen oder versteckte Qualitätsscores.

Die Response-ID ist die Event-ID des Outcome-Events. Damit bleibt die Verbindung stabil,
ohne eine zweite Kennung einzuführen. Der Telegram-Bezug lebt nur in der gedeckelten
RAM-Session. Ein Neustart verwirft ihn; der spätere Randindex muss deshalb löschbar sein
und außerhalb des Kern-Ledgers bleiben.

Ein Feedback-Ack bleibt in dieser Session sichtbar, ist aber selbst nicht feedbackfähig;
ein folgender Daumen darf auf die letzte echte Antwort davor zeigen. Zugestellte Ritual-
und Fehlerantworten sind dagegen Barrieren und verhindern den Durchgriff auf eine ältere
Sachantwort. Ein korrigierter Intent gelangt nur dann als Token ins Ledger, wenn er im
lebenden Verstehensraster bekannt ist.

## Abnahmevertrag

Der Pilot gilt nur dann als grün, wenn:

1. Draft- und Renderer-Tests Claims, Provenienz, Unsicherheit, Anker und Fallback pinnen,
2. ein fehlender Zustellbeleg weder Outcome noch Session-Zug erzeugt,
3. Outcome-/Feedback-Payloads keine zusätzlichen Inhalts- oder Transportfelder erlauben,
4. Feedback nur auf eine vorhandene feedbackfähige Response-ID zeigt,
5. Liveprojektion und Replay exakt dieselben Outcome-/Feedbacktabellen ergeben,
6. Eventdokument, Kartografie und generierte Artefakte driftfrei bleiben.

Die ausführbaren Nachweise liegen in `tests/test_antwort.py`,
`tests/test_response_outcomes.py`, `tests/test_telegram_bot.py`,
`tests/test_event_contract_docs.py` und `tests/test_kartografie.py`.

## Bekannte Pilotgrenzen

- **Edge-Outbox fehlt:** Ist Telegram bereits zugestellt und scheitert danach
  `record_outcome`, wird der Update-Offset trotzdem fortgeschrieben. Die Antwort bleibt
  dauerhaft ungemessen; ein löschbarer, transportnaher Retry-Beleg ist der nächste
  Zuverlässigkeitsschritt.
- **Äußere Crashmeldung ohne Outcome:** Fällt `handle_update` außerhalb seines inneren
  Wächters aus, kann der Statusmelder noch eine Fehlermeldung zustellen, ohne dafür ein
  Outcome anzulegen.

Im Integrationsreview geschlossen wurden zwei frühere Kanten: RAM-Session und Telegram
verwenden nun exakt denselben auf 4000 Zeichen begrenzten Antworttext; ein ungelöstes
Segment senkt das Gesamt-Outcome konservativ, auch wenn ein anderes Segment beantwortet
wurde.

## Nächste Reife, in dieser Reihenfolge

1. Alltagstestset mit klaren Qualitätsdimensionen und menschlicher Abnahme aufbauen.
2. weitere wissenshaltige Handler auf `AnswerDraft` migrieren.
3. Diskursplan ergänzen, ohne Modelltext zur Evidenz zu machen.
4. löschbare Telegram-Edge-Outbox samt Response-Bezug über Neustarts bauen.
5. Feedback erst nach kuratierter Evaluation für begrenzte Strategiewahl nutzen.
6. Memory-Vault, Export, Retention und physisches Vergessen gemeinsam schließen.
