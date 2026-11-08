"""Mobcam: iPhone mit Moblin per USB-Kabel als Kamera (Quelle "mobcam"). Bild und Ton gehen unverändert (H.264 oder H.265) als RTMP an die Box."""
import asyncio
import os
import plistlib
import socket
import struct
import sys
import tempfile
import threading
import types
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from test_irl4you import irl  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "irl4you"))
import mobcam_rtmp as mr  # noqa: E402


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class TestMobcamEinstellungen(unittest.TestCase):
    def setUp(self):
        self.hd = irl("hdmi_daemon")

    def test_quelle_und_ton_sind_erlaubt(self):
        self.assertIn("mobcam", self.hd.SOURCE_CHOICES)
        self.assertEqual(self.hd.clean_settings({"source": "mobcam"})["source"], "mobcam")
        self.assertEqual(self.hd.clean_settings({"source": "mobcam", "audio": "mobcam"})["audio"], "mobcam")

    def test_befehl_fuer_das_hilfsprogramm(self):
        cfg = dict(self.hd.DEFAULTS, source="mobcam", audio="mobcam", key="hdmi")
        a = self.hd.mobcam_feeder_argv(cfg, 1935, "publish", helper="/opt/pipbox/mobcam_rtmp.py")
        self.assertIn("/opt/pipbox/mobcam_rtmp.py", a)
        self.assertEqual(a[a.index("--key") + 1], "hdmi")
        self.assertEqual(a[a.index("--audio") + 1], "mobcam")
        self.assertNotIn("--bitrate", a)     # nichts wird kodiert: Bitrate, Bildrate und Codec kommen aus Moblin
        self.assertNotIn("--fps", a)
        self.assertEqual(self.hd.mobcam_feeder_argv(dict(cfg, audio="none"), 1935, "publish")[-1], "none")
        with self.assertRaises(ValueError):
            self.hd.mobcam_feeder_argv(cfg, 1935, "../x")

    def test_gespeicherte_bildrate_50_oder_60_der_ersten_fassung_geht_nicht_verloren(self):
        import json
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "hdmi.json"), "w") as f:
            json.dump(dict(self.hd.DEFAULTS, source="mobcam", audio="mobcam", enabled=True, fps=60, bitrate=20000), f)
        c = self.hd.Daemon(d, device="/gibt/es/nicht").cfg
        self.assertEqual((c["source"], c["audio"], c["enabled"], c["fps"]), ("mobcam", "mobcam", True, 30))

    def test_bildrate_bleibt_25_oder_30(self):
        for f in (50, 60):
            with self.assertRaises(ValueError):
                self.hd.clean_settings({"fps": f})


class TestMobcamErkennung(unittest.TestCase):
    def setUp(self):
        self.hd = irl("hdmi_daemon")
        self.d = tempfile.mkdtemp()

    def test_iphone_am_usb_wird_gefunden(self):
        usb = os.path.join(self.d, "usb")
        _write(os.path.join(usb, "9-1", "idVendor"), "05ac\n")
        _write(os.path.join(usb, "9-1", "idProduct"), "12a8\n")
        _write(os.path.join(usb, "9-1", "product"), "iPhone\n")
        _write(os.path.join(usb, "9-1:1.0", "idVendor"), "05ac\n")
        p = self.hd.find_apple_phone(usb)
        self.assertEqual((p["name"], p["id"]), ("iPhone", "05ac:12a8"))

    def test_kein_iphone(self):
        usb = os.path.join(self.d, "usb")
        _write(os.path.join(usb, "3-1.3", "idVendor"), "13d3\n")
        self.assertIsNone(self.hd.find_apple_phone(usb))
        self.assertIsNone(self.hd.find_apple_phone(os.path.join(self.d, "fehlt")))

    def test_usb_c_wird_fuer_apple_auf_host_geschaltet(self):
        tc = os.path.join(self.d, "typec")
        _write(os.path.join(tc, "port0", "data_role"), "host [device]\n")
        _write(os.path.join(tc, "port0-partner", "identity", "id_header"), "0xd54005ac\n")
        self.assertTrue(self.hd.typec_make_host(tc))
        with open(os.path.join(tc, "port0", "data_role")) as f:
            self.assertEqual(f.read(), "host")

    def test_usb_c_andere_geraete_und_schon_host_bleiben_unberuehrt(self):
        tc = os.path.join(self.d, "typec")
        _write(os.path.join(tc, "port0", "data_role"), "host [device]\n")
        _write(os.path.join(tc, "port0-partner", "identity", "id_header"), "0xd4001234\n")
        self.assertFalse(self.hd.typec_make_host(tc))
        _write(os.path.join(tc, "port0", "data_role"), "[host] device\n")
        _write(os.path.join(tc, "port0-partner", "identity", "id_header"), "0xd54005ac\n")
        self.assertFalse(self.hd.typec_make_host(tc))
        self.assertFalse(self.hd.typec_make_host(os.path.join(self.d, "fehlt")))


