#!/usr/bin/env python3
"""IRL4YOU BOX: feste Namen für die LAN-Karten (eth0, eth1, …) nach ihrer MAC-Adresse.

Mit net.ifnames=0 vergibt der Kernel eth0/eth1 in der Reihenfolge, in der die Karten bereit werden. Auf dem Orange Pi 5 Plus tauschen die beiden
Karten dabei manchmal die Namen (gesehen am 17.10.2026). Dieses Programm legt die Zuordnung MAC -> Name fest und schreibt sie als systemd-.link-Dateien
(/etc/systemd/network/10-irl4you-<name>.link). udev wendet sie beim nächsten Start an, wenn die Karten erscheinen.

WICHTIG: Im laufenden Betrieb benennt es nie um. Ein Umbenennen im Betrieb (per ip-Befehl) trennt die Karte, NetworkManager bricht DHCP ab und die Box ist
nicht mehr erreichbar (so geschehen beim ersten Update-Test am 17.10.2026). Darum schreibt der normale Aufruf nur Dateien; wirksam werden sie beim Start.

Die .link-Dateien allein reichen nicht: Haben zwei Karten die Namen getauscht (eth0 <-> eth1), scheitert udev mit „File exists“, weil jeder Zielname schon
belegt ist, und die zufällige Reihenfolge des Kernels bleibt (gesehen am 17.11.2026). Darum läuft beim Start, vor dem Netzwerk, einmalig
`pipbox-netnames.py --boot` (Dienst pipbox-netnames.service, Before=network-pre.target): Es tauscht über Zwischennamen (eth0 -> pbn0, eth1 -> pbn1, dann pbn0 -> eth1,
pbn1 -> eth0). Das geschieht nur, solange die Karten noch nicht aktiv sind (Schalter UP aus); jeder Fehler lässt die Namen unverändert.

Quelle der Zuordnung, in dieser Reihenfolge:
  1. /etc/pipbox/netnames.json  ({"<mac>": "eth0", …}), wenn vorhanden
  2. die Namen, die IRL4YOU zuletzt gesehen hat (/var/lib/pipbox/iface-macs.json)
  3. die Lage der Karte am Bus (gleich auf jeder Box desselben Boards)

  pipbox-netnames.py           Zuordnung anlegen (falls noch keine da ist) und .link-Dateien schreiben
  pipbox-netnames.py --show    Zuordnung anzeigen, nichts schreiben
  pipbox-netnames.py --boot    Namen beim Start nach der Zuordnung herstellen (nur vom Dienst beim Start, nie im Betrieb)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

SYS_NET = "/sys/class/net"
CONF = "/etc/pipbox/netnames.json"
SEEN = "/var/lib/pipbox/iface-macs.json"
LINK_DIR = "/etc/systemd/network"
LINK_PREFIX = "10-irl4you-"
MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
NAME_RE = re.compile(r"^eth\d{1,2}$")
WLAN_RE = re.compile(r"^wlan\d{1,2}$")
ANY_NAME_RE = re.compile(r"^(eth|wlan)\d{1,2}$")


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def wired_cards(sysnet=SYS_NET):
    """Eingebaute und USB-LAN-Karten: {name: (mac, bus_path)}; ohne WLAN, Brücken, virtuelle Karten."""
    out = {}
    try:
        names = sorted(os.listdir(sysnet))
    except OSError:
        return out
    for n in names:
        base = os.path.join(sysnet, n)
        if _read(os.path.join(base, "type")) != "1" or not os.path.exists(os.path.join(base, "device")):
            continue
        if any(os.path.isdir(os.path.join(base, d)) for d in ("wireless", "phy80211", "bridge")):
            continue
        if not NAME_RE.match(n):
            continue
        mac = _read(os.path.join(base, "address")).lower()
        if MAC_RE.match(mac):
            out[n] = (mac, os.path.realpath(os.path.join(base, "device")))
    return out


def wifi_cards(sysnet=SYS_NET):
    """WLAN-Karten (USB-Sticks u. a.): {name: (mac, bus_path)}. Die Schnittstelle p2p0 (gleiche MAC wie wlan0) zählt nicht."""
    out = {}
    try:
        names = sorted(os.listdir(sysnet))
    except OSError:
        return out
    for n in names:
        base = os.path.join(sysnet, n)
        if not WLAN_RE.match(n) or not os.path.exists(os.path.join(base, "device")):
            continue
        mac = _read(os.path.join(base, "address")).lower()
        if MAC_RE.match(mac):
            out[n] = (mac, os.path.realpath(os.path.join(base, "device")))
    return out


def initial_map(cards, seen, prefix="eth"):
    """Erste Zuordnung: zuletzt gesehene Namen, sonst nach Bus-Lage."""
    name_re = WLAN_RE if prefix == "wlan" else NAME_RE
    m = {}
    for name, mac in (seen or {}).items():
        if isinstance(name, str) and name_re.match(name) and isinstance(mac, str) and MAC_RE.match(mac.lower()):
            if mac.lower() not in m and name not in m.values():
                m[mac.lower()] = name
    rest = sorted((path, mac) for mac, path in cards.values() if mac not in m)
    i = 0
    for _path, mac in rest:
        while "%s%d" % (prefix, i) in m.values():
            i += 1
        m[mac] = "%s%d" % (prefix, i)
    return m


def link_text(mac, name):
    # WLAN: nur Schnittstellen, die der Kernel wlanN nennt (p2p0 hat dieselbe MAC und darf den Namen nicht bekommen)
    match = "OriginalName=wlan*" if name.startswith("wlan") else "Type=ether"
    return ("# IRL4YOU BOX: feste Kartennamen nach MAC (pipbox-netnames.py). Gilt ab dem nächsten Start, nie im laufenden Betrieb.\n"
            "[Match]\nMACAddress=%s\n%s\n\n[Link]\nName=%s\n" % (mac, match, name))


def write_links(mapping, link_dir=LINK_DIR):
    """Schreibt je Karte eine .link-Datei und entfernt veraltete eigene. Gibt (geschrieben, entfernt) zurück."""
    os.makedirs(link_dir, exist_ok=True)
    want = {LINK_PREFIX + name + ".link": link_text(mac, name) for mac, name in mapping.items()}
    written, removed = [], []
    for fn, text in want.items():
        p = os.path.join(link_dir, fn)
        if _read(p) != text.strip():
            with open(p + ".tmp", "w") as f:
                f.write(text)
            os.replace(p + ".tmp", p)
            written.append(fn)
    for fn in os.listdir(link_dir):
        if fn.startswith(LINK_PREFIX) and fn.endswith(".link") and fn not in want:
            os.remove(os.path.join(link_dir, fn))
            removed.append(fn)
    return written, removed


def load_conf(path=CONF):
    try:
        with open(path) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    return {k.lower(): v for k, v in d.items() if isinstance(k, str) and MAC_RE.match(k.lower()) and isinstance(v, str) and ANY_NAME_RE.match(v)}


TMP_PREFIX = "pbn"      # Zwischennamen beim Tauschen (pbn0, pbn1, …)


def plan_renames(cur, want):
    """Welche Karten müssen wie umbenannt werden? cur: {Name: MAC} der vorhandenen Karten, want: {MAC: Name} der festen Namen.
    Gibt [(alter Name, neuer Name), …] zurück. Karten ohne festen Namen, die einen festen Namen belegen, ziehen auf einen freien um.
    Widersprüchliche Zuordnung (zwei Karten, ein Name): nichts tun."""
    target = {old: want[mac] for old, mac in cur.items() if want.get(mac) and want[mac] != old}
    finals = [want[mac] for old, mac in cur.items() if want.get(mac)]
    if len(finals) != len(set(finals)):
        return []
    taken = set(finals) | set(cur)
    for old in sorted(cur):
        if old in target or want.get(cur[old]) == old or old not in finals:
            continue
        kind = "wlan" if old.startswith("wlan") else "eth"
        k = 0
        while "%s%d" % (kind, k) in taken:
            k += 1
        target[old] = "%s%d" % (kind, k)
        taken.add(target[old])
    return sorted(target.items())


def ip_rename(old, new):
    ip = shutil.which("ip") or "/usr/sbin/ip"
    r = subprocess.run([ip, "link", "set", "dev", old, "name", new], capture_output=True, text=True, timeout=10)
    return r.returncode == 0


def is_up(name, sysnet=SYS_NET):
    """Schalter UP der Karte gesetzt? Aktive Karten werden nie umbenannt (unbekannt gilt als aktiv)."""
    try:
        return bool(int(_read(os.path.join(sysnet, name, "flags")), 16) & 1)
    except ValueError:
        return True


def apply_renames(moves, rename=ip_rename):
    """Führt die Umbenennung über Zwischennamen aus. Schlägt ein Schritt fehl, wird alles auf die alten Namen zurückgesetzt, soweit möglich."""
    tmp = {old: "%s%d" % (TMP_PREFIX, i) for i, (old, _new) in enumerate(moves)}
    done = []
    for old, _new in moves:
        if not rename(old, tmp[old]):
            for o in reversed(done):
                rename(tmp[o], o)
            return False
        done.append(old)
    ok = True
    for old, new in moves:
        if not rename(tmp[old], new):
            ok = False
            rename(tmp[old], old)       # Zwischenname darf nie stehen bleiben
    return ok


def boot_fix(sysnet=SYS_NET, conf=CONF, rename=ip_rename, wait_s=8.0, sleep=time.sleep):
    """Beim Start: Namen nach der festen Zuordnung herstellen. Gibt immer 0 zurück (der Start darf daran nie scheitern)."""
    try:
        mapping = load_conf(conf) or {}
        if not mapping:
            return 0
        wired = [m for m, n in mapping.items() if n.startswith("eth")]
        waited = 0.0
        while waited < wait_s and not all(m in {v[0] for v in wired_cards(sysnet).values()} for m in wired):
            sleep(0.5)
            waited += 0.5       # Karten, die gerade erst erscheinen, kurz abwarten (fehlende Steckkarten kosten höchstens diese Zeit)
        cur = {n: v[0] for n, v in {**wired_cards(sysnet), **wifi_cards(sysnet)}.items()}
        moves = plan_renames(cur, mapping)
        if not moves:
            print("pipbox-netnames: Namen stimmen mit der Zuordnung überein")
            return 0
        busy = [n for pair in moves for n in pair if n in cur and is_up(n, sysnet)]
        if busy:
            print("pipbox-netnames: Karte(n) schon aktiv (%s): nichts umbenannt" % ", ".join(sorted(set(busy))))
            return 0
        ok = apply_renames(moves, rename)
        print("pipbox-netnames: %s: %s" % ("umbenannt" if ok else "Umbenennen fehlgeschlagen, alte Namen belassen", ", ".join("%s -> %s" % m for m in moves)))
    except Exception as e:      # nichts darf den Start aufhalten
        print("pipbox-netnames: Fehler, nichts geändert: %s" % e)
    return 0


def main(argv):
    if "--boot" in argv:
        return boot_fix()
    cards = wired_cards()
    wifi = wifi_cards()
    conf = load_conf()
    mapping = dict(conf) if conf is not None else None
    try:
        with open(SEEN) as f:
            seen = json.load(f)
    except (OSError, ValueError):
        seen = {}
    seen = seen if isinstance(seen, dict) else {}
    if mapping is None:
        mapping = initial_map(cards, seen)
    # Feste WLAN-Namen nur für Sticks, die gerade stecken: Sticks mit wechselnder MAC sollen keine Namen ansammeln
    here = {v[0] for v in wifi.values()}
    mapping = {m: n for m, n in mapping.items() if not WLAN_RE.match(n) or m in here}
    # WLAN-Karten, die noch keinen festen Namen haben, bekommen einen (neue Sticks kommen später dazu); LAN-Zuordnung bleibt unberührt
    new_wifi = {n: v for n, v in wifi.items() if v[0] not in mapping}
    if new_wifi:
        taken = {n for m, n in mapping.items() if WLAN_RE.match(n)}
        extra = initial_map(new_wifi, {k: v for k, v in seen.items() if k not in taken}, "wlan")
        for mac, name in extra.items():
            while name in taken:
                name = "wlan%d" % (int(name[4:]) + 1)
            taken.add(name)
            mapping[mac] = name
    # Neue LAN-Karten (zum Beispiel USB-Netzwerkkarten) bekommen ebenfalls einen festen Namen; die eingebauten bleiben, wie sie sind
    new_wired = {n: v for n, v in cards.items() if v[0] not in mapping}
    if new_wired and conf is not None:
        taken = {n for m, n in mapping.items() if NAME_RE.match(n)}
        extra = initial_map(new_wired, {k: v for k, v in seen.items() if k not in taken}, "eth")
        for mac, name in extra.items():
            while name in taken:
                name = "eth%d" % (int(name[3:]) + 1)
            taken.add(name)
            mapping[mac] = name
    if "--show" in argv:
        print(json.dumps({"cards": {n: m for n, (m, _p) in {**cards, **wifi}.items()}, "mapping": mapping}, indent=1))
        return 0
    if not mapping:
        return 0
    if conf is None or mapping != conf:
        os.makedirs(os.path.dirname(CONF), exist_ok=True)
        with open(CONF + ".tmp", "w") as f:
            json.dump(mapping, f, indent=1, sort_keys=True)
        os.replace(CONF + ".tmp", CONF)
        print("pipbox-netnames: Zuordnung angelegt: " + ", ".join("%s=%s" % (v, k) for k, v in sorted(mapping.items(), key=lambda x: x[1])))
    written, removed = write_links(mapping)
    if written or removed:
        print("pipbox-netnames: .link-Dateien geschrieben: %s (gilt ab dem nächsten Start)" % (", ".join(written + ["-" + r for r in removed])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
