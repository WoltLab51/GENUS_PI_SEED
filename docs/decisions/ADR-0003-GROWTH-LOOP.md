# ADR-0003 — Wachstum ist ein Kreislauf, keine Mustersammlung

> **Status:** accepted · **Datum:** 2026-07-08 · **Zuletzt verifiziert:** 2026-07-12

## Entscheidung

GENUS wächst nicht durch immer neue Regex-/Handler-Sonderfälle. Wachstum wird an
Generalisierung und bewährter Laufzeitwirkung gemessen.

```text
Lücke → Plan → Werkzeug/Fähigkeit vorschlagen → testen → Mensch gibt frei
      → live messen → aus Erfolg und Misserfolg kalibrieren
```

Regex darf Schnellspur für eine bereits verstandene Form sein. Sie ist kein Beleg für
eine neue generalisierende Fähigkeit.

## Messregel

Das Skill-Thermometer beobachtet den Kreislauf, steuert ihn aber nicht. Keine Kennzahl
darf selbst zum Optimierungsziel des Kerns werden. Ein neuer Spezialfall erhöht deshalb
nicht automatisch die Zahl der Fähigkeiten.

## Konsequenzen

- Fähigkeiten besitzen Abnahmefälle und eine Laufzeitmessung.
- Neue Produzenten erhalten Event- und Ressourcenbudgets.
- Scheitern bleibt als Evidenz erhalten und beeinflusst die nächste Priorität.
- Der Mensch behält Freigabe und Richtung.

Siehe [Charter](../CHARTER.md), [NOW](../NOW.md) und [Roadmap](../ROADMAP.md).