class TestMobcamDienst(unittest.TestCase):
    def setUp(self):
        self.hd = irl("hdmi_daemon")

    def _daemon(self, usb, gestartet):
        class P:
            returncode = None
            stderr = None

        async def spawn(argv):
            gestartet.append(argv)
            return P()
        return self.hd.Daemon(tempfile.mkdtemp(), device="/gibt/es/nicht", spawn=spawn, publishing=lambda k: True, sysusb=usb, typec=os.path.join(usb, "tc"))

    def test_ohne_iphone_wird_gewartet_mit_iphone_gestartet(self):
        usb = tempfile.mkdtemp()
        gestartet = []
        d = self._daemon(usb, gestartet)
        d.cfg = dict(d.cfg, source="mobcam", enabled=True, audio="mobcam")

        async def lauf():
            await d.tick()
            self.assertEqual(d.state, "waiting")
            self.assertIn("iPhone", d.message)
            self.assertEqual(gestartet, [])
            _write(os.path.join(usb, "9-1", "idVendor"), "05ac\n")
            _write(os.path.join(usb, "9-1", "product"), "iPhone\n")
            await d.tick()
        asyncio.run(lauf())
        self.assertEqual(len(gestartet), 1)
        self.assertIn("--key", gestartet[0])
        self.assertTrue(d.status()["usb"]["present"])

    def test_warten_auf_moblin_ist_kein_fehler(self):
        usb = tempfile.mkdtemp()
        _write(os.path.join(usb, "9-1", "idVendor"), "05ac\n")
        d = self._daemon(usb, [])
        d.cfg = dict(d.cfg, source="mobcam", enabled=True)
        d.tail.append(self.hd.MOBCAM_WAIT)
        d.started = d.clock() - 100
        asyncio.run(d._watch_stream())
        self.assertEqual(d.state, "starting")
        self.assertIn("Moblin", d.message)
        self.assertIsNone(d.missing_since)

    def test_quellenwechsel_koppelt_den_ton(self):
        d = self._daemon(tempfile.mkdtemp(), [])
        d.cfg = dict(d.cfg, source="hdmi", audio="hdmi")
        r = asyncio.run(d.handle({"cmd": "set", "settings": {"source": "mobcam"}}))
        self.assertEqual((r["settings"]["source"], r["settings"]["audio"]), ("mobcam", "mobcam"))
        r = asyncio.run(d.handle({"cmd": "set", "settings": {"source": "hdmi"}}))
        self.assertEqual(r["settings"]["audio"], "hdmi")


