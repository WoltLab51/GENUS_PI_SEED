# Sicherer Fernzugriff vor der Reise

> **Status:** current manual runbook
>
> **Owner:** GENUS Operations
>
> **Zuletzt verifiziert:** 2026-07-19
>
> **Ziel:** privates SSH vom Android-Telefon über Tailscale. Kein öffentliches Dashboard,
> kein Port-Forwarding und keine automatische Installation durch GENUS.

Tailscale bleibt eine bewusst ausgeführte Systemadministrationsmaßnahme. Die folgenden Befehle
werden **von Hand auf dem Pi** ausgeführt; kein Repository-Skript installiert oder konfiguriert
Tailscale.

Der dazugehörige reale Pi-Befund und Updatevertrag steht im
[Remote-Update-Audit vom 2026-07-19](../reports/2026-07-19-pi-remote-update-audit.md).

## Einmalige Einrichtung auf dem Raspberry Pi

Vorher in einer lokalen SSH-Sitzung prüfen, dass der normale SSH-Zugang funktioniert und der
Login `ronny` verwendet wird. Danach die offizielle
[Linux-Anleitung von Tailscale](https://tailscale.com/docs/install/linux) verwenden. Raspberry Pi
OS wird dort ausdrücklich unterstützt:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Wer `curl | sh` nicht verwenden möchte, folgt auf derselben offiziellen Seite den verlinkten
stabilen Paketquellen für die installierte Raspberry-Pi-OS-Version. Die von `tailscale up`
ausgegebene URL im Browser öffnen und mit dem vorgesehenen Konto anmelden.

Danach auf dem Pi:

```bash
tailscale status
tailscale ip -4
systemctl is-enabled tailscaled
systemctl is-active tailscaled
```

`tailscale status` zeigt den Gerätenamen, `tailscale ip -4` die stabile Tailnet-IP. Wenn MagicDNS
im Tailnet aktiv ist, funktioniert üblicherweise auch der dort angezeigte Gerätename. IP und Name
vor der Reise notieren.

Diese Anleitung nutzt zunächst den vorhandenen OpenSSH-Server **über** das private Tailscale-Netz.
Sie aktiviert nicht zusätzlich Tailscale SSH und verändert weder `/etc/ssh/sshd_config` noch
`authorized_keys`. Das hält die Änderung klein.

## Android verbinden und wirklich testen

1. Tailscale aus dem Play Store gemäß der offiziellen
   [Android-Anleitung](https://tailscale.com/docs/install/android) installieren.
2. Mit **demselben Tailnet-Konto** wie auf dem Pi anmelden und die VPN-Verbindung einschalten.
3. In der App prüfen, dass der Pi online erscheint.
4. In einem Android-SSH-Client mit `ronny@<tailscale-ip>` oder
   `ronny@<magicdns-name>` verbinden. Nur Schlüssel-Authentifizierung verwenden; den privaten
   Schlüssel geschützt im Android-Keystore beziehungsweise im sicheren Speicher des Clients
   halten.
5. WLAN am Telefon vollständig ausschalten und den Test über Mobilfunk wiederholen:

```bash
hostname
cd "$HOME/GENUS_PI_SEED"
./deploy/genus_status.sh
```

Ein Test im heimischen WLAN beweist den Fernzugriff nicht. Erst der Mobilfunktest zählt.

## Neustartprobe vor der Abreise

Nur wenn ein lokaler Zugriff als Rückfallebene vorhanden ist:

```bash
sudo reboot
```

Nach einigen Minuten erneut **über Mobilfunk** verbinden und prüfen:

```bash
tailscale status
systemctl is-active tailscaled ssh
cd "$HOME/GENUS_PI_SEED"
./deploy/genus_status.sh
```

## Empfohlene Sicherheitsgrenzen

- Keine Router-Portfreigabe für SSH und kein öffentliches Web-Frontend einrichten.
- Im Tailnet nur das eigene Konto zulassen, den Identitätsanbieter mit MFA schützen und unbekannte
  Geräte sofort aus der Machines-Liste entfernen.
- Die Tailnet-Zugriffsregeln auf diesen Pi und TCP-Port 22 begrenzen. Ohne eigene Policy gilt bei
  Tailscale standardmäßig eine weit offene Tailnet-Regel; die offiziellen
  [Access-Control-Hinweise](https://tailscale.com/docs/features/access-control/acls) deshalb vor
  dem Hinzufügen weiterer Personen oder Geräte lesen.
- Direkten root-SSH-Login nicht aktivieren. Updates als `ronny` starten; `sudo` nur an den klar
  sichtbaren Dienst-Neustarts erlauben.
- Ablaufdatum des Pi-Gerätes in der Machines-Seite prüfen. Für einen unbeaufsichtigten Server kann
  Key Expiry gezielt nur für dieses Gerät deaktiviert werden; dann sind MFA, Gerätehygiene und das
  Entfernen verlorener Geräte besonders wichtig.
- Vor jedem Update zuerst `./deploy/pi_safe_update.sh --dry-run`, danach den echten Befehl bewusst
  und in einer stabilen Verbindung ausführen. Das Skript ist kein nächtlicher Job.

Tailscale SSH kann später mit enger Policy und Re-Authentifizierung (`check`-Modus) geprüft werden.
Für diese Reise ist die bestehende OpenSSH-Konfiguration über das Tailnet der kleinere Eingriff.

## Abschalten oder entfernen

Vor dem Abschalten sicherstellen, dass ein lokaler Zugang existiert:

```bash
sudo tailscale down
```

Damit bleibt die Software installiert, aber der Pi verlässt vorübergehend das Tailnet. Dauerhaft
den Daemon deaktivieren:

```bash
sudo systemctl disable --now tailscaled
```

Das Gerät zusätzlich in der Tailscale-Machines-Seite entfernen. Erst danach bei Bedarf das Paket
mit dem Paketmanager von Raspberry Pi OS deinstallieren. Nicht aus der einzigen laufenden
Fernwartungssitzung heraus abschalten.
