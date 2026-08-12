# GENUS-Kartografie

> **Status:** generated · aktueller Quellbaumvertrag
> **Quelle:** `genus.kartografie` · nicht von Hand editieren
> **Inhalt:** `59bcd900e6e8643b` · Regeneration: `genus kartografie build`

Diese Karte beantwortet nicht nur *wer importiert wen?*, sondern die wichtigere
Frage: **Was kann über welche Kante tatsächlich Wissen, Antwort oder Betrieb
verändern?** Die interaktive Ansicht liegt in
[GENUS_KARTOGRAFIE.html](../visual/GENUS_KARTOGRAFIE.html); die vollständigen
Daten in [GENUS_KARTOGRAFIE.json](GENUS_KARTOGRAFIE.json).

## Inventar

| Knoten | Kanten | Python-Module | Events | projiziert / roh | Projektionstabellen | H1-Lücken | Pi-Knoten |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 269 | 715 | 103 | 39 | 23 / 16 | 12 | 3 | 16 |

## Kausales Urteil

GENUS lernt bereits symbolisch: Fakten, Relationen, Episoden, Einstellungen und
enge Intent-Korrekturen werden dauerhaft wirksam. Der technische H1-Pilot trägt
Definitionen und Beziehungen als strukturierte Drafts in einen treuen Renderer;
ResponseOutcome und Response-ID entstehen erst nach belegter Telegram-Zustellung.
17 synthetische Alltagsszenarien bilden dafür nun ein aktives hartes Vertragsgate.
Ton und Nutzen bleiben jedoch durch fall- und antwort-hashgebundene Humanreviews
offen. H1 ist damit nicht abgeschlossen: vollständiger Diskursplan, übrige String-
Handler und gegatete Wirkungsbewertung fehlen; Feedback wählt keine Strategie.

```text
Wissen → Handler → AnswerDraft-Pilot + DialogueFrame → treuer Renderer → Ausgabe
            └→ übrige terminale Strings                            ↓ Zustellbeleg
                                      Messung ← Feedback ← ResponseOutcome
Alltagsprobe (17 Fälle) ── hartes Gate ───────────┐
hashgebundene Humanreviews ── offen ──────────────┴→ Wirkungsbewertung (fehlt)
                                                        └→ keine Strategiewahl
```

## Event → Projektor → Tabelle

Der Live-Pfad wendet den Projektor direkt beim Schreiben an; der Router rekonstruiert
denselben Effekt beim Replay. Diese Kanten sind in JSON getrennt.

| Event | Replay-Projektor | persistiertes Ziel |
|---|---|---|
| `belief_confirmed` | `genus.projection.apply_belief_confirmed` | `belief_projection` |
| `belief_created` | `genus.projection.apply_belief_created` | `belief_projection` |
| `belief_superseded` | `genus.projection.apply_belief_superseded` | `belief_projection` |
| `belief_weakened` | `genus.projection.apply_belief_weakened` | `belief_projection` |
| `experience_recharacterized` | `genus.experience.apply_experience_recharacterized` | `experience_log` |
| `experience_recorded` | `genus.experience.apply_experience_recorded` | `experience_log` |
| `governance_decision` | `genus.governance.apply_governance_decision` | `governance_log` |
| `inquiries_reconciled` | `genus.inquiries.apply_inquiries_reconciled` | `inquiry_log` |
| `inquiry_created` | `genus.inquiries.apply_inquiry_created` | `inquiry_log` |
| `inquiry_resolved` | `genus.inquiries.apply_inquiry_resolved` | `inquiry_log` |
| `operation_check_recorded` | `genus.operation.apply_operation_check_recorded` | `operation_log` |
| `operation_recovery_attempted` | `genus.operation.apply_operation_recovery_attempted` | `operation_log` |
| `operation_recovery_result` | `genus.operation.apply_operation_recovery_result` | `operation_log` |
| `proposal_created` | `genus.proposals.apply_proposal_created` | `proposal_log` |
| `proposal_reviewed` | `genus.proposals.apply_proposal_reviewed` | `proposal_log` |
| `relation_asserted` | `genus.projection.apply_relation_asserted` | `relation_projection` |
| `relation_retracted` | `genus.projection.apply_relation_retracted` | `relation_projection` |
| `response_feedback_recorded` | `genus.response_outcomes.apply_response_feedback_recorded` | `response_feedback_log` |
| `response_outcome_recorded` | `genus.response_outcomes.apply_response_outcome_recorded` | `response_outcome_log` |
| `rule_activated` | `genus.maturation.apply_rule_activated` | `rule_projection` |
| `state_changed` | `genus.state.apply_state_changed` | `state_projection` |
| `assertion_recorded` | `genus.projection.apply_assertion_recorded` | `value_projection` |
| `evidence_recorded` | `genus.projection.apply_evidence_recorded` | `value_projection` |

