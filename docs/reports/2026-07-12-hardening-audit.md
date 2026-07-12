# GENUS Härtungsaudit · Repo und Raspberry Pi

**Auditdatum:** 12. Juli 2026
**Verifizierter Stand:** `2e59b39` auf lokalem `main`, `origin/main` und Pi
**Quelle:** Repo-Prüfung, unabhängige Reviews und read-only Pi-Live-Verifikation
**Status:** Pi-Baseline abgeschlossen; ein später im Doku-Review entdeckter
Anchor-Diagnose-Restpfad ist im aktuellen Repo-Nachtrag geschlossen

## Kurzurteil

GENUS hat nach dem Audit eine belastbare Trennung zwischen deterministischem
Nutzerkern, netzwerkfähigen Membranen und der kleinen privilegierten
Betriebsmembran. Die gefundenen Integritäts-, Wachstums- und
Privilegienprobleme wurden nicht nur dokumentiert, sondern im Code beseitigt,
mit Regressionstests versehen, auf dem Pi ausgerollt und gegen das produktive
Ledger geprüft.

Das Ergebnis ist kein Versprechen absoluter Sicherheit. Ein vollständiger
Root-Kompromiss, physischer Zugriff und der noch nicht extern bezeugte
Ledger-Tail bleiben außerhalb der lokalen Garantie. Die genaue Grenze steht im
[kanonischen Sicherheitsmodell](../SECURITY_MODEL.md).

Ein nachfolgender Dokumentationsreview fand eine nicht von der ursprünglichen
Diagnoseprobe erfasste Restnaht: `ledger anchor verify` verwendete noch einen
schreibfähigen Connector. Der aktuelle Repo-Nachtrag stellt auch diesen Befehl auf
read-only um und schützt ihn mit einer Regression. Die folgenden Live-Zahlen bleiben
der unveränderte Snapshot von `2e59b39`.

## Umfang und Methode

Geprüft wurden:

- der Python-/SQLite-Kern, Event-Routing, Replay, Siegel und Anchors;
- Graph- und Inquiry-Semantik einschließlich Zyklen und Relation-Wachstum;
- alle Pi-Installer und systemd-Langzeitdienste;
- die Root-/Nutzer-Grenze des Netzwerk-Watchdogs;
- Telegram-Token, Allowlist, Single-Instance-Verhalten und Ressourcenbudget;
- produktive DB-Pfade, Streu-Datenbanken und Drift-Reparatur;
- lokale und Linux-Tests, statische Checks, Dependency-Audit sowie Live-Replay.

Die Prüfung kombinierte Quellcodeanalyse, unabhängige adversariale Reviews,
Regressionstests und read-only Live-Inspektion. Sie war kein physischer
Hardwaretest, Kernel-Pentest oder Audit des Telegram-Providers.

## Geschlossene Befunde

| Befund | Umsetzung | Nachweis |
| --- | --- | --- |
| Root-Watchdog lief aus nutzerbeschreibbarem Checkout. | Privilegierter Einstieg und Reparatur-Installer nach `/usr/local/libexec/genus`, `root:root 0755`; Root-State nach `/var/lib/genus-network-watchdog`, Modus `0700`; Checkout-Aufrufe auf dem Pi mit `runuser` herabgestuft. | Effektives `ExecStart`, Eigentümer und vorhandenes `runuser` auf dem Pi geprüft. |
| Nutzer-/Home-Drift konnte ein zweites Ledger unter Root erzeugen. | Installer verweigern implizites `GENUS_USER=root`; Units pinnen die jeweils benötigte Nutzer-, Home-, Core- und DB-Identität; der Watchdog heilt Drift. | Produktive Unit-Eigenschaften und zweiter driftfreier Watchdog-Lauf geprüft. |
| Root/PID 1 konnte eine nutzerkontrollierte Telegram-Environment-Datei laden. | Allowlist strikt numerisch validiert und direkt in die root-eigene Unit geschrieben; `EnvironmentFile` vollständig entfernt. | Effektives `EnvironmentFiles` ist leer; Tests verhindern Regression. |
| Telegram konnte Pi-Ressourcen verdrängen oder doppelt pollen. | Prozess-Lock, 409-Behandlung, standardmäßig nur ein Modell, RAM-/Swap-/Task-/FD-Limits und systemd-Sandbox. | Dienst aktiv, Limits effektiv geladen, kein zweiter Poller. |
| Privilegierte Append-Logs öffneten nutzerkontrollierte Pfade. | Alle persistenten Units und Fallbacks schreiben ins systemd-Journal; Driftprüfung umfasst stdout/stderr. | Effektive Journal-Eigenschaften aller Units geprüft. |
| Nutzer-State konnte Root-Recovery zu stark beeinflussen. | Root verlangt eigenen Netzfehler, klemmt Schwelle auf 3–12 und erzwingt eine Stunde Reboot-Cooldown; GENUS darf nur vetoieren. | Shell-Regressionen und adversariales Boundary-Review grün. |
| Unbegrenzte oder blockierende Nutzereingaben am Root-Rand. | Lesen als GENUS-Nutzer mit `O_NOFOLLOW`, `O_NONBLOCK`, `fstat`, Größen- und Zeitlimit; GENUS-Unterbefehle mit 30-Sekunden-/64-KiB-Grenze. | Sicherheits- und Deploy-Tests grün. |
| Deterministische Embedder-Relationen erzeugten bei Wiederholung Eventflut. | Kanonische ungerichtete Semantik, transaktionssichere Deduplizierung und replay-stabile Legacy-Zusammenführung. | Zweifache Live-Wiederholung: 0 neue Events; keine umgekehrten oder doppelten Paare. |
| Transitivität wurde fälschlich mit Azyklizität gleichgesetzt. | Nur ausdrücklich hierarchische Prädikate sind azyklisch; echte Hierarchiezyklen werden vollständig erkannt und zurückgenommen. | Lange-Zyklus-Regression und exhaustive Kleingraphprüfung grün. |
| Diagnose mit falschem Pfad konnte selbst eine DB erzeugen. | Die geprüften Standarddiagnosen verlangen eine vorhandene Datei und nutzen SQLite `mode=ro`; neue Schreib-DBs melden sich laut. Der spätere Doku-Review weitete dies im Repo-Nachtrag auch auf `ledger anchor verify` aus. | Baseline-Regressionen und Live-Pfadprüfung grün; zusätzliche Anchor-Regression im Nachtrag. |

