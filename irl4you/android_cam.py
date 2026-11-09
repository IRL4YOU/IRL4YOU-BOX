#!/usr/bin/env python3
"""Android-Handy als Kamera: Bild und Ton kommen per USB (Android Open Accessory), die Box reicht sie unverändert an SRS weiter.

Reines Python ohne Zusatzpakete (USB über /dev/bus/usb, usbfs). Eigenes Protokoll zwischen der App „IRL4YOU Cam“ und der Box,
kein Fremdcode. Rahmen: Typ (1 Byte), Länge (4 Byte, Big Endian), Inhalt.
  --dry          nur lesen und Kennzahlen zeigen, nichts an SRS senden
  --audio none   den Ton des Handys verwerfen
  --audio usb    statt des Handy-Tons das erste USB-Mikrofon (zum Beispiel DJI-Empfänger) aufnehmen, AAC kodieren und mit dem Bild senden;
                 --audio-offset MS verschiebt den Ton gegenüber dem Bild (positiv = später)
  --key/--rtmp-port/--rtmp-app wie mobcam_rtmp.py (nutzt dessen RTMP-Sender)
Braucht Root (oder Rechte auf /dev/bus/usb)."""
import argparse
import ctypes
import errno
import fcntl
import glob
import json
import os
import re
import signal
import struct
import subprocess
import sys
import threading
import time

ACCESSORY_IDS = {("18d1", "2d00"), ("18d1", "2d01"), ("18d1", "2d04"), ("18d1", "2d05")}
# Hersteller-Kennungen von Android-Handys (ohne 0b05 ASUS und 0e8d MediaTek: dort melden sich auch Bluetooth- und WLAN-Sticks)
VENDORS = {"04e8", "2a70", "22d9", "18d1", "2717", "12d1", "0fce", "0bb4", "1004", "05c6", "1bbb", "2d95", "2ae5", "19d2"}
MAX_MBIT = 10.0                                       # die Live-Kette nimmt je Strom höchstens etwa 12 Mbit/s; die Box stellt das Handy darauf herunter

MSG_CONFIG, MSG_VIDEO_CSD, MSG_VIDEO, MSG_AUDIO_CSD, MSG_AUDIO, MSG_STATS, MSG_ROTATE = 1, 2, 3, 4, 5, 6, 7
CMD_KEYFRAME, CMD_BITRATE, CMD_CONFIG = 0x10, 0x11, 0x12      # 0x12: App soll CONFIG, Parametersätze und ein Schlüsselbild neu senden (ältere Apps ignorieren es)
MAX_MESSAGE = 8 * 1024 * 1024
HOLD_S = 3.5                           # so lange wartet der Helfer nach dem Schließen des Stroms, bevor er einen neuen öffnet: die Live-Kette der Box
                                       # schaltet den Kamerazweig ab (bis ca. 3 s), erst dann darf ein Bild in neuer Größe kommen (GStreamer-Fehler in videorate)
STALL_S = 3.0                          # so lange darf kein Bild an die Box gehen, obwohl die App sendet, bevor der Helfer Konfiguration und Schlüsselbild neu anfordert
VIDEO_JUMP_MS = 250                    # so viel später als sein Zeitstempel darf ein Bild ankommen, bevor die Zeit nachgezogen wird


def say(text):
    sys.stderr.write(text + "\n")
    sys.stderr.flush()


PHONE_EVERY_S = 3.0                    # so oft reicht die Handyzeile für den Dienst (sie dient der Anzeige, nicht der Regelung)


def phone_values(d):
    """Prüft die Handydaten der App: bat 0..100, chg/plug/cur_cal 0/1, cur in mA (netto am Akku, Betrag unter 10000), temp in °C (-20..90), thermal 0..6; Unplausibles wird weggelassen"""
    def num(k, lo, hi, digits=None):
        v = d.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not lo <= v <= hi:
            return None
        return round(v, digits) if digits is not None else int(round(v))
    out = {}
    for k, v in (("bat", num("bat", 0, 100)), ("cur", num("cur", -9999, 9999)), ("temp", num("temp", -20, 90, 1)), ("thermal", num("thermal", 0, 6))):
        if v is not None:
            out[k] = v
    for k in ("chg", "plug", "cur_cal"):                 # chg: lädt; plug: Kabel steckt; cur_cal: App kennt die Stromrichtung (ohne sie fehlt cur)
        v = d.get(k)
        if v in (0, 1, True, False):
            out[k] = 1 if v else 0
    return out


