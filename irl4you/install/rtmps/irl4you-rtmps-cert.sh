#!/bin/sh
# Legt beim ersten Start ein eigenes, selbstsigniertes Zertifikat für den RTMPS-Eingang (Port 1934) an, falls keines da ist.
# Jede Box bekommt so ihren eigenen Schlüssel; im Image selbst liegt keiner.
set -eu
D=${RTMPS_DIR:-/etc/nginx/certs/rtmps}
[ -s "$D/cert.pem" ] && [ -s "$D/privkey.pem" ] && exit 0
install -d -m 755 "$D"
umask 077
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=irl4you-box" -keyout "$D/privkey.pem.tmp" -out "$D/cert.pem.tmp" 2>/dev/null
chmod 600 "$D/privkey.pem.tmp"
chmod 644 "$D/cert.pem.tmp"
mv "$D/privkey.pem.tmp" "$D/privkey.pem"
mv "$D/cert.pem.tmp" "$D/cert.pem"
