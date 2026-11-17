#!/usr/bin/env python3
"""pipbox-link: ein zweites Handy (App "IRL4YOU Stream Link") als zusätzlicher Sendeweg.

Das Hilfshandy hängt im selben Netz (Router) wie die Box und reicht UDP über seinen eigenen Mobilfunk an den SRTLA-Server weiter.
Dieser Dienst sucht es (HELLO als Rundruf), meldet die Box an (CHALLENGE -> OPEN -> OK), hält die Sitzung mit PING offen und trägt die
Leitung in /run/pipbox-link/links ein. irl4you-srtla bekommt sie von pipbox-send als Zeile "<Adresse der Box> via <Hilfshandy>:<Datenport>".

Einstellung: /var/lib/pipbox/link.json {"enabled": bool, "password": str, "iface": "" (alle) oder Name, "hosts": [IPv4, ...]}
Zustand:     /run/pipbox-link/status.json und /run/pipbox-link/links
Protokoll:   UDP, Steuerport 8390 des Hilfshandys; Magic "I4YL", Version 1, Typ, Nutzdaten (Zahlen Big-Endian).
"""
import fcntl
import hashlib
import hmac
import json
import os
import select
import signal
import socket
import struct
import sys
import time

CONF = os.environ.get("IRL4YOU_LINK_CONF", "/var/lib/pipbox/link.json")
SRTLA = os.environ.get("IRL4YOU_LINK_SRTLA", "/var/lib/pipbox/srtla.json")
RUN = os.environ.get("IRL4YOU_LINK_RUN", "/run/pipbox-link")
LINKS = f"{RUN}/links"
STATUS = f"{RUN}/status.json"
PORT = int(os.environ.get("IRL4YOU_LINK_PORT", "8390"))

MAGIC = b"I4YL"
VERSION = 1
HELLO, CHALLENGE, OPEN, OK, ERR, PING, PONG = 1, 2, 3, 4, 5, 6, 7
ERR_PASSWORD, ERR_NO_MOBILE, ERR_TARGET, ERR_BUSY = 1, 2, 3, 4
ERR_NAMES = {ERR_PASSWORD: "password", ERR_NO_MOBILE: "no_mobile", ERR_TARGET: "target", ERR_BUSY: "busy"}

PING_EVERY_S = 2.0
LOST_AFTER_S = 6.5          # 3 verpasste PONGs
OPEN_TIMEOUT_S = 5.0
RETRY_AFTER_ERR_S = 10.0
HELLO_SEARCH_S = 3.0        # ohne Hilfshandy auf der Karte so oft suchen
HELLO_IDLE_S = 20.0         # mit Hilfshandy seltener (weitere Hilfshandys finden)
MAX_HELPERS = 3
CONF_EVERY_S = 2.0
IFACE_EVERY_S = 5.0
SKIP_PREFIX = ("lo", "docker", "veth", "br-", "virbr", "p2p", "tailscale", "tun", "tap", "wg", "zt")


def log(msg):
    print(f"pipbox-link: {msg}", flush=True)


# ---- Protokoll ----

def message(kind, payload=b""):
    return MAGIC + bytes([VERSION, kind]) + payload


def parse(buf):
    """(Typ, Nutzdaten) oder None, wenn das Paket nicht zu diesem Protokoll gehört."""
    if len(buf) < 6 or buf[:4] != MAGIC or buf[4] != VERSION:
        return None
    return buf[5], buf[6:]


def mac(password, salt, host, port):
    key = password.encode("utf-8") or b"\0"
    return hmac.new(key, b"I4YL-open" + salt + struct.pack(">H", port) + host.encode("utf-8"), hashlib.sha256).digest()


def open_message(password, salt, host, port):
    h = host.encode("utf-8")
    if not 1 <= len(h) <= 255:
        raise ValueError("Ziel ungültig")
    return message(OPEN, salt + struct.pack(">HB", port, len(h)) + h + mac(password, salt, host, port))


def parse_challenge(data):
    if len(data) < 16:
        return None
    return data[:16], data[16:24]


def parse_ok(data):
    if len(data) < 6:
        return None
    return struct.unpack(">HI", data[:6])


def parse_pong(data):
    if len(data) < 22:
        return None
    session, battery, mobile, up, down = struct.unpack(">IBBQQ", data[:22])
    # Akku-Byte: 0..100 = Prozent, 255 = unbekannt; 128 + Prozent = das Handy lädt (ältere Apps senden nie 128..228, sie melden nur den Stand)
    level, charging = battery, False
    if battery >= 128:
        level, charging = battery - 128, True
    if level > 100:
        level, charging = None, False
    return {"session": session, "battery": level, "charging": charging, "mobile": bool(mobile), "up": up, "down": down}


# ---- Hilfsfunktionen ----

