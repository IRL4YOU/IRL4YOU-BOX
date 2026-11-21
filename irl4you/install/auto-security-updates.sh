#!/bin/sh
# Ubuntu-Systemupdates (Sicherheit und normale Korrekturen) laufen NUR mit einem IRL4YOU-Update (Commit auf main):
# kein eigener Zeitplan auf der Box, denn der Updater startet nie waehrend einer Uebertragung. Nie automatischer
# Neustart, niedrige Prioritaet. Betrifft ein Update Systemteile, die erst nach einem Neustart wirken, steht
# /run/reboot-required (wie bei Ubuntu); die Oberflaeche zeigt dann einen Hinweis mit Knopf "Neu starten".
# Mehrfach lauffaehig; bei jedem Update wird einmal geprueft und eingespielt.
set -u
if ! dpkg -s unattended-upgrades >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get update -q >/dev/null 2>&1 || true
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends unattended-upgrades >/dev/null 2>&1 || { echo "auto-security-updates: Installation fehlgeschlagen"; exit 0; }
fi
cat > /etc/apt/apt.conf.d/52irl4you-unattended <<'CONF'
// IRL4YOU Box: Ubuntu-Updates nur mit einem IRL4YOU-Update, kein automatischer Neustart
Unattended-Upgrade::Allowed-Origins:: "${distro_id}:${distro_codename}-security";
Unattended-Upgrade::Allowed-Origins:: "${distro_id}:${distro_codename}-updates";
Unattended-Upgrade::Allowed-Origins:: "${distro_id}ESMApps:${distro_codename}-apps-security";
Unattended-Upgrade::Allowed-Origins:: "${distro_id}ESM:${distro_codename}-infra-security";
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "false";
Unattended-Upgrade::Remove-Unused-Dependencies "false";
Unattended-Upgrade::MinimalSteps "true";
CONF
# kein Zeitplan: weder Listen-Aktualisierung noch Upgrade von selbst
printf 'APT::Periodic::Update-Package-Lists "0";\nAPT::Periodic::Unattended-Upgrade "0";\n' > /etc/apt/apt.conf.d/20auto-upgrades
rm -rf /etc/systemd/system/apt-daily.service.d/irl4you-low-priority.conf /etc/systemd/system/apt-daily-upgrade.service.d/irl4you-low-priority.conf
systemctl disable --now apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1 || true
systemctl daemon-reload
# Pakete, die erst nach einem Neustart voll wirken (Kernel nur falls von Ubuntu, Systemverwaltung, C-Bibliothek, D-Bus)
BOOT_PKGS="systemd udev libc6 dbus libsystemd0 libudev1 linux-image-generic"
snap() { dpkg-query -W -f='${Package} ${Version}\n' $BOOT_PKGS 2>/dev/null | sort; }
before=$(snap)
# einmal jetzt: Listen holen und Updates einspielen (niedrige Prioritaet)
DEBIAN_FRONTEND=noninteractive nice -n 19 ionice -c3 apt-get update -q >/dev/null 2>&1 || true
nice -n 19 ionice -c3 unattended-upgrade >/var/log/irl4you-security-updates.log 2>&1 || true
after=$(snap)
if [ "$before" != "$after" ]; then
    echo "*** System restart required ***" > /run/reboot-required
    printf '%s\n' "$before" > /run/reboot-required.old; printf '%s\n' "$after" > /run/reboot-required.new
    diff /run/reboot-required.old /run/reboot-required.new | sed -n 's/^> \([^ ]*\) .*/\1/p' | sort > /run/reboot-required.pkgs
    rm -f /run/reboot-required.old /run/reboot-required.new
fi
echo "auto-security-updates: geprueft und eingespielt (Log: /var/log/irl4you-security-updates.log)"
