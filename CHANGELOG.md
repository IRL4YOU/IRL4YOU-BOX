# Änderungen

Versionsschema: x.y.z, angezeigt als vx.y.z. x gibt Marco vor (0 = Alpha). y steigt nur, wenn Marco ein Release ausruft (dann wird VERSION auf "x.y" geändert). z ist die Zahl der Commits seit dem letzten Release und wird vom Updater beim Installieren aus GitHub gezählt (VERSION enthält nur "x.y"). Die Box folgt weiterhin den Commits von main; die Nummer ist nur der Anzeigename.

## 0.4
- Erste veröffentlichte Version der IRL4YOU Box: fertige Images für Orange Pi 5 Plus und Rock 5B+.
- Neue Oberfläche als Startseite (Live, Kameras, Bild, Netzwerk, System, Suche mit Strg+K, am Handy eine Live-Leiste); die bisherige bleibt unter `/alt`. Logo als Favicon, Fußzeile mit Lizenz und Links.
- Eigener Encoder und eigener SRTLA-Sender, die Kameras (RTMP, DJI, HDMI, USB) zu einem Bild-in-Bild mischen und gebündelt über mehrere Leitungen senden.
- Updates: Die Box folgt den Commits von `main` (nur mit grünen Prüfungen) und installiert sie auf Knopfdruck, nie während einer Sendung. Ubuntu-Sicherheitsupdates laufen mit jedem Update mit.
- Firmware-Stand aus Armbian mit Werkzeug `irl4you-bootloader` für Rock 5B+ und Orange Pi 5 Plus. Rock 5B+: Lüfterregelung (Kupfer und Alu), kein Takt-Deckel. Dateien des jeweils anderen Boards werden nicht installiert.
- Niedrigste Bitrate: Standard 400 statt 300 kbit/s. Latenz als Schieberegler (Standard 4000 ms).
- Facecam bleibt bei der Rotation auf ihrem Platz, der Ton bleibt bei ihr. Tonquelle mit Mikrofon-Symbol.
- Schalter in der Oberfläche sind nur noch selbst anklickbar; Stream-ID des Servers lässt sich anzeigen.