def load_json(path):
    try:
        with open(path) as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def put_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def iface_info(name):
    """(IPv4, Rundruf-Adresse) einer Karte oder None."""
    sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        ifr = struct.pack("256s", name[:15].encode())
        ip = socket.inet_ntoa(fcntl.ioctl(sk.fileno(), 0x8915, ifr)[20:24])
        mask = socket.inet_ntoa(fcntl.ioctl(sk.fileno(), 0x891b, ifr)[20:24])
    except OSError:
        return None
    finally:
        sk.close()
    ipn = struct.unpack(">I", socket.inet_aton(ip))[0]
    mn = struct.unpack(">I", socket.inet_aton(mask))[0]
    return ip, socket.inet_ntoa(struct.pack(">I", ipn | (~mn & 0xFFFFFFFF)))


def list_ifaces(want=""):
    fake = os.environ.get("IRL4YOU_LINK_FAKE_IFACE")  # nur für Tests: "name=IPv4"
    if fake:
        name, _, ip = fake.partition("=")
        return {name: (ip, ip)}
    try:
        names = sorted(os.listdir("/sys/class/net"))
    except OSError:
        return {}
    out = {}
    for name in names:
        if (want and name != want) or name.startswith(SKIP_PREFIX):
            continue
        info = iface_info(name)
        if info and not info[0].startswith("169.254."):
            out[name] = info
    return out


def target_from_srtla(path=None):
    """(Host, Port) des gewählten SRTLA-Servers oder None."""
    d = load_json(path or SRTLA)
    cur = next((s for s in d.get("servers", []) if isinstance(s, dict) and s.get("id") == d.get("selected")), None)
    if not cur:
        return None
    try:
        host, port = str(cur["host"]), int(cur["port"])
    except (KeyError, TypeError, ValueError):
        return None
    return (host, port) if host and 1 <= port <= 65535 else None


class Helper:
    def __init__(self, hid, ip, ctl_port, iface):
        self.hid = hid              # 8 Byte Kennung des Hilfshandys
        self.ip, self.ctl_port, self.iface = ip, ctl_port, iface
        self.state = "opening"      # opening | up | error
        self.session = self.data_port = None
        self.t_open = time.monotonic()
        self.t_ping = self.t_pong = 0.0
        self.battery, self.mobile, self.up, self.down = None, None, 0, 0
        self.charging = False
        self.err = None
        self.t_err = 0.0

    def public(self):
        d = {"id": self.hid.hex(), "ip": self.ip, "iface": self.iface, "state": self.state}
        if self.state == "up":
            d.update({"battery": self.battery, "charging": self.charging, "mobile": self.mobile, "mb_up": round(self.up / 1e6, 1),
                      "mb_down": round(self.down / 1e6, 1)})
        if self.err:
            d["error"] = self.err
        return d


