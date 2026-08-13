# ADR-0008 — External Anchor Trust, Key Custody and Ledger Repair

> **Status:** accepted · **Datum:** 2026-08-09
>
> **Decision Owner:** Ronny · **Umsetzung:** noch nicht begonnen
>
> **Quelle:** D-A0.4 bis D-A0.7 im [A0 Decision Packet](../reports/2026-08-09-a0-decision-packet.md)

## Kontext

Anchor v1 ist ausdrücklich unsigniert. Der Pi erzeugt und veröffentlicht seine
Anchors selbst; das Status-Repository ist Transport und besitzt einen
schreibenden Pi-Deploy-Key. `reseal()` kann die Post-Präfix-Seals neu schreiben,
ohne unabhängigen historischen Wartungsbeleg. Der heutige Verifier versteht nur
eine erste Seal-Epoche.

Die unmittelbar vor dem Decision Packet menschlich gesetzte Minimalhärtung
verbietet Force-Push und Branch-Löschung auf `GENUS_PI_STATUS/main`, lässt
normale Fast-Forward-Status-Pushes aber weiter zu. Sie schützt Git-Historie,
nicht einzelne Anchor-Pfade, und ersetzt keine Signatur.

## Entscheidung: Key Custody

1. Ein Anchor-Signatur-Private-Key liegt niemals auf dem Raspberry Pi.
2. Der Pi erzeugt ausschließlich kanonische unsigned Anchor Candidates.
3. Reguläre Signaturen erfolgen manuell an einer getrennten Vertrauensstation
   mit einem Hardware-Token.
4. Ein getrennt und offline verwahrtes verschlüsseltes Recovery-Medium schützt
   gegen Verlust des Primärtokens.
5. Öffentliche Prüfschlüssel und Trust-Manifeste dürfen im Repository und auf
   dem Pi liegen.
6. Rotation, Widerruf, Verlust, Kompromittierungsfenster und Recovery werden
   als explizite historische Vorgänge definiert, bevor eine produktive Signatur
   verwendet wird.
7. Bei ausgefallenem Signierpfad bleiben Candidates `PENDING/UNTRUSTED`; sie
   werden nicht als extern kryptografisch bezeugt bezeichnet.
8. Algorithmus und Bibliothek folgen einem eigenen Security-Review. GENUS
   implementiert keine Eigenkryptografie.

## Entscheidung: Anchor v2

GENUS entwickelt einen versionierten Anchor-v2-Vertrag mit:

- einer versionierten Envelope, die das kanonische `statement` von einer
  separaten `signatures`-Liste trennt;
- kanonisch und domain-separiert signierten Statement-Bytes;
- `core_id`, Epoche, Eventzahl, Head-ID und Head-Seal im Statement;
- Vorgängeranchor-/Lineage-Bindung im Statement;
- Signaturalgorithmus, `key_id` und Signaturwert je Signatureintrag;
- Public-Key-Lineage, Rotation und Widerruf;
- eindeutiger Ausstellungs-ID und append-orientiertem Dateinamen;
- eindeutiger Verifikationssemantik und dokumentierten Nichtgarantien.

Anchor v1 bleibt unverändert als historischer unsigned Legacy-Anchor
verifizierbar. Er wird weder überschrieben noch nachträglich so dargestellt, als
sei er schon damals signiert gewesen. Eine heutige Signatur über altes Material
ist eine heutige retrospektive Bezeugung, kein rückdatierter Zeitbeweis.

GitHub ist Transport-/Archivfläche, nicht alleinige Signaturautorität. Ziel ist
eine vom Pi getrennte signer-owned Witness-Fläche; unabhängige Mirrors dürfen
sie ergänzen, aber nicht ersetzen. Bestehende Anchor-Dateien müssen später
durch Checks unverändert bleiben; normale neue Status-Snapshots dürfen additiv
weiterlaufen.

## Entscheidung: Production Reseal

Production-Reseal ist standardmäßig verboten und kein normaler Wartungspfad.
Eine Ausnahme ist nur als menschlich geführte Notfallzeremonie zulässig und
erfordert mindestens:

- Writer-Stopp;
- unverändertes DB/WAL/SHM-Backup, Digest und Restore-Probe;
- letzten gültigen externen Anchor;
- dokumentierten Schaden/Grund, Incident-ID, Operator, separaten Approver und
  betroffenen Eventbereich;
- ausdrückliche menschliche Freigabe;
- Prüfung auf einer Arbeitskopie;
- Seal, Integrity und Golden Replay vor Nutzungsfreigabe;
- neuen Head, externen Wartungsbeleg, externe Signatur und neuen eindeutigen
  Anchor;
- unverändert erhaltene alte Anchors und Originalabbilder;
- definierten Abbruch-/Restore-Pfad.

Ein `ledger_resealed`-Event innerhalb derselben neu versiegelten Kette ist allein
kein kryptografischer Beweis. Der neu versiegelnde Akteur könnte auch dieses
Event neu berechnen.

Da Anchor v2, externe Signatur, Recovery-Custody und separater Approver noch
nicht implementiert beziehungsweise benannt sind, kann heute keine produktive
Ausnahme alle Gates erfüllen. Bis dahin gilt praktisch ein vollständiger
Production-Reseal-Stopp, obwohl der bestehende CLI-Befehl technisch noch
aufrufbar ist.

## Entscheidung: Multi-Epoch-Richtung

Langfristig entsteht eine neue Protokollversion für erklärbare
Repair-Transitions:

- eine beschädigte Epoche bleibt als beschädigt sichtbar;
- letzte vertrauenswürdige Position, letzter Anchor und erste untrusted Position
  werden gebunden;
- Schaden, Reparaturgrund, menschliche Freigabe und externer Wartungsbeleg
  tragen Digests;
- eine neue Epoche referenziert Vorgänger, Schadensgrenze und Repair-Artefakt;
- Verifikation erklärt mehrere Epochen und Repair-Übergänge statt eines einzigen
  globalen Booleans;
- nicht semantisch reparierbare Schäden beginnen eine neue Ledger-Generation,
  die über Lineage auf die unverändert quarantänisierte alte Generation zeigt.

Multi-Epoch folgt erst nach Golden Ledger, Anchor v2 und abgenommener
Reseal-Zeremonie. Es ist kein kleiner Patch am heutigen Single-Epoch-Protokoll.

## Konsequenzen und offene Folgeentscheidungen

- Pi-Kompromittierung allein darf keine gültige externe Signatur erzeugen.
- Schlüsselverlust schreibt keine alte Geschichte um.
- Hardware-Token, Offline-Recovery und Witness erhöhen Bedien- und
  Infrastrukturaufwand.
- Signatur beweist weder automatisch Verfügbarkeit noch Vertraulichkeit oder
  vertrauenswürdige Zeit.
- Vor Implementierung bleiben Algorithmus, konkrete kanonische Bytes,
  Token-/Recovery-Besitzer, Mehrpersonenregel, Anchor-Kadenz,
  Widerrufsfenster, Witness-Topologie und Aufbewahrungsfristen menschlich zu
  konkretisieren.
- Alle Änderungen an Seal, Anchor, Signatur, kritischem Publish oder Repair sind
  human-owned critical scope nach ADR-0009.

## Noch nicht umgesetzt

Dieser ADR erzeugt keinen Schlüssel, keine Signatur, keinen Anchor v2, keine
Rotation, keinen Reseal, keine neue Epoche und keine weitere GitHub-Regel.
