# Firmware-Stand für die ROCK 5B+

`region.bin` ist der Bootloader-Bereich (Sektor 64 bis 19747 der SD-Karte) aus dem Armbian-Image
`Armbian_26.8.3_Rock-5b-plus_resolute_vendor_6.1.115_minimal.img.xz` (SHA-256 des Images: e9431dcbe7887aeafd0d5dccea37dd37bbcf641bd9c5556c42cb5a30d1584056),
unverändert übernommen. Inhalt: U-Boot 2026.04 (GPL-2.0-or-later, Quelltext: https://source.denx.de/u-boot/u-boot und das Armbian-Build-Projekt
https://github.com/armbian/build), TF-A v2.13 (BSD-3-Clause, https://github.com/ARM-software/arm-trusted-firmware) und die Speicher-Initialisierung
DDR v1.20 von Rockchip (Binärdatei aus https://github.com/rockchip-linux/rkbin).