class Linker:
    def __init__(self):
        self.conf = {}
        self.conf_mtime = None
        self.conf_t = 0.0
        self.ifaces = {}            # Name -> (IP, Rundruf)
        self.iface_t = -1e9
        self.socks = {}             # Name -> Socket
        self.helpers = {}           # Kennung -> Helper
        self.hello_t = {}           # Name -> Zeitpunkt des letzten HELLO
        self.salts = {}             # (Karte, Absender) -> unbenutzt
        self.target = None
        self.written = None
        self.stop = False

    # -- Einstellung --
    def reload_conf(self, now):
        if now - self.conf_t < CONF_EVERY_S:
            return
        self.conf_t = now
        c = load_json(CONF)
        self.conf = {"enabled": bool(c.get("enabled")), "password": str(c.get("password", "")), "iface": str(c.get("iface", "")),
                     "hosts": [h for h in c.get("hosts", []) if isinstance(h, str)][:8]}
        self.target = target_from_srtla()

    @property
    def enabled(self):
        return bool(self.conf.get("enabled"))

    # -- Karten --
    def refresh_ifaces(self, now):
        if now - self.iface_t < IFACE_EVERY_S:
            return
        self.iface_t = now
        have = list_ifaces(self.conf.get("iface", ""))
        for name in list(self.socks):
            if name not in have or have[name][0] != self.ifaces.get(name, (None,))[0]:
                self.close_iface(name)
        self.ifaces = have
        for name, (ip, _bc) in have.items():
            if name in self.socks:
                continue
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.bind((ip, 0))
                s.setblocking(False)
            except OSError:
                continue
            self.socks[name] = s

    def close_iface(self, name):
        s = self.socks.pop(name, None)
        if s:
            s.close()
        for hid in [h for h, x in self.helpers.items() if x.iface == name]:
            del self.helpers[hid]

    def close_all(self):
        for name in list(self.socks):
            self.close_iface(name)
        self.helpers.clear()
        self.hello_t.clear()
        self.salts.clear()

    # -- Senden --
    def send_hello(self, name, now):
        s = self.socks.get(name)
        if not s:
            return
        up = any(h.state == "up" and h.iface == name for h in self.helpers.values())
        if now - self.hello_t.get(name, -1e9) < (HELLO_IDLE_S if up else HELLO_SEARCH_S):
            return
        self.hello_t[name] = now
        dests = [(self.ifaces[name][1], PORT)]
        dests += [(h, PORT) for h in self.conf.get("hosts", []) if (h, PORT) not in dests]
        for d in dests:
            try:
                s.sendto(message(HELLO), d)
            except OSError:
                pass

    def send_open(self, name, addr, salt, hid):
        s = self.socks.get(name)
        if not s or not self.target:
            return
        host, port = self.target
        try:
            s.sendto(open_message(self.conf.get("password", ""), salt, host, port), addr)
        except (OSError, ValueError):
            return
        h = self.helpers.get(hid)
        if h is None:
            h = self.helpers[hid] = Helper(hid, addr[0], addr[1], name)
        h.state, h.t_open, h.err = "opening", time.monotonic(), None

    # -- Empfangen --
    def handle(self, name, addr, buf, now):
        p = parse(buf)
        if not p:
            return
        kind, data = p
        if kind == CHALLENGE:
            c = parse_challenge(data)
            if not c or not self.target:
                return
            salt, hid = c
            h = self.helpers.get(hid)
            if h is not None:
                # Gilt nur die jüngste Zufallszahl des Hilfshandys: bei "opening" mit ihr noch einmal anmelden
                if h.state == "up" or (h.state == "error" and now - h.t_err < RETRY_AFTER_ERR_S):
                    return
            elif len(self.helpers) >= MAX_HELPERS:
                return
            self.send_open(name, addr, salt, hid)
            return
        h = next((x for x in self.helpers.values() if x.iface == name and x.ip == addr[0]), None)
        if h is None:
            return
        if kind == OK and h.state == "opening":
            ok = parse_ok(data)
            if ok:
                h.data_port, h.session = ok
                h.state, h.t_pong, h.t_ping, h.err = "up", now, 0.0, None
                log("Hilfshandy verbunden")
        elif kind == ERR and h.state == "opening":
            h.err = ERR_NAMES.get(data[0] if data else 0, "other")
            h.state, h.t_err = "error", now
            log(f"Hilfshandy lehnt ab ({h.err})")
        elif kind == PONG and h.state == "up":
            pg = parse_pong(data)
            if pg and pg["session"] == h.session:
                h.t_pong = now
                h.battery, h.mobile, h.up, h.down = pg["battery"], pg["mobile"], pg["up"], pg["down"]
                h.charging = pg["charging"]

    # -- Takt --
    def tick(self, now):
        for name in list(self.socks):
            self.send_hello(name, now)
        for hid, h in list(self.helpers.items()):
            s = self.socks.get(h.iface)
            if h.state == "opening" and now - h.t_open > OPEN_TIMEOUT_S:
                del self.helpers[hid]
            elif h.state == "error" and now - h.t_err > RETRY_AFTER_ERR_S:
                del self.helpers[hid]
            elif h.state == "up":
                if now - h.t_pong > LOST_AFTER_S:
                    log("Hilfshandy verloren")
                    del self.helpers[hid]
                elif s and now - h.t_ping >= PING_EVERY_S:
                    h.t_ping = now
                    try:
                        s.sendto(message(PING, struct.pack(">I", h.session)), (h.ip, h.ctl_port))
                    except OSError:
                        pass
        self.publish()

    def link_lines(self):
        lines = []
        for h in self.helpers.values():
            if h.state == "up" and h.iface in self.ifaces:
                lines.append(f"{self.ifaces[h.iface][0]} via {h.ip}:{h.data_port}")
        return sorted(lines)

    def publish(self):
        lines = self.link_lines()
        st = {"enabled": self.enabled, "target": bool(self.target),
              "helpers": [h.public() for h in self.helpers.values()],
              "searching": self.enabled and bool(self.socks) and not lines,
              "ifaces": sorted(self.socks)}
        sig = (lines, json.dumps(st, sort_keys=True))
        if sig == self.written:
            return
        self.written = sig
        try:
            if lines:
                put_file(LINKS, "".join(l + "\n" for l in lines))
            else:
                self.remove_links()
            put_file(STATUS, json.dumps(st) + "\n")
        except OSError as e:
            log(f"Zustand nicht schreibbar: {e}")

    @staticmethod
    def remove_links():
        try:
            os.unlink(LINKS)
        except FileNotFoundError:
            pass

    # -- Lauf --
    def step(self, now=None, timeout=0.25):
        now = time.monotonic() if now is None else now
        self.reload_conf(now)
        if not self.enabled:
            if self.socks or self.helpers:
                self.close_all()
            self.publish()
            time.sleep(timeout)
            return
        self.refresh_ifaces(now)
        socks = {s: n for n, s in self.socks.items()}
        if socks:
            r, _, _ = select.select(list(socks), [], [], timeout)
            for s in r:
                for _ in range(32):
                    try:
                        buf, addr = s.recvfrom(2048)
                    except (BlockingIOError, OSError):
                        break
                    self.handle(socks[s], addr, buf, now)
        else:
            time.sleep(timeout)
        self.tick(now)

    def run(self):
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "stop", True))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "stop", True))
        while not self.stop:
            try:
                self.step()
            except Exception as e:  # der Dienst soll nicht an einem Einzelfall sterben
                log(f"Fehler: {type(e).__name__}")
                time.sleep(1)
        self.close_all()
        self.remove_links()


def main(argv):
    if len(argv) > 1 and argv[1] == "once":
        print(json.dumps(list_ifaces()))
        return 0
    Linker().run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
