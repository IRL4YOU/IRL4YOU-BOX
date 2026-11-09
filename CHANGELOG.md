# Änderungen

Versionsschema: x.y.z, angezeigt als vx.y.z. x gibt Marco vor (0 = Alpha). y steigt nur, wenn Marco ein Release ausruft (dann wird VERSION auf "x.y" geändert). z ist die Zahl der Commits seit dem letzten Release und wird vom Updater beim Installieren aus GitHub gezählt (VERSION enthält nur "x.y"). Die Box folgt weiterhin den Commits von main; die Nummer ist nur der Anzeigename.

## 0.5
- Mobcam: iPhone mit Moblin per USB-Kabel als Kamera (Kameras > HDMI und USB > Quelle „Mobcam“), Bild und Ton gehen unverändert durch (H.264 oder H.265, kaum Rechenzeit); Ströme über 12 Mbit/s werden abgelehnt, in Moblin höchstens 10 Mbit/s einstellen.
- IRL4YOU Cam: Android-Handy mit der App „IRL4YOU Cam“ per USB-Kabel als Kamera (Kameras > HDMI und USB > Quelle „IRL4YOU Cam“), ohne Netzwerk und ohne USB-Debugging; Bild und Ton gehen unverändert durch, die Box stellt die Bitrate auf höchstens 10 Mbit/s.
- Live: Kachel „Handy“ mit Akku, Strom, Temperatur und Akkukurve des Android-Handys, solange es per USB mit der IRL4YOU Cam sendet (Strom grün beim Laden, orange wenn der Akku sinkt); die Kennzahlen-Karten sind alle gleich groß.
- Bitrate-Grenzen (Netzwerk > Server) gelten sofort, ohne die Sendung neu zu starten; die Einzelbild-Kette nimmt jetzt auch H.265 von Handy-Apps an.
- Ton von einem USB-Mikrofon (zum Beispiel DJI-Empfänger): bei der IRL4YOU Cam und im Bildaufbau („Ton von“), mit Regler für den Ton-Versatz; die Karte „Antwortzeit“ zeigt die Laufzeit der Leitung.
- Testbild als Kamera-Quelle: bewegtes Wellenmuster mit Schrift, Zeit und Logo, Stereo-Testton (links 440, rechts 660 Hz).
- Leitungstest: „Testen“ je Leitung und „Alle Leitungen testen“ (Herunterladen, Hochladen, Antwortzeit, auch während der Sendung).
- Update-Prüfung alle 2 Stunden mit niedrigster Priorität; „Nach Updates suchen“ wartet auf das Ergebnis, auch während der Sendung.
- Vorschau läuft flüssig, Passwortanzeige und Bluetooth-Einrichtung korrigiert.
- Ansicht „Handy“ auch für die neue Oberfläche; Hinweis auf neue Versionen als kleiner Punkt; niedrigste Bitrate mindestens 450 kbit/s, Latenz mindestens 1000 ms.
- Während ein Update installiert wird, kann nicht live gegangen werden; ein hängendes Update lässt sich abbrechen (erst nach 5 Minuten Stillstand, nie beim Umschalten); ein unterbrochenes Update wird erkannt.
- Weniger Flackern der Seiten; „Alle Änderungen“ zeigt die letzten 50 Stände.

## 0.4
- Erste veröffentlichte Version der IRL4YOU Box: fertige Images für Orange Pi 5 Plus und Rock 5B+.
- Neue Oberfläche als Startseite (Live, Kameras, Bild, Netzwerk, System, Suche mit Strg+K, am Handy eine Live-Leiste); die bisherige bleibt unter `/alt`. Logo als Favicon, Fußzeile mit Lizenz und Links.
- Eigener Encoder und eigener SRTLA-Sender, die Kameras (RTMP, DJI, HDMI, USB) zu einem Bild-in-Bild mischen und gebündelt über mehrere Leitungen senden.
- Updates: Die Box folgt den Commits von `main` (nur mit grünen Prüfungen) und installiert sie auf Knopfdruck, nie während einer Sendung. Ubuntu-Sicherheitsupdates laufen mit jedem Update mit.
- Firmware-Stand aus Armbian mit Werkzeug `irl4you-bootloader` für Rock 5B+ und Orange Pi 5 Plus. Rock 5B+: Lüfterregelung (Kupfer und Alu), kein Takt-Deckel. Dateien des jeweils anderen Boards werden nicht installiert.
- Niedrigste Bitrate: Standard 400 statt 300 kbit/s. Latenz als Schieberegler (Standard 4000 ms).
- Facecam bleibt bei der Rotation auf ihrem Platz, der Ton bleibt bei ihr. Tonquelle mit Mikrofon-Symbol.
- Schalter in der Oberfläche sind nur noch selbst anklickbar; Stream-ID des Servers lässt sich anzeigen.
