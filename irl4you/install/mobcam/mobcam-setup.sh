#!/bin/bash
# Richtet Mobcam ein: iPhone (Moblin) per USB-Kabel als Kamera. Läuft automatisch aus release/hooks/install bei jedem Update (als root), von Hand: sudo bash /opt/pipbox/install/mobcam/mobcam-setup.sh
# Installiert die Pakete, baut mobcam-virtualcam 1.0.0 (GPL-2.0, github.com/eerimoq/mobcam) mit einem Patch für mehrere Dekoder-Kerne
# und legt die Einstellungen für das Kernelmodul v4l2loopback und snd-aloop an. Mehrfaches Ausführen ist harmlos.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Bitte als root ausführen (sudo)."; exit 1; }
VER=1.0.0
URL=https://github.com/eerimoq/mobcam/releases/download/$VER/mobcam-$VER-source.tar.xz
SHA=64efc0607b5c9a160b05f5ecac61be4c78a9773aa02aa4d8e4cae8f10a54591e
RUST=1.98.0
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK=/var/tmp/irl4you-mobcam-build
BIN=/usr/local/bin/mobcam-virtualcam

echo "== Pakete"
export DEBIAN_FRONTEND=noninteractive
apt-get install -y --no-install-recommends v4l2loopback-dkms v4l-utils usbmuxd libimobiledevice-utils build-essential pkg-config curl xz-utils \
    libclang-dev libasound2-dev libavcodec-dev libavutil-dev libswresample-dev

echo "== Kernelmodule"
printf 'options v4l2loopback video_nr=20 card_label=Mobcam exclusive_caps=1 max_buffers=4\n' > /etc/modprobe.d/irl4you-mobcam.conf
printf 'v4l2loopback\nsnd-aloop\n' > /etc/modules-load.d/irl4you-mobcam.conf
modprobe v4l2loopback 2>/dev/null || echo "Hinweis: v4l2loopback ließ sich noch nicht laden (nach einem Neustart erneut prüfen)"
modprobe snd-aloop 2>/dev/null || true

if [ -x "$BIN" ] && [ -z "${MOBCAM_REBUILD:-}" ]; then
    echo "== mobcam-virtualcam ist schon installiert ($BIN). Neu bauen mit: MOBCAM_REBUILD=1 $0"
    exit 0
fi

echo "== Quelltext"
rm -rf "$WORK"; mkdir -p "$WORK"; cd "$WORK"
curl -fsSL -o src.tar.xz "$URL"
echo "$SHA  src.tar.xz" | sha256sum -c -
tar xf src.tar.xz
cd "mobcam-$VER-source"
patch -p1 < "$HERE/mobcam-threads.patch"

echo "== Rust $RUST"
export RUSTUP_HOME=$WORK/rustup CARGO_HOME=$WORK/cargo
curl -fsSL -o "$WORK/rustup-init" https://static.rust-lang.org/rustup/dist/$(uname -m)-unknown-linux-gnu/rustup-init
chmod +x "$WORK/rustup-init"
"$WORK/rustup-init" -y --profile minimal --default-toolchain "$RUST" --no-modify-path >/dev/null

echo "== Bauen"
PATH=$CARGO_HOME/bin:$PATH cargo build --locked --release --package mobcam-virtualcam
install -m 755 target/release/mobcam-virtualcam "$BIN"
cd /; rm -rf "$WORK"
echo "Fertig. In Moblin die Stream-Adresse mobcam://localhost:7790 eintragen, dann unter Kameras > HDMI und USB die Quelle „Mobcam“ wählen."
