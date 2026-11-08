#!/usr/bin/env python3
"""Mobcam: ein iPhone mit Moblin liefert per USB-Kabel Bild und Ton. Die Box reicht beides unverändert an ihren RTMP-Eingang weiter.

Kein Dekodieren, kein Umrechnen, kein Neukodieren: Das HEVC- (oder H.264-)Bild und der AAC-Ton des iPhones gehen direkt als RTMP-Strom an SRS
(HEVC mit der Kennung 12, so wie Handys es senden; die Kette der Box versteht das). Dadurch kostet die Quelle fast keine Rechenzeit.

Ablauf: usbmuxd stellt die USB-Verbindung zu Port 7790 des iPhones her (dort wartet Moblin mit der Stream-Adresse mobcam://localhost:7790).
Das Nachrichtenformat ist einfach: Typ (1 Byte), Länge (4 Byte, Big Endian), Inhalt. Bild und Ton stehen schon so da, wie FLV sie braucht."""
import argparse
import os
import plistlib
import queue
import random
import re
import signal
import socket
import struct
import sys
import threading
import time

USBMUXD = "/var/run/usbmuxd"
PORT = 7790
WAIT = "Warte auf Moblin"
STALL = 8.0
STATS = bool(os.environ.get("IRL4YOU_MOBCAM_STATS"))
# Schutz der Live-Kette: Ihr RTMP-Eingang kommt mit mehr als etwa 13 Mbit/s je Strom nicht mehr mit (Verzug, Abstürze). Ein Strom über MAX_MBIT wird abgelehnt,
# bevor er die Kette erreicht; gemessen über die ersten WINDOW_US Mikrosekunden Bildzeit und danach fortlaufend.
MAX_MBIT = 12.0
WINDOW_US = 2000000
TOO_HIGH = "Die Bitrate in Moblin ist zu hoch. Bitte höchstens 10 Mbit/s einstellen."


class TooHigh(Exception):
    pass
CHUNK = 4096
MSG_HOST_HELLO, MSG_DEVICE_HELLO, MSG_VIDEO_CONFIG, MSG_VIDEO_FRAME, MSG_AUDIO_CONFIG, MSG_AUDIO_FRAME = 1, 2, 3, 4, 5, 6
CODEC_H264, CODEC_HEVC = 0, 1
FLV_CODEC = {CODEC_H264: 7, CODEC_HEVC: 12}
MAX_MESSAGE = 100 * 1024 * 1024


def say(text):
    sys.stderr.write(text + "\n")
    sys.stderr.flush()


# ---------------------------------------------------------------- USB über usbmuxd
class MuxError(Exception):
    pass


def _mux_request(sock, tag, body):
    data = plistlib.dumps(dict(body, ClientVersionString="irl4you", ProgName="irl4you", kLibUSBMuxVersion=3), fmt=plistlib.FMT_XML)
    sock.sendall(struct.pack("<IIII", 16 + len(data), 1, 8, tag) + data)
    head = _read_exact(sock, 16)
    total = struct.unpack("<I", head[:4])[0]
    if total < 16 or total > 4 * 1024 * 1024:
        raise MuxError("Antwort von usbmuxd ungültig")
    return plistlib.loads(_read_exact(sock, total - 16))


def _read_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise MuxError("Verbindung beendet")
        buf += chunk
    return bytes(buf)