## Verifikation

### Repository

- `1.250 passed, 3 skipped`
- Ruff, `compileall`, `pip check` und Shell-Syntaxprüfung grün
- `pip-audit`: keine bekannte Schwachstelle in den geprüften Abhängigkeiten
- abschließende unabhängige Reviews: keine auf dem geprüften Pi verbleibenden
  P1-/P2-Befunde; die Portabilitätsgrenze ohne `runuser` ist unten dokumentiert

### Raspberry Pi und Produkt-Ledger

- `1.253 passed` unter Linux
- 933.953 Ledger-Events
- zweimaliger Replay ohne Drift
- Integrity-Check und Siegelkette intakt
- verifizierter Seal-Head:
  `26609cce2d1bc58f82446b9a9f8ce4b2a50b9c6d1a2a4396c28f0eaa46c39ae1`
- neuer Offline-Anchor:
  `<GENUS_HOME>/.genus/anchors/genus-anchor-<core>-933953-26609cce2d1b.json`
- Learner, Telegram und Watchdog-Timer aktiv; keine fehlgeschlagene Unit
- ursprüngliche Root-, Telegram-, Journald- und Zyklusfehler nicht mehr
  reproduzierbar

Eventzahl, Head und Anchor sind ein datierter Prüfbeleg, keine fortlaufend zu
pflegende Statusanzeige.

## Historische Root-Streu-Datenbank

Die historische Streu-DB im Root-Home wurde ausschließlich read-only untersucht:

- SQLite `quick_check=ok`;
- 7.094 unversiegelte `relation_asserted`-Events;
- 6.483 projizierte Relationen;
- davon 5.961 bereits im Produkt-Ledger und 522 abweichend;
- keine offenen Prozess- oder Dateihandles.

Eine automatische Vermischung hätte Herkunft, Reihenfolge und Siegelgarantie
des Produkt-Ledgers verletzt. Daher wurde nichts importiert. DB und zugehörige
Lerner-Cursor liegen reversibel unter
`<root-only quarantine>/2026-07-12T142859Z-unsealed-scatter`.

SHA-256 der quarantänisierten DB:
`cb6353824625ddae3c41c7c75c2c48cabe09ee9ebbe014c339f8d1a29a1ffeb8`

## Verbleibende, nicht blockierende Risiken

1. **Anchor-Kadenz:** Jeder neue Tail ist bis zur nächsten extern verwahrten
   Anchor-Kopie nur lokal bezeugt.
2. **Einzelknoten:** SQLite auf einem Pi bietet keine Hochverfügbarkeit; Restore
   und Anchor-Wiederherstellung sollten regelmäßig geübt werden.
3. **Wachstumsbudget:** Die Eventflut ist gestoppt, aber ein 24/48/72-Stunden-
   Profil pro Ereignistyp bleibt sinnvoll, sobald das alte Messfenster
   abgeklungen ist.
4. **Identitäts-Demotion:** Auf dem auditierten Pi ist `runuser` vorhanden. Der
   aktuelle Watchdog-Fallback ist auf einem Root-Host ohne `runuser` nicht
   fail-closed; ein solches reduziertes Image ist nicht freigegeben.
5. **Lokaler Nutzer:** Ein kompromittierter GENUS-Nutzer kontrolliert weiterhin
   Checkout, Token und zukünftige Ledger-Eingaben innerhalb seiner Zone.
6. **Lieferkette und Host:** Kernel, Betriebssystem, Modellgewichte, Telegram und
   physischer Zugriff wurden nicht vollständig auditiert.

## Betriebsentscheidung

Der gehärtete Stand ist für den aktuellen lokalen Pi-Betrieb freigegeben. Neue
Membranen, privilegierte Aktionen oder autonome Code-Ausführung müssen vor dem
Merge dieselben Gates durchlaufen: klare Trust Boundary, deterministischer
Eventvertrag, Tests, Replay, Integrity, Seal-Verify, externer Anchor und
beobachtete Laufzeitwirkung.

Historische Details zum ursprünglichen Siegelentwurf bleiben im
[`Ledger Audit v1.5`](../history/LEDGER_AUDIT_v1.5.md) erhalten; sie sind ein
Snapshot und keine aktuelle Betriebsanweisung.