Die 16 bewusst rohen Events sind kein gemeinsamer Mülleimer: Die JSON-Karte
zeichnet `raw_fold`, `audit_trigger`, `audit_trace` und `audit_only` getrennt.

`code_entwurf_erstellt`, `code_entwurf_geprueft`, `constraint_checked`, `contradiction_detected`, `forecast_made`, `forecast_scored`, `hand_abgelehnt`, `hand_ausgefuehrt`, `hand_bestaetigt`, `hand_vorgeschlagen`, `ledger_epoch_opened`, `observation_created`, `policy_evaluated`, `proposal_umgesetzt`, `rule_proposed`, `werkzeug_registriert`.

## Lernwirkung auf Antworten

| Signal | Speicher | Verbraucher | Wirkung | tatsächlicher Effekt | Quelle |
|---|---|---|---|---|---|
| Fakten und Relationen | event_log + relation/value_projection | sources, auskunft, Wortgraph | direkt | Mehr erkannte Begriffe, Definitionen, Relationen und Quellenbelege. | [genus/sources.py:395](../../genus/sources.py) |
| Quellenvertrauen und Übereinstimmung | Read-time Confidence | Narratoren | indirekt | Auswahl, Unsicherheits- und Mehrfachbelegsätze ändern sich. | [genus/sources.py:293](../../genus/sources.py) |
| Intent-Lesungen | relation_projection | Thermometer und Lückendetektor | keine | Zählt Verständnis, verbessert aber keine Formulierung und keinen Inhalt. | [genus/verstehen.py:232](../../genus/verstehen.py) |
| Enge Intent-Korrektur | response_feedback_log + korrekturen.jsonl | lokaler/entfernter Deuter-Prompt + Qualitätsmessung | indirekt | Ist mit der Response-ID replaybar belegt; Beispieltext bleibt lokal, begrenzte Intent-Verwechslungen schärfen die spätere Intentwahl. | [genus/response_outcomes.py:165](../../genus/response_outcomes.py) · [deploy/deuter.py:178](../../deploy/deuter.py) |
| Persönliche Episode | append-only Ledger | Erinnerungsabruf | direkt, begrenzt | Wird auf Abruf und über einen engen Konzeptbezug eingebunden. | [genus/erinnerung.py:113](../../genus/erinnerung.py) |
| Persönlichkeitseinstellung | art:* Relationen | Antwort-Belegung | direkt, begrenzt | Ändert wenige Floskeln, Länge, Beiwerk und optionale Stimme. | [genus/antwort.py:558](../../genus/antwort.py) |
| Forecasts und Fehler | rohe Ledger-Events | learning CLI und Kurven | keine | Kalibrierung sichtbar, aber kein normaler Dialogverbraucher. | [genus/learning.py:97](../../genus/learning.py) |
| Explizites Antwortfeedback (👍/👎) | response_feedback_log | replaybare Qualitätsmessung | keine | Reine Daumen und enge eindeutige Textkritik werden sicher mit einer zugestellten Response-ID verknüpft; automatische Strategiegewichtung bleibt bewusst aus. | [genus/response_outcomes.py:165](../../genus/response_outcomes.py) |
| Modellgedeutetes Lob oder Kritik | nur Lesarten-Zählung | fester Handler | keine | Wird ohne eindeutige Gebärde oder Korrektur nicht als Qualitätsfeedback gespeichert. | [genus/companion.py:1023](../../genus/companion.py) |
| Unbekanntes Chatwort | Opt-in Lernqueue | externer Lerner | potenziell | Nur ein ausdrücklich als Definition erfragter unbekannter Einzelbegriff kann später Graphwissen erzeugen; die Queue ist standardmäßig aus. | [deploy/telegram_bot.py:110](../../deploy/telegram_bot.py) |
| Modellgewichte | statische GGUF-Dateien | Deuter, Stimme, Waage | keine | GENUS aktualisiert oder trainiert diese Gewichte nicht. | [deploy/deuter.py:258](../../deploy/deuter.py) |