def connect_phone(port=PORT, path=USBMUXD):
    """Verbindung zum ersten per USB angeschlossenen iPhone/iPad. Wirft MuxError, wenn keins da ist oder Moblin nicht wartet."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(path)
    except OSError:
        raise MuxError("usbmuxd ist nicht erreichbar")
    try:
        devs = [d for d in _mux_request(s, 1, {"MessageType": "ListDevices"}).get("DeviceList", [])
                if (d.get("Properties") or {}).get("ConnectionType", "USB") == "USB"]
    except (MuxError, OSError, plistlib.InvalidFileException, ValueError):
        s.close()
        raise MuxError("usbmuxd antwortet nicht")
    s.close()
    if not devs:
        raise MuxError("kein iPhone angeschlossen")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect(path)
        r = _mux_request(s, 1, {"MessageType": "Connect", "DeviceID": devs[0]["DeviceID"], "PortNumber": socket.htons(port)})
    except (MuxError, OSError):
        s.close()
        raise MuxError("usbmuxd antwortet nicht")
    if r.get("Number") != 0:
        s.close()
        raise MuxError("Moblin wartet nicht (Stream in Moblin starten)")
    s.settimeout(STALL)
    return s, str((devs[0].get("Properties") or {}).get("SerialNumber", ""))


# ---------------------------------------------------------------- RTMP (nur Senden)
def amf_value(v):
    if v is None:
        return b"\x05"
    if isinstance(v, bool):
        return b"\x01" + (b"\x01" if v else b"\x00")
    if isinstance(v, (int, float)):
        return b"\x00" + struct.pack(">d", float(v))
    if isinstance(v, str):
        b = v.encode()
        return b"\x02" + struct.pack(">H", len(b)) + b
    if isinstance(v, dict):
        out = b"\x03"
        for k, x in v.items():
            kb = k.encode()
            out += struct.pack(">H", len(kb)) + kb + amf_value(x)
        return out + b"\x00\x00\x09"
    raise ValueError("AMF-Typ nicht unterstützt")


def amf_command(*vals):
    return b"".join(amf_value(v) for v in vals)


def amf_read(data, i=0):
    t = data[i]
    i += 1
    if t == 0:
        return struct.unpack(">d", data[i:i + 8])[0], i + 8
    if t == 1:
        return bool(data[i]), i + 1
    if t == 2:
        n = struct.unpack(">H", data[i:i + 2])[0]
        return data[i + 2:i + 2 + n].decode("utf-8", "replace"), i + 2 + n
    if t in (3, 8):
        if t == 8:
            i += 4
        obj = {}
        while True:
            n = struct.unpack(">H", data[i:i + 2])[0]
            i += 2
            if n == 0 and data[i] == 9:
                return obj, i + 1
            k = data[i:i + n].decode("utf-8", "replace")
            v, i = amf_read(data, i + n)
            obj[k] = v
    if t in (5, 6):
        return None, i
    raise ValueError("AMF-Typ %d unbekannt" % t)


class RtmpError(Exception):
    pass


class Rtmp:
    """Minimaler RTMP-Sender: Handschlag, connect, createStream, publish, dann Audio-, Video- und Datenpakete."""

    def __init__(self, host, port, app, key):
        self.key = key
        self.stream_id = 0
        self.sock = socket.create_connection((host, port), timeout=10)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.chunk_in = 128
        self.inbox = queue.Queue()
        self.lock = threading.Lock()
        self._handshake()
        threading.Thread(target=self._reader, daemon=True).start()
        self._send(3, 0, 20, 0, amf_command("connect", 1, {"app": app, "type": "nonprivate", "flashVer": "FMLE/3.0 (compatible; irl4you)",
                                                           "tcUrl": "rtmp://%s:%d/%s" % (host, port, app)}))
        self._send(2, 0, 1, 0, struct.pack(">I", CHUNK))          # eigene Chunk-Größe
        self.chunk_out = CHUNK
        self._expect(1)
        self._send(3, 0, 20, 0, amf_command("createStream", 2, None))
        res = self._expect(2)
        self.stream_id = int(res[3]) if len(res) > 3 and isinstance(res[3], float) else 1
        self._send(3, 0, 20, self.stream_id, amf_command("publish", 3, None, key, "live"))
        self._expect_status("NetStream.Publish.Start")

    def _handshake(self):
        c1 = struct.pack(">II", 0, 0) + bytes(random.getrandbits(8) for _ in range(1528))
        self.sock.sendall(b"\x03" + c1)
        s = b""
        while len(s) < 1 + 1536 * 2:
            d = self.sock.recv(1 + 1536 * 2 - len(s))
            if not d:
                raise RtmpError("RTMP-Eingang schließt beim Handschlag")
            s += d
        self.sock.sendall(s[1:1537])

    def _reader(self):
        """Liest und verwirft, was SRS schickt; Antworten auf Befehle gehen in die Warteschlange."""
        last = {}
        buf = bytearray()
        sock = self.sock
        sock.settimeout(None)
        try:
            while True:
                d = sock.recv(65536)
                if not d:
                    break
                buf += d
                while True:
                    msg = self._parse(buf, last)
                    if msg is None:
                        break
                    if msg is not False:
                        self.inbox.put(msg)
        except OSError:
            pass
        self.inbox.put(None)

    def _parse(self, buf, last):
        """Ein Chunk aus buf; gibt (Typ, Inhalt) bei fertiger Nachricht, False wenn ein Chunk ohne fertige Nachricht, None wenn mehr Daten nötig."""
        if not buf:
            return None
        fmt, csid, i = buf[0] >> 6, buf[0] & 0x3F, 1
        if csid == 0:
            if len(buf) < 2:
                return None
            csid, i = buf[1] + 64, 2
        elif csid == 1:
            if len(buf) < 3:
                return None
            csid, i = buf[1] + buf[2] * 256 + 64, 3
        size = (11, 7, 3, 0)[fmt]
        if len(buf) < i + size:
            return None
        st = last.setdefault(csid, {"len": 0, "type": 0, "got": bytearray(), "ts": 0})
        h = buf[i:i + size]
        i += size
        if fmt <= 2:
            st["ts"] = int.from_bytes(h[0:3], "big")
        if fmt <= 1:
            st["len"], st["type"] = int.from_bytes(h[3:6], "big"), h[6]
        if st["ts"] == 0xFFFFFF:
            if len(buf) < i + 4:
                return None
            i += 4
        want = min(self.chunk_in, st["len"] - len(st["got"]))
        if len(buf) < i + want:
            return None
        st["got"] += buf[i:i + want]
        del buf[:i + want]
        if len(st["got"]) < st["len"]:
            return False
        payload, st["got"] = bytes(st["got"]), bytearray()
        if st["type"] == 1 and len(payload) >= 4:
            self.chunk_in = struct.unpack(">I", payload[:4])[0] & 0x7FFFFFFF
        return st["type"], payload

    def _commands(self, timeout):
        end = time.monotonic() + timeout
        while True:
            left = end - time.monotonic()
            if left <= 0:
                raise RtmpError("keine Antwort vom RTMP-Eingang")
            try:
                m = self.inbox.get(timeout=left)
            except queue.Empty:
                raise RtmpError("keine Antwort vom RTMP-Eingang")
            if m is None:
                raise RtmpError("RTMP-Eingang hat die Verbindung beendet")
            if m[0] == 20:
                vals, i = [], 0
                try:
                    while i < len(m[1]):
                        v, i = amf_read(m[1], i)
                        vals.append(v)
                except (ValueError, IndexError, struct.error):
                    pass
                yield vals

    def _expect(self, txn):
        for vals in self._commands(10):
            if len(vals) >= 2 and vals[0] in ("_result", "_error") and vals[1] == float(txn):
                if vals[0] == "_error":
                    raise RtmpError("RTMP-Eingang lehnt ab")
                return vals

    def _expect_status(self, code):
        for vals in self._commands(10):
            if vals and vals[0] == "onStatus" and len(vals) > 3 and isinstance(vals[3], dict):
                c = str(vals[3].get("code", ""))
                if c == code:
                    return
                if c.startswith("NetStream.Publish.") or c.endswith(("BadName", "Failed", "Rejected")):
                    raise RtmpError("RTMP-Eingang lehnt den Schlüssel ab (%s)" % c)

    def _send(self, csid, ts, mtype, sid, payload):
        n = len(payload)
        ext = ts >= 0xFFFFFF
        t3 = (0xFFFFFF if ext else ts).to_bytes(3, "big")
        e4 = struct.pack(">I", ts) if ext else b""
        chunk = getattr(self, "chunk_out", 128)
        out = [bytes([csid]) + t3 + n.to_bytes(3, "big") + bytes([mtype]) + struct.pack("<I", sid) + e4, payload[:chunk]]
        for off in range(chunk, n, chunk):
            out.append(bytes([0xC0 | csid]) + e4)
            out.append(payload[off:off + chunk])
        with self.lock:
            self.sock.sendall(b"".join(out))

    def send_data(self, ts, payload):
        self._send(5, ts, 18, self.stream_id, payload)

    def send_audio(self, ts, payload):
        self._send(4, ts, 8, self.stream_id, payload)

    def send_video(self, ts, payload):
        self._send(6, ts, 9, self.stream_id, payload)

    def close(self):
        """Sauber abmelden, damit SRS den Schlüssel sofort wieder freigibt (sonst meldet es beim Neuverbinden "Stream busy")."""
        try:
            if self.stream_id:
                self._send(3, 0, 20, self.stream_id, amf_command("FCUnpublish", 4, None, self.key))
                self._send(3, 0, 20, self.stream_id, amf_command("deleteStream", 5, None, float(self.stream_id)))
                time.sleep(0.2)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------- Mobcam-Nachrichten und FLV-Pakete
def read_message(sock):
    head = _read_exact(sock, 5)
    kind, length = head[0], struct.unpack(">I", head[1:])[0]
    if length > MAX_MESSAGE:
        raise MuxError("Nachricht zu groß")
    return kind, _read_exact(sock, length)


def parse_video_config(p):
    codec, w, h = p[0], struct.unpack(">H", p[1:3])[0], struct.unpack(">H", p[3:5])[0]
    n = struct.unpack(">I", p[5:9])[0]
    return codec, w, h, bytes(p[9:9 + n])


def parse_audio_config(p):
    rate, ch = struct.unpack(">I", p[1:5])[0], p[5]
    n = struct.unpack(">I", p[6:10])[0]
    return p[0], rate, ch, bytes(p[10:10 + n])


def flv_video(codec, keyframe, packet_type, body):
    return bytes([((1 if keyframe else 2) << 4) | FLV_CODEC.get(codec, 12), packet_type, 0, 0, 0]) + body


def flv_audio(packet_type, body):
    return bytes([0xAF, packet_type]) + body


def metadata(w, h, codec, audio):
    d = {"width": float(w), "height": float(h), "videocodecid": float(FLV_CODEC.get(codec, 12))}
    if audio:
        d["audiocodecid"] = 10.0
    return amf_command("@setDataFrame", "onMetaData", d)


class Session:
    """Eine Verbindung zu Moblin: Nachrichten lesen und als RTMP weitergeben."""

    def __init__(self, sock, args):
        self.sock, self.args = sock, args
        self.rtmp = None
        self.base = None
        self.vcfg = self.acfg = None
        self.audio_sent = self.video_sent = False
        self.have_key = False
        self.last_ts = {"v": 0, "a": 0}
        self.counts = {"v": 0, "a": 0}
        self.next_try = 0.0
        self.failed = 0
        self.window_us = getattr(args, "window_us", WINDOW_US)
        self.max_mbit = getattr(args, "max_mbit", MAX_MBIT)
        self.probing = self.window_us > 0
        self.pending = []
        self.win = None
        self.st = {"t": time.monotonic(), "last": 0.0, "gap": 0.0, "n": 0, "bytes": 0, "maxsz": 0}

    def stats(self, size):
        """Nur zur Fehlersuche (IRL4YOU_MOBCAM_STATS=1): Bilder pro Sekunde, größte Lücke zwischen zwei Bildern, Datenrate."""
        now = time.monotonic()
        st = self.st
        if st["last"]:
            st["gap"] = max(st["gap"], now - st["last"])
        st["last"] = now
        st["n"] += 1
        st["bytes"] += size
        st["maxsz"] = max(st["maxsz"], size)
        if now - st["t"] >= 5:
            say("info: %.1f Bilder/s, groesste Luecke %d ms, %.1f Mbit/s, groesstes Bild %d KB" % (st["n"] / (now - st["t"]), st["gap"] * 1000, st["bytes"] * 8 / 1e6 / (now - st["t"]), st["maxsz"] // 1024))
            st.update(t=now, gap=0.0, n=0, bytes=0, maxsz=0)

    def ts(self, pts_us, kind):
        if self.base is None:
            self.base = pts_us
        t = max(0, (pts_us - self.base) // 1000)
        t = max(t, self.last_ts[kind])
        self.last_ts[kind] = t
        return t

    def open(self):
        if self.rtmp is None:
            self.rtmp = Rtmp("127.0.0.1", self.args.rtmp_port, self.args.rtmp_app, self.args.key)
            codec, w, h, rec = self.vcfg
            self.rtmp.send_data(0, metadata(w, h, codec, self.args.audio == "mobcam"))
            self.rtmp.send_video(0, flv_video(codec, True, 0, rec))

    def check_rate(self, size, pts):
        """Misst die Datenrate des Bildes in Fenstern von window_us; wirft TooHigh, wenn sie über max_mbit liegt. True, wenn ein Fenster in Ordnung war."""
        if not self.window_us:
            return False
        if self.win is None:
            self.win = [pts, 0]
        self.win[1] += size
        span = pts - self.win[0]
        if span < self.window_us:
            return False
        mbit = self.win[1] * 8 / (span / 1e6) / 1e6
        self.win = [pts, 0]
        if mbit > self.max_mbit:
            raise TooHigh(mbit)
        return True

    def run(self):
        self.sock.sendall(bytes([MSG_HOST_HELLO]) + struct.pack(">I", 1) + bytes([1]))
        while True:
            kind, p = read_message(self.sock)
            ok = kind == MSG_VIDEO_FRAME and len(p) >= 9 and self.check_rate(len(p), struct.unpack(">Q", p[:8])[0])
            if self.probing:
                self.pending.append((kind, p))
                if ok:
                    self.probing = False
                    for k, q in self.pending:
                        self.handle(k, q)
                    self.pending = []
                continue
            self.handle(kind, p)

    def handle(self, kind, p):
        if kind == MSG_DEVICE_HELLO:
            try:
                import json
                j = json.loads(p[5:5 + struct.unpack(">I", p[1:5])[0]])
                say("Moblin %s auf %s verbunden" % (j.get("version", "?"), j.get("name", "iPhone")))
            except (ValueError, struct.error):
                say("Moblin verbunden")
        elif kind == MSG_VIDEO_CONFIG:
            self.vcfg = parse_video_config(p)
            codec, w, h, _ = self.vcfg
            say("Bild: %dx%d %s" % (w, h, "HEVC" if codec == CODEC_HEVC else "H.264"))
            if self.rtmp is not None:               # neue Einstellung während des Betriebs: Kopf erneut senden
                self.rtmp.send_video(self.last_ts["v"], flv_video(codec, True, 0, self.vcfg[3]))
            self.have_key = False
        elif kind == MSG_AUDIO_CONFIG:
            self.acfg = parse_audio_config(p)
            self.audio_sent = False
        elif kind == MSG_VIDEO_FRAME and self.vcfg:
            pts, flags = struct.unpack(">QB", p[:9])
            key = bool(flags & 1)
            if not self.have_key and not key:
                return
            if self.rtmp is None:
                # SRS gibt einen eben beendeten Sender erst nach einigen Sekunden frei: Bilder verwerfen und es erneut versuchen, Moblin bleibt verbunden
                if time.monotonic() < self.next_try:
                    return
                try:
                    self.open()
                except (RtmpError, OSError) as e:
                    self.failed += 1
                    self.next_try = time.monotonic() + 1.0
                    self.rtmp = None
                    if self.failed > 15:
                        raise
                    return
                self.failed = 0
            self.have_key = True
            if STATS and not self.counts["v"]:
                say("info: erstes Bild: Zeit %d us" % pts)
            self.rtmp.send_video(self.ts(pts, "v"), flv_video(self.vcfg[0], key, 1, p[9:]))
            self.counts["v"] += 1
            if STATS:
                self.stats(len(p))
        elif kind == MSG_AUDIO_FRAME and self.acfg and self.args.audio == "mobcam" and self.rtmp is not None:
            pts = struct.unpack(">Q", p[:8])[0]
            if STATS and not self.counts["a"]:
                say("info: erster Ton: Zeit %d ms nach dem ersten Bild (Basis %d)" % ((pts - self.base) // 1000 if self.base else -1, self.base or 0))
            if not self.audio_sent:
                self.rtmp.send_audio(self.last_ts["a"], flv_audio(0, self.acfg[3]))
                self.audio_sent = True
            self.rtmp.send_audio(self.ts(pts, "a"), flv_audio(1, p[8:]))
            self.counts["a"] += 1

    def close(self):
        if self.rtmp:
            self.rtmp.close()
        try:
            self.sock.close()
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True)
    ap.add_argument("--rtmp-port", type=int, required=True)
    ap.add_argument("--rtmp-app", required=True)
    ap.add_argument("--audio", choices=("mobcam", "none"), default="mobcam")
    args = ap.parse_args()
    if not re.match(r"^[a-z0-9][a-z0-9_-]{0,31}$", args.key) or not re.match(r"^[a-z0-9_]{1,20}$", args.rtmp_app):
        say("Ungültige Einstellung")
        sys.exit(2)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: (stop.set(), os._exit(0)))
    signal.signal(signal.SIGINT, lambda *_: (stop.set(), os._exit(0)))
    announced = None
    while not stop.is_set():
        try:
            sock, serial = connect_phone()
        except MuxError as e:
            if str(e) != announced:
                say("%s (%s)" % (WAIT, e))
                announced = str(e)
            time.sleep(1)
            continue
        announced = None
        session = Session(sock, args)
        rejected = False
        try:
            session.run()
        except TooHigh as e:
            rejected = True
            say("info: gemessen %.1f Mbit/s, erlaubt bis %.0f Mbit/s" % (e.args[0], MAX_MBIT))
            say(TOO_HIGH)
        except (MuxError, OSError, RtmpError, struct.error) as e:
            say("Verbindung zu Moblin beendet: %s" % (e if not isinstance(e, socket.timeout) else "Moblin sendet nicht mehr"))
        finally:
            session.close()
        if not rejected:
            say(WAIT)
        time.sleep(3 if rejected else 1)


if __name__ == "__main__":
    main()
