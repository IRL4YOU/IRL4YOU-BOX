# Firmware-Stand für die Orange Pi 5 Plus

`region.bin` ist der Bootloader-Bereich (Sektor 64 bis 19747 der SD-Karte) aus dem Armbian-Image
`Armbian_26.8.2_Orangepi5-plus_resolute_vendor_6.1.115_minimal.img.xz` (SHA-256 des Images: 60e2df87f22252da4fd1ec3d63c1d4717980c4c1cfbe9bcedbddac9502c5a438),
unverändert übernommen. Inhalt: U-Boot 2017.09 im Rockchip-Vendorzweig, von Armbian für die Orange Pi 5 Plus gebaut
(GPL-2.0-or-later, Quelltext: https://github.com/armbian/build und der dort genannte U-Boot-Zweig), TF-A BL31 v1.48
(BSD-3-Clause, https://github.com/ARM-software/arm-trusted-firmware) und die Speicher-Initialisierung DDR v1.20 von Rockchip
(Binärdatei aus https://github.com/rockchip-linux/rkbin).