# ---------------------------------------------------------------- USB-Mikrofon als Ton
AAC_RATES = (96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000)
MIC_RESYNC_MS = 120                    # so weit darf der Zeitstempel eines Tonrahmens von der Uhr des Bilds abweichen, bevor er neu angesetzt wird
ALSA_CLOCK = ["provide-clock=false", "slave-method=resample"]


def usb_capture_card(asound="/proc/asound"):
    """Erste USB-Tonkarte mit Aufnahme (Mikrofon-Empfänger, Mischpult), als ALSA-Name plughw:CARD=<id>; None, wenn keine steckt."""
    try:
        cards = sorted(os.listdir(asound), key=lambda c: (len(c), c))
    except OSError:
        return None
    for c in cards:
        base = os.path.join(asound, c)
        if not re.match(r"^card\d{1,2}$", c) or not os.path.exists(os.path.join(base, "usbbus")):
            continue
        try:
            has_capture = any(re.match(r"^pcm\d+c$", d) for d in os.listdir(base))
            with open(os.path.join(base, "id")) as f:
                cid = f.read(40).strip()
        except OSError:
            continue
        if has_capture and re.match(r"^[A-Za-z0-9_]{1,40}$", cid):
            return "plughw:CARD=" + cid
    return None


def usb_audio_argv(device):
    """GStreamer: Mikrofon aufnehmen, als AAC-LC mit ADTS-Kopf auf die Standardausgabe schreiben (48 kHz, Stereo, 128 kbit/s)."""
    if not re.match(r"^plughw:CARD=[A-Za-z0-9_]{1,40}$", device):
        raise ValueError("Tonkarte ungültig")
    return (["gst-launch-1.0", "-q", "alsasrc", "device=" + device] + ALSA_CLOCK +
            ["!", "audioconvert", "!", "audioresample", "!", "audio/x-raw,rate=48000,channels=2", "!", "voaacenc", "bitrate=128000", "!",
             "aacparse", "!", "audio/mpeg,mpegversion=4,stream-format=adts", "!", "fdsink", "fd=1"])


def adts_split(buf):
    """Zerlegt einen ADTS-Datenstrom in (AAC-Rahmen ohne Kopf, AudioSpecificConfig, Abtastrate); Rest ist der angefangene letzte Rahmen."""
    frames, i = [], 0
    while True:
        j = buf.find(b"\xff", i)
        if j < 0:
            return frames, b""
        if len(buf) - j < 7:
            return frames, buf[j:]
        b = buf[j:j + 7]
        if (b[1] & 0xF0) != 0xF0 or (b[1] & 0x06) != 0:
            i = j + 1
            continue
        length = ((b[3] & 3) << 11) | (b[4] << 3) | (b[5] >> 5)
        sri = (b[2] >> 2) & 0xF
        if length < 7 or sri >= len(AAC_RATES):
            i = j + 1
            continue
        if len(buf) - j < length:
            return frames, buf[j:]
        head = 7 if b[1] & 1 else 9
        profile, ch = (b[2] >> 6) & 3, ((b[2] & 1) << 2) | (b[3] >> 6)
        asc = bytes([((profile + 1) << 3) | (sri >> 1), ((sri & 1) << 7) | (ch << 3)])
        frames.append((buf[j + head:j + length], asc, AAC_RATES[sri]))
        i = j + length


