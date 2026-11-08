# Drittprojekte und Lizenzen

IRL4YOU Box besteht aus eigenem Code (CC BY-ND 4.0, siehe `LICENSE` und `ZUSATZERLAUBNIS.md`) und aus Programmen und Treibern anderer Projekte, die mit der Box ausgeliefert oder bei der Installation geladen werden. Diese Seite nennt, was wirklich verwendet wird. Keine Rechtsberatung.

## Quelltext in diesem Repository

| Teil | Herkunft | Lizenz |
|---|---|---|
| Oberfläche, Dienste, Updater, Tests (`irl4you/`, `updater/`, `tests/`) | eigene Entwicklung | CC BY-ND 4.0 |
| Encoder `irl4you-encoder`, SRTLA-Sender `irl4you-srtla` | eigene Entwicklung (Clean-Room: SRTLA nur nach eigener Protokollbeschreibung) | CC BY-ND 4.0 |
| Bild-in-Bild-Baustein `irl4you/gst-src/` | eigene Entwicklung, lädt zur Laufzeit GStreamer (LGPL) | CC BY-ND 4.0 |
| Lüfterregelung `irl4you/install/fan/`, Firmware-Werkzeug `irl4you/install/bootloader/irl4you-bootloader.sh`, RTMPS-Zertifikat `irl4you/install/rtmps/` | eigene Entwicklung | CC BY-ND 4.0 |
| DJI-Kopplung `irl4you/dji_daemon.py`, `dji.py` | Ablauf und Nachrichtenformat nach Moblin (siehe unten), DJI-Dienst von Bittersweet1987 | CC BY-ND 4.0, Moblin-Ablauf unter MIT (Hinweis unten) |

## Mobcam (Protokoll)

