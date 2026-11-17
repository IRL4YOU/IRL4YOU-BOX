#!/bin/bash
# Läuft AUF der Box: baut den WLAN-USB-Treiber aircrack-ng/rtl8188eus (RTL8188EUS/8188ETV, z. B. 0bda:8179, cfg80211) gegen den Kernelbaum
# aus 09-box-kerneltree.sh (oder die Kernel-Header der Box) und packt ihn als irl4you-wifi-rtl8188eus_<datum>+<kernel>_arm64.deb.
# Installiert nichts ins System. Nur 2,4 GHz, eine Antenne; Hotspot (AP) geht mit WPA2, wenn PMF aus ist (setzt der Hotspot-Code der Box).
set -euo pipefail
B=${B:-/var/tmp/irl4you-build}
KVER=$(uname -r)
KSRC=$B/linux
[ -f "$KSRC/Module.symvers" ] || KSRC=/lib/modules/$KVER/build
test -f "$KSRC/Module.symvers" || { echo "FEHLER: kein Kernelbaum (09-box-kerneltree.sh oder Kernel-Header)"; exit 1; }
mkdir -p "$B"; cd "$B"
[ -d rtl8188eus/.git ] || git clone -q --depth 1 -b v5.3.9 https://github.com/aircrack-ng/rtl8188eus.git rtl8188eus
REV=$(git -C rtl8188eus log -1 --format='%h %cs'); echo "rtl8188eus $REV"
cd rtl8188eus
git checkout -q -- Makefile
# Plattform: arm64 statt PC
sed -i 's/^CONFIG_PLATFORM_I386_PC = y/CONFIG_PLATFORM_I386_PC = n/;s/^CONFIG_PLATFORM_ARM64_RPI = n/CONFIG_PLATFORM_ARM64_RPI = y/' Makefile
make clean >/dev/null 2>&1 || true
make -j"$(nproc)" KVER="$KVER" KSRC="$KSRC" 2>&1 | grep -vE '^\s+CC \[M\]' | tail -8
ls -la 8188eu.ko
# Paket
ST=$B/rtl8188eus-st; rm -rf "$ST"; mkdir -p "$ST/DEBIAN" "$ST/lib/modules/$KVER/updates/rtl8188eus"
cp 8188eu.ko "$ST/lib/modules/$KVER/updates/rtl8188eus/"
D=${PKG_PREFIX:-$(date +%Y%m%d)}
cat > "$ST/DEBIAN/control" <<CTL
Package: irl4you-wifi-rtl8188eus
Version: $D+$KVER
Architecture: arm64
Maintainer: IRL4YOU <irl4you@localhost>
Depends: kmod
Section: kernel
Priority: optional
Description: WLAN-USB-Treiber RTL8188EUS (aircrack-ng, cfg80211) fuer Kernel $KVER
 Modul 8188eu fuer Sticks mit RTL8188EUS/8188ETV (z. B. 0bda:8179), nur 2,4 GHz. Quelle: github.com/aircrack-ng/rtl8188eus ($REV, Zweig v5.3.9, GPL-2.0).
CTL
printf '#!/bin/sh\ndepmod -a %s || true\nexit 0\n' "$KVER" > "$ST/DEBIAN/postinst"; cp "$ST/DEBIAN/postinst" "$ST/DEBIAN/postrm"
chmod 755 "$ST/DEBIAN/postinst" "$ST/DEBIAN/postrm"
mkdir -p "$ST/usr/share/doc/irl4you-wifi-rtl8188eus"; printf 'Paket: irl4you-wifi-rtl8188eus
Lizenz: GPL-2.0
Quelle/Urheber: Realtek und Mitwirkende, aircrack-ng/rtl8188eus
Vollstaendige Lizenztexte: /usr/share/common-licenses/GPL-2 und NOTICE.md im Repo IRL4YOU/IRL4YOU-BOX
' > "$ST/usr/share/doc/irl4you-wifi-rtl8188eus/copyright"
dpkg-deb --root-owner-group --build "$ST" "$B/irl4you-wifi-rtl8188eus_${D}+${KVER}_arm64.deb" >/dev/null
ls -la "$B"/irl4you-wifi-rtl8188eus_*.deb
