#!/bin/sh
# Tauscht Firmware-Teile auf der SD-Karte. Aufruf als root:  irl4you-bootloader status | apply (ROCK 5B Plus und Orange Pi 5 Plus)
# ROCK 5B Plus: Firmware-Stand aus dem Armbian-Image (U-Boot 2026.04, DDR v1.20, TF-A v2.13), ein Block ab Sektor 64 (Ordner rock-5b-plus/armbian/).
# Orange Pi 5 Plus: Firmware-Stand aus dem Armbian-Image (U-Boot 2017.09, DDR v1.20, BL31 v1.48), ein Block ab Sektor 64 (Ordner orange-pi-5-plus/armbian/).
#   status zeigt, ob er aktiv ist; apply schreibt ihn (mit Sicherung des Ist-Stands nach /var/lib/irl4you/bootloader-backup).
# Wird NICHT automatisch beim Update ausgeführt. Neustart nach apply nötig.
# Startet die Box danach nicht mehr, hilft nur die Karte am PC (Image neu schreiben).
# Zum Testen: DEV=<Datei oder Gerät>, MODEL_FILE=<Datei mit dem Modellnamen>, BK=<Sicherungsordner>, DEV_TEST=1 (ohne root).
set -eu
HERE=$(dirname "$(readlink -f "$0")")
BK=${BK:-/var/lib/irl4you/bootloader-backup}
MODEL_FILE=${MODEL_FILE:-/proc/device-tree/model}
MODEL=$(tr -d '\0' < "$MODEL_FILE" 2>/dev/null || true)
case "$MODEL" in
    *"ROCK 5B Plus"*|*"ROCK 5B+"*) BOARD=rock ;;
    *"Orange Pi 5 Plus"*) BOARD=opi ;;
    *) BOARD=none ;;
esac

if [ -z "${DEV:-}" ]; then
    DEV=/dev/mmcblk1
    R=$(findmnt -n -o SOURCE / 2>/dev/null || true)
    if [ "$R" = /dev/root ]; then
        PU=$(tr ' ' '\n' < /proc/cmdline | sed -n 's/^root=PARTUUID=//p')
        [ -n "$PU" ] && R=$(blkid -t "PARTUUID=$PU" -o device 2>/dev/null || true)
    fi
    if [ -b "$R" ]; then
        P=$(lsblk -no pkname "$R" 2>/dev/null | head -1)
        [ -n "$P" ] && DEV=/dev/$P
    fi
fi

hash_of() { sha256sum | cut -d' ' -f1; }
# cur DATEI SEKTOR: Prüfsumme des Kartenbereichs in der Länge der Datei
cur() { dd if="$DEV" bs=512 skip="$2" count=$(( $(stat -c %s "$1") / 512 )) status=none | hash_of; }
want() { hash_of < "$1"; }
is() { [ "$(cur "$1" "$2")" = "$(want "$1")" ]; }
put() { dd if="$1" of="$DEV" bs=512 seek="$2" conv=notrunc,fsync status=none; sync; is "$1" "$2" || { echo "FEHLER: Rücklesen stimmt nicht"; exit 1; }; }
need_root() { [ "$(id -u)" = 0 ] || [ -n "${DEV_TEST:-}" ] || { echo "nur als root"; exit 1; }; }

case "$BOARD" in
rock|opi)
    if [ "$BOARD" = rock ]; then
        V="$HERE/rock-5b-plus"
        LABEL="rock-5b-plus-armbian-uboot-2026.04-ddr-v1.20-tfa-v2.13"
    else
        V="$HERE/orange-pi-5-plus"
        LABEL="orange-pi-5-plus-armbian-uboot-2017.09-ddr-v1.20-bl31-v1.48"
    fi
    REGION="$V/armbian/region.bin"; REGION_START=64
    case "${1:-status}" in
    status)
        if is "$REGION" $REGION_START; then echo "aktiv: $LABEL"; else echo "unbekannt: nicht der mitgelieferte Firmware-Stand"; fi
        exit 0 ;;
    apply)
        need_root
        if is "$REGION" $REGION_START; then echo "schon aktiv"; exit 0; fi
        REGION_SECTORS=$(( $(stat -c %s "$REGION") / 512 ))
        mkdir -p "$BK"
        dd if="$DEV" bs=512 skip=$REGION_START count=$REGION_SECTORS of="$BK/$BOARD-$(date +%Y%m%d%H%M%S).bin" status=none
        put "$REGION" $REGION_START
        echo "geschrieben: $LABEL. Neustart nötig." ;;
    *) echo "Aufruf: $0 status|apply"; exit 1 ;;
    esac ;;
*)
    echo "Dieses Board wird nicht unterstützt ($MODEL)"; exit 1 ;;
esac
