"""Mobcam: iPhone mit Moblin per USB-Kabel als Kamera (Quelle "mobcam"), 25/30/50/60 Bilder pro Sekunde, Einrichtung und Lizenzhinweis."""
import asyncio
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from test_irl4you import irl  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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

    def test_bildraten_nur_mit_iphone_50_und_60(self):
        for f in (25, 30, 50, 60):
            self.assertEqual(self.hd.clean_settings({"source": "mobcam", "fps": f})["fps"], f)
        for f in (50, 60):
            with self.assertRaises(ValueError):
                self.hd.clean_settings({"source": "hdmi", "fps": f})
        with self.assertRaises(ValueError):
            self.hd.clean_settings({"source": "mobcam", "fps": 45})

    def test_quellenwechsel_setzt_unpassende_bildrate_zurueck(self):
        cur = dict(self.hd.DEFAULTS, source="mobcam", fps=60)
        self.assertEqual(self.hd.clean_settings({"source": "hdmi"}, cur)["fps"], 30)
        cur = dict(self.hd.DEFAULTS, source="hdmi", fps=25)
        self.assertEqual(self.hd.clean_settings({"source": "mobcam"}, cur)["fps"], 25)
        cur = dict(self.hd.DEFAULTS, source="mobcam", fps=25)
        self.assertEqual(self.hd.clean_settings({"bitrate": 12000}, cur)["fps"], 25)

    def test_bitrate_bis_20_mbit(self):
        self.assertEqual(self.hd.clean_settings({"bitrate": 20000})["bitrate"], 20000)

    def test_befehl_fuer_das_hilfsprogramm(self):
        cfg = dict(self.hd.DEFAULTS, source="mobcam", audio="mobcam", fps=60, bitrate=20000, key="hdmi")
        a = self.hd.mobcam_feeder_argv(cfg, 1935, "publish", helper="/opt/pipbox/mobcam_feed.py")
        self.assertIn("/opt/pipbox/mobcam_feed.py", a)
        self.assertEqual(a[a.index("--fps") + 1], "60")
        self.assertEqual(a[a.index("--bitrate") + 1], "20000")
        self.assertEqual(a[a.index("--audio") + 1], "mobcam")
        self.assertEqual(self.hd.mobcam_feeder_argv(dict(cfg, audio="none"), 1935, "publish")[-1], "none")
        with self.assertRaises(ValueError):
            self.hd.mobcam_feeder_argv(cfg, 1935, "../x")


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
        self.assertEqual(p["name"], "iPhone")
        self.assertEqual(p["id"], "05ac:12a8")

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
        d.cfg = dict(d.cfg, source="mobcam", enabled=True, audio="mobcam", fps=60)

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
        self.assertIn("--fps", gestartet[0])
        self.assertTrue(d.status()["usb"]["present"])
        self.assertEqual(d.status()["usb"]["name"], "iPhone")

    def test_warten_auf_moblin_ist_kein_fehler(self):
        usb = tempfile.mkdtemp()
        _write(os.path.join(usb, "9-1", "idVendor"), "05ac\n")
        d = self._daemon(usb, [])
        d.cfg = dict(d.cfg, source="mobcam", enabled=True)
        d.tail.append(self.hd.MOBCAM_WAIT)
        d.started = d.clock() - 100

        async def lauf():
            await d._watch_stream()
        asyncio.run(lauf())
        self.assertEqual(d.state, "starting")
        self.assertIn("Moblin", d.message)
        self.assertIsNone(d.missing_since)

    def test_quellenwechsel_koppelt_ton_und_bildrate(self):
        d = self._daemon(tempfile.mkdtemp(), [])
        d.cfg = dict(d.cfg, source="hdmi", audio="hdmi", fps=30)
        r = asyncio.run(d.handle({"cmd": "set", "settings": {"source": "mobcam"}}))
        self.assertEqual((r["settings"]["source"], r["settings"]["audio"]), ("mobcam", "mobcam"))
        r = asyncio.run(d.handle({"cmd": "set", "settings": {"fps": 60}}))
        self.assertEqual(r["settings"]["fps"], 60)
        r = asyncio.run(d.handle({"cmd": "set", "settings": {"source": "hdmi"}}))
        self.assertEqual((r["settings"]["audio"], r["settings"]["fps"]), ("hdmi", 30))


class TestMobcamHilfsprogramm(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "irl4you"))
        import mobcam_feed
        self.mf = mobcam_feed

    def test_geraet_wird_am_namen_gefunden(self):
        d = tempfile.mkdtemp()
        _write(os.path.join(d, "video0", "name"), "rk_hdmirx\n")
        _write(os.path.join(d, "video20", "name"), "Mobcam\n")
        self.assertEqual(self.mf.find_node(d), "/dev/video20")
        self.assertIsNone(self.mf.find_node(os.path.join(d, "fehlt")))

    def test_gst_befehl_60_fps_mit_ton_und_ohne(self):
        class A:
            fps, bitrate, key, rtmp_port, rtmp_app, audio = 60, 20000, "hdmi", 1935, "publish", "mobcam"
        a = self.mf.gst_argv(A, 1920, 1080)
        self.assertIn("framerate=60/1", a)
        self.assertIn("blocksize=3110400", a)
        self.assertIn("bps=20000000", a)
        self.assertIn("device=plughw:CARD=Loopback,DEV=1", a)
        self.assertEqual(a[-1], "location=rtmp://127.0.0.1:1935/publish/hdmi")
        A.audio = "none"
        b = self.mf.gst_argv(A, 1280, 720)
        self.assertIn("wave=silence", b)
        self.assertNotIn("device=plughw:CARD=Loopback,DEV=1", b)


class TestMobcamEinrichtung(unittest.TestCase):
    def _text(self, *teile):
        with open(os.path.join(ROOT, *teile), encoding="utf-8") as f:
            return f.read()

    def test_skript_prueft_summe_und_patch(self):
        s = self._text("irl4you", "install", "mobcam", "mobcam-setup.sh")
        self.assertIn("sha256sum -c", s)
        self.assertIn("64efc0607b5c9a160b05f5ecac61be4c78a9773aa02aa4d8e4cae8f10a54591e", s)
        self.assertIn("mobcam-threads.patch", s)
        self.assertIn("options v4l2loopback video_nr=20 card_label=Mobcam exclusive_caps=1 max_buffers=4", s)
        p = self._text("irl4you", "install", "mobcam", "mobcam-threads.patch")
        self.assertIn("thread_count = 3", p)
        self.assertIn("FF_THREAD_FRAME", p)

    def test_update_richtet_mobcam_ein_und_bricht_bei_fehler_nicht_ab(self):
        h = self._text("release", "hooks", "install")
        self.assertIn("bash install/mobcam/mobcam-setup.sh", h)
        self.assertIn("|| echo", h)
        self.assertIn('!= rollback', h)
        self.assertNotIn("sudo bash", self._text("irl4you", "mobcam_feed.py"))

    def test_lizenzhinweise_sind_da(self):
        self.assertIn("Mobcam (GPL-2.0)", self._text("NOTICE.md"))
        self.assertIn("mobcam-GPL-2.0.txt", self._text("licenses", "README.md"))
        self.assertIn("GNU GENERAL PUBLIC LICENSE", self._text("licenses", "mobcam-GPL-2.0.txt"))
        self.assertIn("eerimoq/mobcam", self._text("README.md"))


if __name__ == "__main__":
    unittest.main()
