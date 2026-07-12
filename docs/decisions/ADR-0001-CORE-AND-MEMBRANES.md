# ADR-0001 — Deterministischer Kern, begrenzte Membranen

> **Status:** accepted · **Datum:** 2026-06-28 · **Zuletzt verifiziert:** 2026-07-12

## Entscheidung

`genus/` bleibt der deterministische, replaybare Wahrheits- und Governance-Kern.
Netzwerkzugriffe, lokale Modelle, Telegram, freie Sprache und Betriebssystemaktionen
leben in Membranen außerhalb dieses Kerns.

Der heutige Quellbaum enthält mit `genus/sensor.py` eine benannte, eng begrenzte Naht:
synchrone lokale `psutil`-Leser formen System-Readings. Sie sind keine Replaylogik und
greifen weder auf Netzwerk noch Modelle zu. Determinismus gilt ab dem gespeicherten
Event; neue Außenbeschaffung gehört weiterhin unter `deploy/`.

Membranen dürfen Beobachtungen und bequellte Behauptungen liefern. Sie dürfen weder
Beliefs direkt setzen noch Governance umgehen oder Root-Rechte in den Kern tragen.

## Warum

Modelle und externe Quellen liefern Fähigkeit, aber keine verlässliche Autorität. Die
Trennung erhält Replay, Prüfbarkeit und Austauschbarkeit: Ein Modell kann ersetzt werden,
ohne dass GENUS' Wahrheitssystem seine Bedeutung ändert.

## Konsequenzen

- Kernmodule importieren keine LLM-, HTTP- oder subprocess-Bibliotheken.
- Netzwerk und Modelle sind erlaubt, aber nur in benannten Membranen.
- Modelloutput erhält Herkunft `model:*` und gedeckeltes Vertrauen.
- OS-/Root-Handlungen bleiben außerhalb des Kerns und werden durch Kernentscheidungen
  höchstens weiter eingeschränkt, nie zusätzlich ermächtigt.

Siehe [Architektur](../ARCHITECTURE.md) und [Security-Modell](../SECURITY_MODEL.md).