## H1-Pilot und nächste Kanten

Aktiv im Pilot: `AnswerDraft` und `DialogueFrame` für Definitionen und Beziehungen,
ein delivery-only `ResponseOutcome`, explizites Feedback mit Response-ID und die
Alltagsprobe mit 17 synthetischen Fällen als hartes Vertragsgate. Frage, Antwort
und Telegram-Kennungen bleiben aus Outcome und Feedback heraus.
Die menschliche Prüfung von Ton und Nutzen ist fall- und antwort-hashgebunden:
geänderte Antworten machen alte Reviews automatisch ungültig. Diese Abnahme ist
noch offen; `h1:evaluation` bleibt deshalb `missing_h1`. Ein grünes synthetisches
Gate und gespeichertes Feedback wählen ausdrücklich noch keine Antwortstrategie.

1. die hashgebundene menschliche Abnahme der 17 Alltagsfälle durchführen.
2. die übrigen Handler schrittweise auf belegte Drafts migrieren.
3. einen vollständigen Diskursplan vor dem treuen Renderer ergänzen.
4. persönliche Episoden in einen physisch löschbaren `MemoryVault` migrieren.
5. eine löschbare Telegram-Edge-Outbox für Outcome-Retry und Feedbackbezug
   über Neustarts bauen.
6. Feedback erst nach kuratierter Abnahme gegatet auf Strategien wirken lassen.

## Modulringe

Module dürfen mehrere Rollen tragen; der Ring beschreibt nur ihre primäre Lage.
Lazy Imports bleiben als eigene Kanten sichtbar und werden nicht als saubere
Schichtgrenze missverstanden.
Python-Imports sind rekursiv abgeleitet. Dynamische SQL-Stellen werden im JSON
explizit als Grenze geführt; Shell-/systemd-/Cronkanten sind einzeln belegte
Runtime-Verträge und keine behauptete vollständige Shell-Sprachanalyse.

| Ring | Module |
|---|---:|
| `antwort` | 9 |
| `domaene` | 35 |
| `fundament` | 5 |
| `lernen` | 8 |
| `membranen` | 20 |
| `projektionen` | 8 |
| `querschnitt` | 2 |
| `schnittstellen` | 13 |
| `wahrheitsmechanik` | 3 |

### Sichtbare Importzyklen

| Mitglieder | Kantenart | Bewertung |
|---|---|---|
| genus.auskunft, genus.werkzeuge_auskunft | `imports_eager, imports_lazy` | `visible_runtime_cycle` |
| genus.companion, genus.druck, genus.experience, genus.maturation, genus.query, genus.rechnen, genus.werkzeuge_seed | `imports_eager, imports_lazy` | `visible_runtime_cycle` |
| genus.inference, genus.sources | `imports_eager, imports_lazy` | `visible_runtime_cycle` |

Direkt erkannte Nicht-Stdlib-Abhängigkeiten: `click`, `fastembed`, `llama_cpp`, `numpy`, `psutil`, `sympy`.

## Pi-Soll-/Ist-Overlay vom 2026-07-13

Der produktive Pfad war read-only verifiziert: Checkout sauber, Ledger einzeln und
gesund, Cron/Watchdog/Learner/Telegram aktiv, H0.1 laufend, kein GENUS-Listener.
Die Karte exportiert keine Token, IDs, Chat- oder Ledgerinhalte.
`genus kartografie check` prüft diesen datierten Snapshot als Repo-Artefakt,
verbindet sich aber nicht live mit dem Pi. Der vollständige Befund steht im
[Runtime-Audit](../reports/2026-07-13-cartography-runtime-audit.md).