Die Quelle „Mobcam“ (iPhone mit Moblin per USB-Kabel als Kamera) spricht das Mobcam-Protokoll des Projekts [eerimoq/mobcam](https://github.com/eerimoq/mobcam) von Erik Moqvist (GPL-2.0; die App Moblin selbst: MIT). `irl4you/mobcam_rtmp.py` ist eine eigene Umsetzung des Nachrichtenformats in Python; Programmcode aus Mobcam ist nicht enthalten, das Programm `mobcam-virtualcam` wird nicht verwendet. Die USB-Verbindung stellt `usbmuxd` (LGPL-2.1/GPL-2.0) her.

Die Quelle „IRL4YOU Cam“ (Android-Handy per USB-Kabel) nutzt ein eigenes Protokoll über Android Open Accessory (`irl4you/android_cam.py`), ohne Fremdcode.

IRL4YOU Box ist kein Produkt von Radxa, Orange Pi, Rockchip oder DJI.

## Moblin (MIT)

Die DJI-Kopplung per Bluetooth folgt dem Ablauf, den das Projekt [Moblin](https://github.com/eerimoq/moblin) von Erik Moqvist umsetzt (Ordner `Moblin/Integrations/Dji/`): Nachrichtenformat, Konstanten und Ablauf wurden nach Python übertragen. Gegenprobe mit [dimadesu/dji-remote](https://github.com/dimadesu/dji-remote) (MIT). Das DJI-Protokoll ist von DJI nicht dokumentiert. Die App Moblin selbst ist nicht enthalten; die Oberfläche bietet nur einen Link, der Streams in der App Moblin öffnet.

> Copyright (c) 2023 Erik Moqvist
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Pakete und Bibliotheken

Die Pakete in `irl4you/debs/` sind für die Box gebaut. Der Quelltext der Fremdprojekte stammt von GitHub; Stand und Quelle stehen in der Tabelle unten. Die Skripte für die GPL-Teile (Kernelbaum, WLAN-Treiber, SRS) liegen in `build/`.

| Komponente | Quelle | Lizenz | Hinweis |
|---|---|---|---|
| SRS 6.0.193 (`irl4you-srs`) | [ossrs/srs](https://github.com/ossrs/srs) | MIT | RTMP/SRT-Eingang, Bau mit einer Zeile Korrektur (`build/box-build.sh`) |
| Rockchip MPP 1.1.0 (`irl4you-mpp`) | [rockchip-linux/mpp](https://github.com/rockchip-linux/mpp) | Apache-2.0 | Hardware-Video |
| Rockchip RGA (`librga`) | [JeffyCN/mirrors](https://github.com/JeffyCN/mirrors), Zweig `linux-rga-multi` | Apache-2.0 | Bildskalierung |
| GStreamer-Elemente für MPP (`irl4you-gst-rockchip`) | [JeffyCN/mirrors](https://github.com/JeffyCN/mirrors), Zweig `gstreamer-rockchip` | LGPL (COPYING: LGPL-2.1; Quelldateien: LGPL-2 oder neuer) | gebaut gegen MPP; Lizenz gegen den gebauten Zweig geprüft |
| WLAN-Treiber rtw88 (`irl4you-wifi-rtw88`) | [lwfinger/rtw88](https://github.com/lwfinger/rtw88) | GPL-2.0 | Kernelmodul für Kernel 6.1.172 |
| WLAN-Treiber AIC8800 (`irl4you-wifi-aic8800`) | [shenmintao/aic8800d80](https://github.com/shenmintao/aic8800d80), Zweig `legacy-mcu1` | GPL-2.0, Firmware des Herstellers | Kernelmodul für Kernel 6.1.172 |
| Linux-Kernel (Rockchip BSP 6.1) | [armbian/linux-rockchip](https://github.com/armbian/linux-rockchip) | GPL-2.0 | Quelle für Kernelbaum und Module |
| Firmware-Stand ROCK 5B+ (`irl4you/install/bootloader/rock-5b-plus/armbian/region.bin`) | unverändert aus dem Armbian-Image 26.8.3: U-Boot 2026.04 ([u-boot](https://source.denx.de/u-boot/u-boot), Bau durch [armbian/build](https://github.com/armbian/build)), TF-A v2.13 ([ARM-software/arm-trusted-firmware](https://github.com/ARM-software/arm-trusted-firmware)), DDR-Initialisierung von Rockchip ([rockchip-linux/rkbin](https://github.com/rockchip-linux/rkbin)) | GPL-2.0-or-later (U-Boot), BSD-3-Clause (TF-A), Binärdatei von Rockchip | Quelle und Prüfsumme des Images in `QUELLE.md` neben der Datei |
| Firmware-Stand Orange Pi 5 Plus (`irl4you/install/bootloader/orange-pi-5-plus/armbian/region.bin`) | unverändert aus dem Armbian-Image 26.8.2: U-Boot 2017.09 im Rockchip-Vendorzweig (Bau durch [armbian/build](https://github.com/armbian/build)), TF-A BL31 v1.48 ([ARM-software/arm-trusted-firmware](https://github.com/ARM-software/arm-trusted-firmware)), DDR-Initialisierung v1.20 von Rockchip ([rockchip-linux/rkbin](https://github.com/rockchip-linux/rkbin)) | GPL-2.0-or-later (U-Boot), BSD-3-Clause (TF-A), Binärdatei von Rockchip | Quelle und Prüfsumme des Images in `QUELLE.md` neben der Datei |
| bleak 3.0.2, dbus-fast 5.2.0 | PyPI | MIT / MIT | per `pip` bei der Installation geladen, nicht mitgeliefert |
| GStreamer, libsrt, OpenSSL, nginx, NetworkManager, Python, Tailscale u. a. | Ubuntu 26.04 bzw. Tailscale-Paketquelle | jeweils eigene Lizenz (u. a. LGPL, MPL-2.0, Apache-2.0, BSD) | Systempakete, nicht verändert |

## Symbole

Einige Symbole der Oberfläche sind an [Feather](https://github.com/feathericons/feather) (MIT, Cole Bemis) und [Lucide](https://github.com/lucide-icons/lucide) (ISC) angelehnt, aber selbst gezeichnet. Die Lizenztexte liegen in `licenses/feather-MIT.txt` und `licenses/lucide-ISC.txt`.

## Emotes im Twitch-Chat

Der Chat lädt Emotes zur Laufzeit von Twitch, BetterTTV, FrankerFaceZ und 7TV. Die Bilder gehören ihren Urhebern und werden nicht mitgeliefert.

## Welche Lizenz gilt wo

- **CC BY-ND 4.0**: der eigene Code dieses Repositorys (Nutzung auch kommerziell erlaubt, Änderungen nur nach Rückfrage bei [Bittersweet1987](https://discord.com/users/232451293040476160) oder [Akinos01](https://discord.com/users/523858990510243861), Ausnahme IRL4YOU; siehe `ZUSATZERLAUBNIS.md`). Die Lizenz gilt auch für frühere Versionen; was jemand vor dem 18.10.2026 unter MIT erhalten hat, behält die damals gewährten Rechte. Der Moblin-Hinweis oben bleibt bestehen.
- **MIT** (Fremdcode): Moblin-Ablauf, SRS, bleak, dbus-fast.
- **GPL-2.0**: Kernel, die beiden WLAN-Treiber und U-Boot in den Firmware-Ständen der ROCK 5B+ und der Orange Pi 5 Plus. Die Pakete enthalten die gebauten Module; der Quelltext ist über die oben genannten Quellen und die Bauskripte in `build/` erreichbar.
- **MIT, Apache-2.0, LGPL**: SRS, MPP und librga (MIT bzw. Apache-2.0), gstreamer-rockchip (LGPL) (siehe Tabelle).

## Lizenztexte

Die Originaltexte der Lizenzen der Fremdprojekte liegen im Ordner [`licenses/`](licenses/), mit Quellen in [`licenses/README.md`](licenses/README.md).
