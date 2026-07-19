SOLARINSPECTOR 4.0 – RASPBERRY-PI-UPGRADE
=========================================

Dieses Paket aktualisiert eine bestehende SolarInspector-3.x-Installation auf
SolarInspector 4.0.1 mit Solakon ONE über read-only Modbus TCP.
Es kann auch für eine frische Installation verwendet werden.

Geeignet für
------------
- Raspberry Pi OS Bullseye oder neuer
- Raspberry Pi 3B oder neuer
- Python 3.9 oder neuer
- bestehender systemd-Service "solarinspector.service"

Das Upgrade
-----------
- erkennt den Installationsordner über den vorhandenen systemd-Service,
- stoppt SolarInspector vor der Sicherung,
- sichert Programm, config.json und die SQLite-Datenbank,
- behält alle vorhandenen Messdaten und Shelly-Einstellungen,
- ergänzt die Solakon-ONE-Modbus-Konfiguration,
- migriert das SQLite-Schema automatisch,
- aktualisiert die Python-Abhängigkeiten,
- führt automatisierte Tests aus,
- richtet beziehungsweise aktualisiert den systemd-Service,
- startet SolarInspector und prüft die Weboberfläche,
- führt bei einem fehlgeschlagenen Upgrade automatisch ein Rollback aus.

Schnellinstallation
-------------------
1. ZIP auf den Raspberry Pi kopieren und entpacken:

   unzip SolarInspector_4.0.1_RaspberryPi_Upgrade.zip
   cd SolarInspector_4.0.1_RaspberryPi_Upgrade

2. Upgrade starten:

   chmod +x *.sh
   ./Upgrade-SolarInspector-RaspberryPi.sh

Das Skript fragt bei Bedarf nach dem sudo-Kennwort. Nicht das gesamte Skript mit
"sudo ./..." starten; ein normaler Benutzer mit sudo-Rechten ist vorzuziehen.

Nach erfolgreichem Upgrade zeigt das Skript die URLs an, zum Beispiel:

   Dashboard:     http://<RASPBERRY-PI-IP>:8787/
   Konfiguration: http://<RASPBERRY-PI-IP>:8787/configuration

Bestehende Installation an einem abweichenden Ort
--------------------------------------------------
Normalerweise wird der Ordner automatisch aus solarinspector.service erkannt.
Falls erforderlich:

   ./Upgrade-SolarInspector-RaspberryPi.sh --install-dir /pfad/zu/SolarInspector

Abweichender Servicename:

   ./Upgrade-SolarInspector-RaspberryPi.sh --service mein-solarinspector.service

Upgrade installieren, aber noch nicht starten:

   ./Upgrade-SolarInspector-RaspberryPi.sh --no-start

Solakon ONE konfigurieren
-------------------------
Im Browser "Konfiguration" öffnen und im Bereich "Solakon ONE – Modbus TCP":

- Aktiv: einschalten
- IP-Adresse: lokale IP der Solakon ONE
- Port: 502
- Geräte-ID: 1
- Timeout: 5 Sekunden
- Verbindung testen
- Konfiguration speichern

SolarInspector verwendet ausschließlich lesende Modbus-Aufrufe. Es werden keine
Lade-, Entlade- oder Betriebsparameter der Solakon ONE verändert.

Backup
------
Vor jedem Upgrade wird ein Backup angelegt unter:

   /home/<service-benutzer>/SolarInspector-Backups/

Der genaue Pfad wird am Ende des Upgrades angezeigt und zusätzlich in
"upgrade-info.txt" im Installationsordner gespeichert.

Manuelles Rollback
------------------
Die zuletzt erzeugte Sicherung automatisch auswählen:

   ./Rollback-SolarInspector-RaspberryPi.sh

Eine bestimmte Sicherung verwenden:

   ./Rollback-SolarInspector-RaspberryPi.sh \
     /home/pi/SolarInspector-Backups/solarinspector-before-4.0.1-DATUM.tar.gz

Service-Befehle
---------------
Status:

   sudo systemctl status solarinspector

Live-Log:

   journalctl -u solarinspector -f

Neustart:

   sudo systemctl restart solarinspector

Diagnose
--------

   ./Diagnose-SolarInspector-RaspberryPi.sh

Das Diagnoseskript zeigt Service, Log und eine Konfiguration mit ausgeblendeten
Kennwörtern. Es verändert keine Daten.

Wichtige Dateien
----------------
- config.json
- data/solarinspector.db
- data/solarinspector.log
- upgrade-info.txt

Hinweis zum Netzwerk
--------------------
Der Raspberry Pi muss die lokale IP-Adresse der Solakon ONE auf TCP-Port 502
erreichen können. Dashboard und Konfiguration sind standardmäßig im Heimnetz auf
Port 8787 erreichbar. SolarInspector nicht direkt ins Internet veröffentlichen.


KORREKTUR IN 4.0.1
-------------------
Version 4.0.1 korrigiert die systemd-Direktive WorkingDirectory der ersten
4.0-Paketfassung. Das Upgrade prüft die erzeugte Unit nun vor dem Neustart
zusätzlich mit systemd-analyze verify.