class TestMobcamProtokoll(unittest.TestCase):
    def test_amf_hin_und_zurueck(self):
        data = mr.amf_command("connect", 1, {"app": "publish", "flag": True, "w": 1920.0}, None)
        vals, i = [], 0
        while i < len(data):
            v, i = mr.amf_read(data, i)
            vals.append(v)
        self.assertEqual(vals, ["connect", 1.0, {"app": "publish", "flag": True, "w": 1920.0}, None])

    def test_flv_pakete(self):
        self.assertEqual(mr.flv_video(mr.CODEC_HEVC, True, 0, b"REC"), bytes([0x1C, 0, 0, 0, 0]) + b"REC")
        self.assertEqual(mr.flv_video(mr.CODEC_HEVC, False, 1, b"X"), bytes([0x2C, 1, 0, 0, 0]) + b"X")
        self.assertEqual(mr.flv_video(mr.CODEC_H264, True, 1, b"X")[0], 0x17)
        self.assertEqual(mr.flv_audio(0, b"\x11\x90"), bytes([0xAF, 0, 0x11, 0x90]))

    def test_konfigurationen(self):
        v = struct.pack(">BHHI", mr.CODEC_HEVC, 1920, 1080, 3) + b"abc"
        self.assertEqual(mr.parse_video_config(v), (mr.CODEC_HEVC, 1920, 1080, b"abc"))
        a = struct.pack(">BIBI", 0, 48000, 2, 2) + b"\x11\x90"
        self.assertEqual(mr.parse_audio_config(a), (0, 48000, 2, b"\x11\x90"))

    def test_rtmp_chunks_mit_langer_nachricht_und_erweitertem_zeitstempel(self):
        a, b = socket.socketpair()
        r = mr.Rtmp.__new__(mr.Rtmp)
        r.sock, r.lock, r.chunk_out = a, threading.Lock(), 4096
        payload = bytes(range(256)) * 40
        teile = []

        def lesen():
            while True:
                d = b.recv(65536)
                if not d:
                    break
                teile.append(d)
        t = threading.Thread(target=lesen, daemon=True)
        t.start()
        r._send(6, 0x1000000, 9, 1, payload)
        a.close()
        t.join(5)
        got = b"".join(teile)
        self.assertEqual(got[0], 6)
        self.assertEqual(got[1:4], b"\xff\xff\xff")
        self.assertEqual(int.from_bytes(got[4:7], "big"), len(payload))
        self.assertEqual(got[7], 9)
        self.assertEqual(got[8:12], struct.pack("<I", 1))
        self.assertEqual(got[12:16], struct.pack(">I", 0x1000000))
        self.assertEqual(got[16:16 + 4096], payload[:4096])
        self.assertEqual(got[16 + 4096], 0xC6)                 # Folge-Chunk gleicher Strom, mit erweitertem Zeitstempel
        self.assertEqual(got[16 + 4097:16 + 4101], struct.pack(">I", 0x1000000))
        self.assertEqual(len(got), 16 + len(payload) + 5 * ((len(payload) - 1) // 4096))

    def test_usbmux_verbindet_mit_dem_ersten_iphone(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "usbmuxd")
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(path)
        srv.listen(2)
        seen = {}

        def serve():
            for _ in range(2):
                c, _ = srv.accept()
                head = c.recv(16)
                body = plistlib.loads(c.recv(struct.unpack("<I", head[:4])[0] - 16))
                if body["MessageType"] == "ListDevices":
                    reply = {"DeviceList": [{"DeviceID": 7, "Properties": {"ConnectionType": "USB", "SerialNumber": "ABC"}}]}
                else:
                    seen.update(body)
                    reply = {"Number": 0}
                data = plistlib.dumps(reply, fmt=plistlib.FMT_XML)
                c.sendall(struct.pack("<IIII", 16 + len(data), 1, 8, 1) + data)
                if body["MessageType"] == "Connect":
                    c.sendall(b"HALLO")
                c.close()
        t = threading.Thread(target=serve, daemon=True)
        t.start()
        sock, serial = mr.connect_phone(7790, path)
        self.assertEqual(serial, "ABC")
        self.assertEqual(seen["DeviceID"], 7)
        self.assertEqual(seen["PortNumber"], socket.htons(7790))
        self.assertEqual(sock.recv(5), b"HALLO")
        t.join(2)
        sock.close()
        srv.close()
        with self.assertRaises(mr.MuxError):
            mr.connect_phone(7790, os.path.join(d, "gibt-es-nicht"))


def _senden(sock, nachrichten):
    """Schickt die Nachrichten aus einem eigenen Thread (große Mengen würden sonst vor dem Lesen den Socket verstopfen) und schließt dann die Schreibseite."""
    def lauf():
        try:
            for kind, payload in nachrichten:
                sock.sendall(bytes([kind]) + struct.pack(">I", len(payload)) + payload)
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass
    threading.Thread(target=lauf, daemon=True).start()


class FakeRtmp:
    def __init__(self, *a):
        self.sent = []

    def send_data(self, ts, payload):
        self.sent.append(("data", ts, payload))

    def send_video(self, ts, payload):
        self.sent.append(("video", ts, payload))

    def send_audio(self, ts, payload):
        self.sent.append(("audio", ts, payload))

    def close(self):
        pass


class TestMobcamSitzung(unittest.TestCase):
    def _lauf(self, nachrichten, audio="mobcam", window_us=0, fehler=mr.MuxError):
        a, b = socket.socketpair()
        _senden(b, nachrichten)
        args = types.SimpleNamespace(key="hdmi", rtmp_port=1935, rtmp_app="publish", audio=audio, window_us=window_us)
        s = mr.Session(a, args)
        fake = FakeRtmp()
        s.open = lambda: (setattr(s, "rtmp", fake), fake.send_video(0, mr.flv_video(s.vcfg[0], True, 0, s.vcfg[3])))
        with self.assertRaises(fehler):
            s.run()
        a.close()
        b.close()
        return fake.sent

    def test_bild_und_ton_werden_unveraendert_weitergereicht(self):
        vcfg = struct.pack(">BHHI", mr.CODEC_HEVC, 1920, 1080, 4) + b"hvcC"
        acfg = struct.pack(">BIBI", 0, 48000, 2, 2) + b"\x11\x90"
        vf = lambda pts, key, data: struct.pack(">QB", pts, 1 if key else 0) + data
        sent = self._lauf([
            (mr.MSG_VIDEO_CONFIG, vcfg), (mr.MSG_AUDIO_CONFIG, acfg),
            (mr.MSG_VIDEO_FRAME, vf(5_000_000, False, b"P0")),                      # vor dem ersten Schlüsselbild: verworfen
            (mr.MSG_VIDEO_FRAME, vf(5_010_000, True, b"K1")),
            (mr.MSG_AUDIO_FRAME, struct.pack(">Q", 5_012_000) + b"AAC1"),
            (mr.MSG_VIDEO_FRAME, vf(5_026_667, False, b"P2")),
        ])
        self.assertEqual(sent[0], ("video", 0, bytes([0x1C, 0, 0, 0, 0]) + b"hvcC"))      # Kopf (Konfiguration)
        self.assertEqual(sent[1], ("video", 0, bytes([0x1C, 1, 0, 0, 0]) + b"K1"))         # Schlüsselbild, Zeit 0 ms
        self.assertEqual(sent[2], ("audio", 0, bytes([0xAF, 0, 0x11, 0x90])))              # Tonkopf
        self.assertEqual(sent[3], ("audio", 2, bytes([0xAF, 1]) + b"AAC1"))
        self.assertEqual(sent[4], ("video", 16, bytes([0x2C, 1, 0, 0, 0]) + b"P2"))
        self.assertEqual(len(sent), 5)

    def test_ohne_ton_wird_kein_ton_gesendet(self):
        vcfg = struct.pack(">BHHI", mr.CODEC_H264, 1280, 720, 2) + b"av"
        sent = self._lauf([(mr.MSG_VIDEO_CONFIG, vcfg), (mr.MSG_AUDIO_CONFIG, struct.pack(">BIBI", 0, 48000, 2, 2) + b"\x11\x90"),
                           (mr.MSG_VIDEO_FRAME, struct.pack(">QB", 1000, 1) + b"K"),
                           (mr.MSG_AUDIO_FRAME, struct.pack(">Q", 1000) + b"AAC")], audio="none")
        self.assertEqual([k for k, *_ in sent], ["video", "video"])
        self.assertEqual(sent[0][2][0], 0x17)                                              # H.264: Kennung 7


class TestMobcamBitratenSperre(unittest.TestCase):
    """Ein Strom über 12 Mbit/s wird abgelehnt, bevor er die Live-Kette erreicht (sie schafft je Strom nur etwa 13 Mbit/s)."""

    def _strom(self, mbit, sekunden=3, fps=30):
        vcfg = struct.pack(">BHHI", mr.CODEC_HEVC, 1920, 1080, 4) + b"hvcC"
        gross = int(mbit * 1e6 / 8 / fps)
        msgs = [(mr.MSG_VIDEO_CONFIG, vcfg)]
        for i in range(sekunden * fps):
            msgs.append((mr.MSG_VIDEO_FRAME, struct.pack(">QB", 1000000 + i * 1000000 // fps, 1 if i == 0 else 0) + bytes(gross)))
        return msgs

    def _lauf(self, msgs):
        return TestMobcamSitzung._lauf(self, msgs, window_us=2000000, fehler=(mr.TooHigh, mr.MuxError))

    def test_zu_hohe_bitrate_wird_abgelehnt_und_nichts_gesendet(self):
        a, b = socket.socketpair()
        _senden(b, self._strom(30))
        s = mr.Session(a, types.SimpleNamespace(key="hdmi", rtmp_port=1935, rtmp_app="publish", audio="mobcam", window_us=2000000))
        s.open = lambda: self.fail("die Kette darf den Strom nicht sehen")
        with self.assertRaises(mr.TooHigh) as cm:
            s.run()
        self.assertGreater(cm.exception.args[0], mr.MAX_MBIT)
        a.close()
        b.close()

    def test_bitrate_im_rahmen_geht_durch_und_alles_wird_in_reihenfolge_nachgereicht(self):
        sent = self._lauf(self._strom(10))
        self.assertEqual(sent[0][0], "video")                      # Kopf
        self.assertEqual(sent[0][2][1], 0)
        self.assertGreater(len([x for x in sent if x[0] == "video"]), 60)

    def test_meldung_ist_im_dienst_und_im_hilfsprogramm_gleich(self):
        hd = irl("hdmi_daemon")
        self.assertEqual(hd.MOBCAM_TOO_HIGH, mr.TOO_HIGH)

    def test_dienst_zeigt_die_meldung_ohne_neustart(self):
        hd = irl("hdmi_daemon")
        usb = tempfile.mkdtemp()
        _write(os.path.join(usb, "9-1", "idVendor"), "05ac\n")
        d = hd.Daemon(tempfile.mkdtemp(), device="/gibt/es/nicht", spawn=None, publishing=lambda k: True, sysusb=usb, typec=os.path.join(usb, "tc"))
        d.cfg = dict(d.cfg, source="mobcam", enabled=True)
        d.tail.append(hd.MOBCAM_TOO_HIGH)
        d.started = d.clock() - 100
        asyncio.run(d._watch_stream())
        self.assertEqual((d.state, d.message), ("starting", hd.MOBCAM_TOO_HIGH))
        self.assertIsNone(d.missing_since)


class TestMobcamHinweise(unittest.TestCase):
    def _text(self, *teile):
        with open(os.path.join(ROOT, *teile), encoding="utf-8") as f:
            return f.read()

    def test_update_braucht_nur_usbmuxd_und_raeumt_die_erste_fassung_auf(self):
        h = self._text("release", "hooks", "install")
        self.assertIn("usbmuxd", h)
        self.assertIn("|| echo", h)
        self.assertIn("rm -f /usr/local/bin/mobcam-virtualcam", h)

    def test_hinweise_zu_mobcam_stehen_da(self):
        n = self._text("NOTICE.md")
        self.assertIn("Mobcam (Protokoll)", n)
        self.assertIn("kein Mobcam-Programmcode", n.replace("Programmcode aus Mobcam ist nicht enthalten", "kein Mobcam-Programmcode"))
        self.assertIn("eerimoq/mobcam", self._text("README.md"))


if __name__ == "__main__":
    unittest.main()