| Schärfungspunkt | Schwere | Quelle |
|---|---|---|
| Das Embedder-Venv ist persistent, der Modellcache liegt live jedoch flüchtig unter /tmp; Offline- und Neustartverhalten sind dadurch nicht reproduzierbar. | `high` | [docs/reports/2026-07-13-cartography-runtime-audit.md:55](../../docs/reports/2026-07-13-cartography-runtime-audit.md) · [deploy/pi_install_embedder.sh:25](../../deploy/pi_install_embedder.sh) |
| Die Installer deklarieren Chat-Wortlernen explizit aus; die live installierten Units verließen sich beim Audit noch auf denselben Code-Default. | `medium` | [docs/reports/2026-07-13-cartography-runtime-audit.md:61](../../docs/reports/2026-07-13-cartography-runtime-audit.md) · [deploy/pi_install_learner.sh:33](../../deploy/pi_install_learner.sh) · [deploy/pi_install_telegram_bot.sh:40](../../deploy/pi_install_telegram_bot.sh) · [deploy/pi_network_watchdog.sh:278](../../deploy/pi_network_watchdog.sh) |
| Backups sind funktional und physisch getrennt, aber Ziel und Dateien benötigen einen eigenen 0700/0600-Vertrag für Defense in Depth. | `high` | [docs/reports/2026-07-13-cartography-runtime-audit.md:67](../../docs/reports/2026-07-13-cartography-runtime-audit.md) · [deploy/backup_ledger_to_sd.sh:20](../../deploy/backup_ledger_to_sd.sh) · [docs/SECURITY_MODEL.md:47](../../docs/SECURITY_MODEL.md) |
| Cron-, Doctor- und Statuslogs werden ohne Größen- oder Generationengrenze fortgeschrieben. | `medium` | [docs/reports/2026-07-13-cartography-runtime-audit.md:73](../../docs/reports/2026-07-13-cartography-runtime-audit.md) · [deploy/pi_install_cron.sh:68](../../deploy/pi_install_cron.sh) |
| Der private Elternpfad ist 0700, einzelne State-, Log- und Ledgerdateien besitzen aber keinen einheitlichen 0600-Eigenvertrag. | `medium` | [docs/reports/2026-07-13-cartography-runtime-audit.md:78](../../docs/reports/2026-07-13-cartography-runtime-audit.md) · [docs/SECURITY_MODEL.md:120](../../docs/SECURITY_MODEL.md) |
| Mehrere nicht aktive Werkstattmodelle erschweren Rollen-, Update- und Speicherinventar. | `low` | [docs/reports/2026-07-13-cartography-runtime-audit.md:83](../../docs/reports/2026-07-13-cartography-runtime-audit.md) · [deploy/pi_install_deuter.sh:1](../../deploy/pi_install_deuter.sh) |
| Der netzaktive Learner teilt den Benutzer und damit einen breiten Ausfallradius mit Ledger und privatem Membranzustand. | `architectural` | [docs/reports/2026-07-13-cartography-runtime-audit.md:88](../../docs/reports/2026-07-13-cartography-runtime-audit.md) · [deploy/pi_install_learner.sh:85](../../deploy/pi_install_learner.sh) · [docs/SECURITY_MODEL.md:104](../../docs/SECURITY_MODEL.md) |
| Cron wird in lokaler Pi-Zeit interpretiert, Tickzeilen sind UTC; der Sommerzeitvertrag ist nicht explizit. | `low` | [docs/reports/2026-07-13-cartography-runtime-audit.md:93](../../docs/reports/2026-07-13-cartography-runtime-audit.md) · [deploy/pi_install_cron.sh:68](../../deploy/pi_install_cron.sh) |

## Pflegevertrag

- `genus kartografie build` erzeugt JSON, Markdown und die interaktive Ansicht.
- `genus kartografie check` bricht bei Drift oder ungültigen Quellenkanten ab.
- CI prüft Vollständigkeit von Event-Produzenten, Projektionszielen, Replay-Tabellen,
  Quellenreferenzen und generierten Dateien.
- Live-Zahlen gehören nicht in diesen deterministischen Kern. Ein Pi-Befund bleibt
  ein datierter Report; die Betriebsansicht zeigt den deploybaren Sollpfad.
- 25 dynamische SQL-Aufrufe bleiben explizit
  als Analysegrenze im JSON sichtbar; Tabellenziele werden dort nicht geraten.