class UsbMic(threading.Thread):
    """Nimmt das USB-Mikrofon auf und gibt jeden AAC-Rahmen mit seiner Ankunftszeit an die Sitzung. Fehlt die Tonkarte oder bricht die
    Aufnahme ab (Empfänger abgezogen), wird alle paar Sekunden neu versucht; das Bild läuft unabhängig davon weiter."""

    def __init__(self, session, asound="/proc/asound", spawn=subprocess.Popen, sleep=time.sleep):
        super().__init__(daemon=True)
        self.s, self.asound, self.spawn, self.sleep = session, asound, spawn, sleep
        self.said = None

    def note(self, text):
        if text != self.said:
            self.said = text
            say(text)

    def run(self):
        while not self.s.closed:
            dev = usb_capture_card(self.asound)
            if dev is None:
                self.note("info: Kein USB-Mikrofon gefunden (Empfänger anstecken), der Ton fehlt solange")
                self.sleep(2)
                continue
            try:
                proc = self.spawn(usb_audio_argv(dev), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            except (OSError, ValueError) as e:
                self.note("info: Aufnahme des USB-Mikrofons startet nicht: %s" % e)
                self.sleep(3)
                continue
            self.note("info: Ton vom USB-Mikrofon (%s)" % dev)
            buf = b""
            try:
                while not self.s.closed:
                    chunk = proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(4096)
                    if not chunk:
                        break
                    t = self.s.clock()
                    frames, buf = adts_split(buf + chunk)
                    for n, (raw, asc, rate) in enumerate(frames):
                        self.s.on_mic_frame(raw, asc, rate, t - (len(frames) - 1 - n) * 1024.0 / rate)
            except (OSError, ValueError):
                pass
            finally:
                try:
                    proc.kill()
                    proc.wait(timeout=2)
                except Exception:
                    pass
            if not self.s.closed:
                self.note("info: Ton vom USB-Mikrofon unterbrochen, neuer Versuch")
                self.sleep(3)


# ---------------------------------------------------------------- USB (usbfs)
class _Ctrl(ctypes.Structure):
    _fields_ = [("rt", ctypes.c_uint8), ("req", ctypes.c_uint8), ("val", ctypes.c_uint16), ("idx", ctypes.c_uint16),
                ("len", ctypes.c_uint16), ("timeout", ctypes.c_uint32), ("data", ctypes.c_void_p)]


class _Bulk(ctypes.Structure):
    _fields_ = [("ep", ctypes.c_uint), ("len", ctypes.c_uint), ("timeout", ctypes.c_uint), ("data", ctypes.c_void_p)]


def _ioc(d, nr, size):
    return (d << 30) | (size << 16) | (ord("U") << 8) | nr


IOCTL_CONTROL = _ioc(3, 0, ctypes.sizeof(_Ctrl))
IOCTL_BULK = _ioc(3, 2, ctypes.sizeof(_Bulk))
IOCTL_CLAIM = _ioc(2, 15, 4)


class UsbError(Exception):
    pass


def list_usb():
    out = []
    for d in sorted(glob.glob("/sys/bus/usb/devices/[0-9]*")):
        if ":" in os.path.basename(d):
            continue
        try:
            out.append((open(d + "/idVendor").read().strip(), open(d + "/idProduct").read().strip(),
                        int(open(d + "/busnum").read()), int(open(d + "/devnum").read())))
        except (OSError, ValueError):
            pass
    return out


def control(fd, rt, req, val, idx, data):
    buf = ctypes.create_string_buffer(bytes(data), max(len(data), 1))
    c = _Ctrl(rt, req, val, idx, len(data), 2000, ctypes.cast(buf, ctypes.c_void_p).value)
    try:
        n = fcntl.ioctl(fd, IOCTL_CONTROL, c)
    except OSError as e:
        raise UsbError("Steuerabfrage: %s" % e)
    return bytes(buf.raw[:max(n, 0)])


def switch_to_accessory(bus, dev):
    """AOA-Handshake: Hersteller/Modell/Version müssen zu res/xml/accessory_filter.xml der App passen."""
    fd = os.open("/dev/bus/usb/%03d/%03d" % (bus, dev), os.O_RDWR)
    try:
        d = control(fd, 0xC0, 51, 0, 0, bytearray(2))
        if len(d) != 2 or struct.unpack("<H", d)[0] < 1:
            raise UsbError("Gerät kennt AOA nicht")
        for i, s in enumerate(["IRL4YOU", "Cam", "IRL4YOU Cam", "1", "", "0001"]):
            control(fd, 0x40, 52, 0, i, s.encode() + b"\0")
        control(fd, 0x40, 53, 0, 0, b"")
    finally:
        os.close(fd)


def bulk_endpoints(fd):
    """(Schnittstelle, EP-IN, EP-OUT) aus den Rohbeschreibungen des Geräts."""
    os.lseek(fd, 0, os.SEEK_SET)
    raw = os.read(fd, 4096)
    i, iface, ep_in, ep_out = 0, None, None, None
    while i + 2 <= len(raw) and raw[i] >= 2:
        ln, typ = raw[i], raw[i + 1]
        if typ == 4 and iface is None:
            iface = raw[i + 2]
        if typ == 5 and iface is not None and (raw[i + 3] & 3) == 2:
            if raw[i + 2] & 0x80:
                ep_in = ep_in or raw[i + 2]
            else:
                ep_out = ep_out or raw[i + 2]
        i += ln
    if iface is None or ep_in is None or ep_out is None:
        raise UsbError("keine Bulk-Endpunkte")
    return iface, ep_in, ep_out


class Accessory:
    def __init__(self, bus, dev):
        self.fd = os.open("/dev/bus/usb/%03d/%03d" % (bus, dev), os.O_RDWR)
        self.iface, self.ep_in, self.ep_out = bulk_endpoints(self.fd)
        try:
            fcntl.ioctl(self.fd, IOCTL_CLAIM, struct.pack("I", self.iface))
        except OSError as e:
            raise UsbError("Schnittstelle belegt: %s" % e)
        self.rbuf = ctypes.create_string_buffer(16384)
        self.lock = threading.Lock()
        self.pending = bytearray()

    def _read_chunk(self):
        b = _Bulk(self.ep_in, len(self.rbuf), 0, ctypes.cast(self.rbuf, ctypes.c_void_p).value)   # 0 = ohne Zeitlimit (sonst gehen Teile verloren)
        try:
            n = fcntl.ioctl(self.fd, IOCTL_BULK, b)
        except OSError as e:
            raise UsbError("Lesen: %s" % e)
        return self.rbuf.raw[:n]

    def read(self, n):
        while len(self.pending) < n:
            self.pending += self._read_chunk()
        out = bytes(self.pending[:n])
        del self.pending[:n]
        return out

    def message(self):
        head = self.read(5)
        length = struct.unpack(">I", head[1:])[0]
        if length > MAX_MESSAGE:
            raise UsbError("Nachricht zu groß")
        return head[0], self.read(length)

    def send(self, kind, payload=b""):
        data = bytes([kind]) + struct.pack(">I", len(payload)) + payload
        buf = ctypes.create_string_buffer(data, len(data))
        b = _Bulk(self.ep_out, len(data), 2000, ctypes.cast(buf, ctypes.c_void_p).value)
        with self.lock:
            try:
                fcntl.ioctl(self.fd, IOCTL_BULK, b)
            except OSError as e:
                raise UsbError("Schreiben: %s" % e)

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


def find_accessory():
    for vid, pid, bus, dev in list_usb():
        if (vid, pid) in ACCESSORY_IDS:
            return bus, dev
    return None


def connect():
    """Gibt ein offenes Accessory zurück; schaltet ein angeschlossenes Android-Handy bei Bedarf um."""
    found = find_accessory()
    if found is None:
        for vid, pid, bus, dev in list_usb():
            if vid in VENDORS and (vid, pid) not in ACCESSORY_IDS and not _is_hub_like(bus, dev):
                try:
                    switch_to_accessory(bus, dev)
                except (OSError, UsbError):
                    continue
                for _ in range(40):                  # Handy meldet sich neu
                    time.sleep(0.25)
                    found = find_accessory()
                    if found:
                        break
                break
    if found is None:
        raise UsbError("kein Android-Handy angeschlossen")
    return Accessory(*found)


def _is_hub_like(bus, dev):
    try:
        fd = os.open("/dev/bus/usb/%03d/%03d" % (bus, dev), os.O_RDONLY)
    except OSError:
        return True
    try:
        raw = os.read(fd, 18)
        return len(raw) >= 5 and raw[4] == 9        # Geräteklasse Hub
    finally:
        os.close(fd)


# ---------------------------------------------------------------- Annex B -> AVCC/HVCC
def split_annexb(b):
    idx = [m.start() for m in re.finditer(b"\x00\x00\x01", b)]
    nals = []
    for k, s in enumerate(idx):
        end = idx[k + 1] if k + 1 < len(idx) else len(b)
        nal = b[s + 3:end].rstrip(b"\x00")
        if nal:
            nals.append(nal)
    return nals


def to_length_prefixed(b):
    return b"".join(struct.pack(">I", len(n)) + n for n in split_annexb(b))


def unescape(b):
    return re.sub(b"\x00\x00\x03", b"\x00\x00", b)


def avcc_record(csd):
    sps = next((n for n in split_annexb(csd) if n[0] & 0x1F == 7), None)
    pps = next((n for n in split_annexb(csd) if n[0] & 0x1F == 8), None)
    if not sps or not pps:
        raise ValueError("SPS/PPS fehlen")
    return bytes([1, sps[1], sps[2], sps[3], 0xFF, 0xE1]) + struct.pack(">H", len(sps)) + sps + b"\x01" + struct.pack(">H", len(pps)) + pps


def hvcc_record(csd):
    nals = split_annexb(csd)
    by = {}
    for n in nals:
        by.setdefault((n[0] >> 1) & 0x3F, n)
    if not all(t in by for t in (32, 33, 34)):
        raise ValueError("VPS/SPS/PPS fehlen")
    ptl = unescape(by[33][:24])[3:15]            # general_profile_space..general_level_idc
    out = bytes([1]) + ptl[0:1] + ptl[1:5] + ptl[5:11] + ptl[11:12]
    out += b"\xF0\x00" + b"\xFC" + b"\xFD" + b"\xF8" + b"\xF8" + b"\x00\x00" + bytes([0x0F, 3])
    for t in (32, 33, 34):
        out += bytes([0x80 | t]) + b"\x00\x01" + struct.pack(">H", len(by[t])) + by[t]
    return out


# ---------------------------------------------------------------- Sitzung
class Session:
    def __init__(self, acc, args, clock=time.monotonic):
        self.acc, self.args, self.clock = acc, args, clock
        self.vshift = 0                  # Millisekunden, um die die Zeitstempel des Bilds nachgezogen wurden (siehe track_video)
        self.v_arr0 = None
        self.v_ref = 0.0
        self.cfg = None
        self.record = None
        self.rtmp = None
        self.base = None
        self.last = {"v": 0, "a": 0}
        self.have_key = False
        self.acsd = None
        self.audio_sent = False
        self.st = {"t": time.monotonic(), "v": 0, "a": 0, "bytes": 0, "key": 0, "maxgap": 0.0, "lastv": 0.0, "skew": None, "vpts": 0}
        self.win = None
        self.closed = False
        self.reconf = False              # Bildgröße hat gewechselt: vor dem nächsten Schlüsselbild kommt ein neuer Kopf in den laufenden Strom
        self.hold_until = 0.0            # bis dahin werden Bilder verworfen (siehe HOLD_S)
        self.hold_asked = False
        self.t_cfg = 0.0                 # Zeit der letzten CONFIG
        self.last_v_sent = 0.0           # Zeit des letzten Bilds, das an die Box ging
        self.stall_asked = 0.0
        self.phone_at, self.phone_chg = -1e9, None
        self.tx_lock = threading.Lock()  # Bild (Hauptschleife) und Mikrofon-Ton (eigener Thread) schreiben in dieselbe RTMP-Verbindung
        self.a_next = None               # Zeitstempel des nächsten Tonrahmens vom USB-Mikrofon (ms, Zeitachse des Bilds)

    def ts(self, pts, kind):
        if self.base is None:
            self.base = pts
        t = max(0, (pts - self.base) // 1000)
        if kind == "v":
            t += self.vshift
        t = max(t, self.last[kind])
        self.last[kind] = t
        return t

    def tx(self, name, *a):
        """Sendet über die aktuelle RTMP-Verbindung; nie gleichzeitig aus zwei Threads."""
        with self.tx_lock:
            r = self.rtmp
            if r is not None:
                getattr(r, name)(*a)

    def has_audio(self):
        return self.args.audio == "usb" or self.cfg["audio"]["ch"] > 0

    def on_mic_frame(self, raw, asc, rate, t):
        """Ein AAC-Rahmen vom USB-Mikrofon (Aufnahmezeit t auf der Uhr dieser Sitzung). Der Zeitstempel folgt der Zeitachse des Bilds: Zeit des letzten
        Bilds plus Zeit seitdem plus der eingestellte Ton-Versatz; die Rahmen laufen sonst lückenlos (1024 Abtastwerte je Rahmen)."""
        if self.args.dry or self.rtmp is None or not self.last_v_sent or self.hold_until:
            return
        ref = self.last["v"] + (t - self.last_v_sent) * 1000.0 + getattr(self.args, "audio_offset", 0)
        if self.a_next is None or abs(self.a_next - ref) > MIC_RESYNC_MS:
            self.a_next = ref
        ts = max(int(self.a_next), self.last["a"], 0)
        self.a_next += 1024.0 * 1000.0 / rate
        self.last["a"] = ts
        if not self.audio_sent:
            self.audio_sent = True
            self.tx("send_audio", ts, self.m.flv_audio(0, asc))
        self.tx("send_audio", ts, self.m.flv_audio(1, raw))

    def open_rtmp(self):
        import mobcam_rtmp as m
        self.m = m
        self.rtmp = m.Rtmp("127.0.0.1", self.args.rtmp_port, self.args.rtmp_app, self.args.key)
        codec = m.CODEC_HEVC if self.cfg["codec"] == "hevc" else m.CODEC_H264
        self.codec = codec
        self.tx("send_data", 0, m.metadata(self.cfg["w"], self.cfg["h"], codec, self.has_audio()))
        self.tx("send_video", 0, m.flv_video(codec, True, 0, self.record))

    def reconf_header(self, t):
        """Neue Bildgröße im selben RTMP-Strom: Metadaten und neuer Kopf (Parametersätze) kurz vor dem ersten Schlüsselbild der neuen Größe."""
        self.reconf = False
        self.tx("send_data", t, self.m.metadata(self.cfg["w"], self.cfg["h"], self.codec, self.has_audio()))
        self.tx("send_video", t, self.m.flv_video(self.codec, True, 0, self.record))

    def restart_stream(self, hold=False):
        """Neuer RTMP-Strom (Größe oder Codec haben gewechselt): alte Verbindung schließen, Zeit und Parametersätze zurücksetzen.
        Mit hold wartet der Helfer danach HOLD_S, bis die Live-Kette den Kamerazweig abgeschaltet hat."""
        if hold and self.rtmp is not None:
            self.hold_until = self.clock() + HOLD_S
            self.hold_asked = False
        try:
            if self.rtmp:
                self.rtmp.close()
        except Exception:
            pass
        self.rtmp = None
        self.record = None
        self.have_key = False
        self.acsd = None
        self.audio_sent = False
        self.base = None
        self.last = {"v": 0, "a": 0}
        self.a_next = None
        self.vshift = 0
        self.v_arr0 = None
        self.v_ref = 0.0
        self.reconf = False

    def track_video(self, pts):
        """Kommt ein Bild viel später an, als sein Zeitstempel erwarten lässt (die App hat zum Beispiel beim Umstellen pausiert und die
        Pause nicht in die Zeitstempel gerechnet), sieht die Live-Kette die Kamera dauerhaft nachhängen. Dann ziehen wir die Zeit des Bilds nach."""
        if self.base is None:
            self.base = pts
        now = self.clock()
        raw = (pts - self.base) / 1000.0
        if self.v_arr0 is None:
            self.v_arr0 = now - raw / 1000.0
        d = (now - self.v_arr0) * 1000.0 - raw          # Ankunftszeit minus Zeitstempel, in Millisekunden
        if d < self.v_ref:
            self.v_ref = d
        elif d - self.v_ref > VIDEO_JUMP_MS:
            jump = int(d - self.v_ref)
            self.vshift += jump
            self.v_ref = d
            say("info: Bild kam %d ms später als sein Zeitstempel, die Zeit wird nachgezogen" % jump)

    def run(self):
        self.acc.send(CMD_CONFIG)
        self.acc.send(CMD_KEYFRAME)
        while True:
            kind, p = self.acc.message()
            self.handle(kind, p)

    def report(self, size, vpts=None, apts=None):
        st = self.st
        now = time.monotonic()
        if vpts is not None:
            if st["lastv"]:
                st["maxgap"] = max(st["maxgap"], now - st["lastv"])
            st["lastv"] = now
            st["vpts"] = vpts
        if apts is not None and st["vpts"]:
            st["skew"] = (apts - st["vpts"]) // 1000
        st["bytes"] += size
        if now - st["t"] >= 2:
            dt = now - st["t"]
            say("info: Bild %.1f/s (Schlüsselbilder %d), Ton %.1f/s, %.1f Mbit/s, größte Lücke %d ms, Ton−Bild-Zeit %s ms" % (
                st["v"] / dt, st["key"], st["a"] / dt, st["bytes"] * 8 / dt / 1e6, st["maxgap"] * 1000,
                "?" if st["skew"] is None else st["skew"]))
            st.update(t=now, v=0, a=0, bytes=0, key=0, maxgap=0.0)

    def check_stall(self):
        """Die App sendet (Ton/Messwerte kommen), aber es geht kein Bild an die Box (Konfiguration oder Parametersätze verpasst, Schlüsselbild fehlt):
        Konfiguration und Schlüsselbild neu anfordern, höchstens alle 2 s."""
        if self.cfg is None or self.args.dry:
            return
        now = self.clock()
        if now < self.hold_until:
            return
        last = max(self.last_v_sent, self.t_cfg)
        if now - last < STALL_S or now - self.stall_asked < 2.0:
            return
        self.stall_asked = now
        say("info: Seit %.0f s geht kein Bild an die Box, Konfiguration und Schlüsselbild werden neu angefordert" % (now - last))
        try:
            self.acc.send(CMD_CONFIG)
            self.acc.send(CMD_KEYFRAME)
        except (UsbError, OSError):
            pass

    def phone_line(self, d):
        """Handydaten aus dem STATS-Rahmen (Akku, Laden, Strom, Temperatur) als eigene Zeile für den Dienst; ältere Apps schicken sie nicht"""
        out = phone_values(d)
        if not out:
            return
        now = self.clock()
        if out.get("chg") == self.phone_chg and now - self.phone_at < PHONE_EVERY_S:
            return
        self.phone_at, self.phone_chg = now, out.get("chg")
        say("Handy: " + json.dumps(out, separators=(",", ":")))

    def handle(self, kind, p):
        if kind in (MSG_AUDIO, MSG_STATS, MSG_VIDEO):
            self.check_stall()
        if kind == MSG_CONFIG:
            self.t_cfg = self.clock()
            neu = json.loads(p.decode())
            if self.rtmp is not None and self.cfg and (neu.get("w"), neu.get("h"), neu.get("codec")) != (self.cfg.get("w"), self.cfg.get("h"), self.cfg.get("codec")):
                nahtlos = bool(neu.get("seamless")) or getattr(self.args, "reconfig", "restart") == "inband"
                if nahtlos and neu.get("codec") == self.cfg.get("codec"):
                    # nahtloser Wechsel der App (Pause unter ca. 50 ms) oder Modus inband: den Strom offen lassen, nur neuer Kopf
                    say("info: Bildgröße hat sich geändert (nahtlos), neuer Kopf im selben Strom")
                    self.reconf = True
                    self.have_key = False
                else:
                    say("info: Bildgröße oder Codec haben sich geändert, der Strom wird neu aufgebaut")
                    self.restart_stream(hold=True)
            self.cfg = neu
            say("Bild: %dx%d %s %d fps, Ton: %s" % (self.cfg["w"], self.cfg["h"], "HEVC" if self.cfg["codec"] == "hevc" else "H.264",
                                                   self.cfg["fps"], "%d Hz %d Kanäle" % (self.cfg["audio"]["rate"], self.cfg["audio"]["ch"])
                                                   if self.cfg["audio"]["ch"] else "aus"))
            if self.cfg.get("ae"):
                say("info: Bildraten-Bereich der Kamera (AE) %s" % self.cfg["ae"])
            if self.cfg["bitrate"] / 1e6 > MAX_MBIT:
                self.acc.send(CMD_BITRATE, struct.pack(">I", int(MAX_MBIT * 1e6)))
                say("info: Bitrate des Handys von %.0f auf %.0f Mbit/s begrenzt" % (self.cfg["bitrate"] / 1e6, MAX_MBIT))
        elif kind == MSG_ROTATE:
            if self.rtmp is not None:
                say("info: Die App dreht gleich, der Strom wird geschlossen")
                self.restart_stream(hold=True)
        elif kind == MSG_STATS:
            try:
                d = json.loads(p.decode())
            except (ValueError, UnicodeDecodeError):
                return
            say("info: App: Kamera %s/s, gesendet %s/s, verworfen %s, Rückstau %s, %s Mbit/s von %s, AE %s" % (
                d.get("cam", "?"), d.get("out", "?"), d.get("dropped", "?"), d.get("backlog", "?"),
                d.get("mbit", "?"), d.get("target", "?"), d.get("ae", "?")))
            self.phone_line(d)
        elif kind == MSG_VIDEO_CSD and self.cfg:
            try:
                self.record = hvcc_record(p) if self.cfg["codec"] == "hevc" else avcc_record(p)
            except ValueError as e:
                say("Parametersätze unvollständig: %s" % e)
                return
            self.have_key = False
            say("info: Parametersätze erhalten (%d Byte)" % len(p))
        elif kind == MSG_AUDIO_CSD:
            self.acsd = p
            self.audio_sent = False
        elif kind == MSG_VIDEO and self.record and len(p) >= 9:
            if self.hold_until:
                if self.clock() < self.hold_until:
                    return                                   # Zweig der Box ist noch nicht sicher abgeschaltet
                self.hold_until = 0.0
                if not self.hold_asked:
                    self.hold_asked = True
                    self.acc.send(CMD_KEYFRAME)              # gleich ein Schlüsselbild für den neuen Strom
            key = bool(p[0] & 1)
            pts = struct.unpack(">Q", p[1:9])[0]
            if not self.have_key and not key:
                return
            self.have_key = True
            self.track_video(pts)
            st = self.st
            st["v"] += 1
            st["key"] += int(key)
            if not self.args.dry:
                if self.rtmp is None:
                    self.open_rtmp()
                t = self.ts(pts, "v")
                if self.reconf:
                    self.reconf_header(t)
                self.tx("send_video", t, self.m.flv_video(self.codec, key, 1, to_length_prefixed(p[9:])))
                self.last_v_sent = self.clock()
            self.report(len(p), vpts=pts)
        elif kind == MSG_AUDIO and len(p) > 8:
            pts = struct.unpack(">Q", p[:8])[0]
            self.st["a"] += 1
            if not self.args.dry and self.rtmp is not None and self.acsd and self.args.audio == "mobcam":
                if not self.audio_sent:
                    self.tx("send_audio", self.last["a"], self.m.flv_audio(0, self.acsd))
                    self.audio_sent = True
                self.tx("send_audio", self.ts(pts, "a"), self.m.flv_audio(1, p[8:]))
            self.report(len(p), apts=pts)

    def close(self):
        self.closed = True
        if self.rtmp:
            self.rtmp.close()
        self.acc.close()


def _wait_note(s):
    """Meldet alle 3 Sekunden, dass die App noch nichts sendet (die Box zeigt das an), und fordert die Konfiguration erneut an."""
    time.sleep(1)
    while s.cfg is None and not s.closed:
        say("Warte auf die App (IRL4YOU Cam am Handy öffnen)")
        try:
            s.acc.send(CMD_CONFIG)
        except (UsbError, OSError):
            return
        time.sleep(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--audio", default="mobcam", choices=("mobcam", "none", "usb"))
    ap.add_argument("--audio-offset", type=int, default=0, help="nur mit --audio usb: Ton gegenüber dem Bild verschieben, in ms (positiv = später)")
    ap.add_argument("--reconfig", default="restart", choices=("inband", "restart"),
                    help="Bildgröße wechselt: restart (Standard) = Strom schließen, ca. 3,5 s warten und neu öffnen; inband = neuer Kopf im selben Strom "
                         "(stürzt die Live-Kette ab, wenn zwischen den Bildern mehr als ca. 80 ms liegen)")
    ap.add_argument("--key", default="hdmi")
    ap.add_argument("--rtmp-port", type=int, default=1935)
    ap.add_argument("--rtmp-app", default="publish")
    ap.add_argument("--seconds", type=float, default=0, help="nach so vielen Sekunden beenden (Test)")
    args = ap.parse_args()
    args.audio_offset = max(-1000, min(1000, args.audio_offset))
    if not re.match(r"^[a-z0-9][a-z0-9_-]{0,31}$", args.key) or not re.match(r"^[a-z0-9_]{1,20}$", args.rtmp_app):
        say("Ungültige Einstellung")
        sys.exit(2)
    signal.signal(signal.SIGTERM, lambda *_: os._exit(0))
    signal.signal(signal.SIGINT, lambda *_: os._exit(0))
    if args.seconds:
        threading.Timer(args.seconds, lambda: os._exit(0)).start()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    announced = None
    while True:
        try:
            acc = connect()
        except (UsbError, OSError) as e:
            if str(e) != announced:
                say("Warte auf das Handy (%s)" % e)
                announced = str(e)
            time.sleep(1)
            continue
        announced = None
        say("Handy verbunden (USB-Zubehör)")
        s = Session(acc, args)
        threading.Thread(target=_wait_note, args=(s,), daemon=True).start()
        if args.audio == "usb" and not args.dry:
            UsbMic(s).start()
        try:
            s.run()
        except (UsbError, OSError, ValueError, KeyError, struct.error, json.JSONDecodeError) as e:
            say("Verbindung zum Handy beendet: %s" % e)
        finally:
            s.close()
        time.sleep(1)


if __name__ == "__main__":
    main()
