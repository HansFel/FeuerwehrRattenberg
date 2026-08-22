# FeuerwehrRattenberg-Failover

Stand: 22.08.2026

## Aufbau

- Aktiver Server: `hans-ThinkPad-E590`, LAN `192.168.1.34`, Tailscale
  `100.119.59.86`.
- Backup-Server: `ffrattenberg`, LAN `192.168.1.35`, Tailscale
  `100.78.100.82`.
- Auf dem Backup laufen dieselben vier App-Instanzen (Ports 8000 bis 8003),
  vier PostgreSQL-17-Datenbanken und Traefik. Der geprüfte Stand ist Build 79.
- Router, internes DNS und Portweiterleitungen bleiben auf `.34`. Im Fehlerfall
  übernimmt der Backup-Server deshalb die Adresse `.34`.

Der Backup-Server ruft alle fünf Minuten mit
`/home/hans/failover-daten-sync.sh` vollständige Dumps der vier Datenbanken
über Tailscale ab. Der aktive Server wird dabei nur gelesen. Erst wenn alle
Dumps vollständig und prüfbar sind, werden die Datenbanken auf `.35`
wiederhergestellt. Währenddessen werden ausschließlich die vier Apps auf dem
Backup kurz gestoppt. 288 Stände je Instanz (mindestens 24 Stunden) bleiben
unter `/home/hans/backups/failover-sync/` erhalten. Der Zeitstempel des letzten
Erfolgs steht in `LETZTE_ERFOLGREICHE_SYNCHRONISIERUNG`.

Die SSH-Verbindung verwendet auf dem Backup den eigenen Schlüssel
`~/.ssh/id_ed25519_failover_sync`. Sein öffentlicher Schlüssel ist auf dem
aktiven Server auf die Tailscale-IP des Backups eingeschränkt. Private
Schlüssel und `.env`-Dateien gehören niemals ins Repository.

## Kontrolle im Normalbetrieb

Auf dem Backup-Server:

```bash
cat ~/backups/failover-sync/LETZTE_ERFOLGREICHE_SYNCHRONISIERUNG
tail -50 ~/backups/failover-sync.log
docker ps
crontab -l
```

Die Synchronisation kann gefahrlos manuell ausgelöst werden:

```bash
~/failover-daten-sync.sh
```

## Failover aktivieren

Nur umschalten, wenn der aktive Server sicher abgeschaltet oder vom Netz
getrennt ist. Zwei Geräte mit `.34` verursachen einen IP-Konflikt.

1. Aktiven ThinkPad sicher abschalten oder Netzwerk trennen.
2. Per Tailscale mit dem Backup verbinden.
3. Umschalten:

   ```bash
   sudo /home/hans/failover-aktivieren.sh
   ```

4. Die LAN-SSH-Verbindung zu `.35` bricht erwartungsgemäß ab. Über Tailscale
   oder anschließend `.34` neu verbinden.
5. `docker ps` und die vier Instanzen auf den Ports 8000 bis 8003 prüfen.
6. Intern und extern `https://ffrattenberg.duckdns.org/` testen.

Das Skript bricht ab, solange `.34` noch auf Ping antwortet. Vor der
IP-Änderung legt es eine Netplan-Sicherung an und setzt
`/home/hans/FAILOVER_ACTIVE`. Dieser Marker stoppt weitere Datenabrufe vom
ausgefallenen beziehungsweise später wiederkehrenden Hauptserver.

## In den Normalbetrieb zurückkehren

Bevor der ursprüngliche Server wieder `.34` verwendet, den Backup-Server per
Tailscale zurücksetzen:

```bash
sudo /home/hans/failover-zuruecksetzen.sh
```

Danach prüfen, dass das Backup wieder `.35` verwendet. Erst dann den aktiven
Server anschließen. Daten, die während des Failovers neu entstanden sind,
müssen vor dem Rückwechsel bewusst vom Backup zum Hauptserver übertragen
werden; das geschieht absichtlich nicht automatisch.

## Deployment-Hinweise

Der initiale Stand wurde aus geprüften Dumps und dem exakten aktiven
Docker-Image aufgebaut. Docker Compose v5 kann bei `up` trotz vorhandenem Tag
neu bauen. Soll ein zuvor geladenes, exakt identisches Produktionsimage
verwendet werden, deshalb `docker compose up -d --no-build` verwenden und die
Image-ID anschließend mit `docker inspect` vergleichen.

Die Skripte im Repository sind die dokumentierte Vorlage. Installierte Kopien
liegen auf dem Backup unter `/home/hans/` und haben Modus 700.

## Bekannte Grenze: Nextcloud

Auf Port 81 läuft auf `.35` bereits ein eigenständiger Nextcloud-Dienst. Er
wurde bei dieser Einrichtung nicht überschrieben. Seine Dateien, Datenbank
und Aktualität sind **nicht** Bestandteil der FeuerwehrRattenberg-
Datenbanksynchronisation und müssen separat gesichert bzw. gespiegelt werden.
