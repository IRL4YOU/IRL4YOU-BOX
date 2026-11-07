"""Testbild als Kamera-Quelle: Wellenmuster mit Schrift, Zeit und Logo, Stereo-Testton, kein interleave mit Live-Quellen."""
import asyncio
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from test_irl4you import irl  # noqa: E402


class TestTestbild(unittest.TestCase):
    def setUp(self):
        self.hd = irl("hdmi_daemon")
        self.cfg = dict(self.hd.DEFAULTS, source="test", audio="hdmi", bitrate=4000, fps=30, key="hdmi")

    def test_quelle_ist_erlaubt(self):
        self.assertIn("test", self.hd.SOURCE_CHOICES)
        self.assertEqual(self.hd.clean_settings({"source": "test"})["source"], "test")
        with self.assertRaises(ValueError):
            self.hd.clean_settings({"source": "foto"})

    def test_befehl_ist_liste_mit_muster_zeit_logo(self):
        a = self.hd.test_feeder_argv(self.cfg, logo=True)
        self.assertIsInstance(a, list)
        self.assertEqual(a[:2], ["gst-launch-1.0", "-q"])
        for teil in ("videotestsrc", "pattern=zone-plate", "textoverlay", "timeoverlay", "rsvgoverlay", "flvmux"):
            self.assertIn(teil, a)
        self.assertIn("video/x-raw,format=BGRA,width=1280,height=720,framerate=30/1", a)
        self.assertEqual(a.count("videoconvert"), 1)
        self.assertIn("rtmp://127.0.0.1:1935/publish/hdmi", a[-1])

    def test_ohne_logo_element_laeuft_es_ohne_logo(self):
        a = self.hd.test_feeder_argv(self.cfg, logo=False)
        self.assertNotIn("rsvgoverlay", a)
        self.assertIn("timeoverlay", a)

    def test_logo_ist_feste_konstante(self):
        self.assertTrue(self.hd.TEST_LOGO.startswith("<svg"))
        a = self.hd.test_feeder_argv(self.cfg, logo=True)
        self.assertIn("data=" + self.hd.TEST_LOGO, a)

    def test_stereo_testton_links_tief_rechts_hoch(self):
        a = self.hd.test_feeder_argv(self.cfg, logo=False)
        self.assertEqual([x for x in a if x.startswith("freq=")], ["freq=440", "freq=660"])
        self.assertEqual([x for x in a if x.startswith("panorama=")], ["panorama=-1", "panorama=1"])
        self.assertIn("audiomixer", a)

    def test_kein_interleave_mit_live_quellen(self):
        # zwei Live-Tonquellen in interleave hängten den Start auf (nur etwa jeder zweite Start kam an)
        a = self.hd.test_feeder_argv(self.cfg, logo=False)
        self.assertNotIn("interleave", a)
        self.assertNotIn("adder", a)

    def test_ohne_ton_ist_stille(self):
        a = self.hd.test_feeder_argv(dict(self.cfg, audio="none"), logo=False)
        self.assertIn("wave=silence", a)
        self.assertNotIn("audiopanorama", a)

    def test_kodierer_nutzt_bps(self):
        a = self.hd.test_feeder_argv(self.cfg, logo=False)
        i = a.index("mpph264enc")
        self.assertEqual(a[i + 1], "bps=4000000")

    def test_rtmp_ziel_wird_geprueft(self):
        with self.assertRaises(ValueError):
            self.hd.test_feeder_argv(self.cfg, rtmp_app="a/b", logo=False)

    def test_dienst_meldet_signal_und_startet_ohne_hdmi(self):
        gestartet = []

        class P:
            returncode = None
            stderr = None

        async def spawn(argv):
            gestartet.append(argv)
            return P()

        d = self.hd.Daemon(tempfile.mkdtemp(), device="/gibt/es/nicht", spawn=spawn, publishing=lambda k: True)
        d.cfg = dict(self.cfg, enabled=True)
        self.assertTrue(d.available)

        async def lauf():
            await d.tick()
            await d.tick()
        asyncio.run(lauf())
        self.assertEqual(d.signal["width"], 1280)
        self.assertTrue(d.signal["locked"])
        self.assertEqual(len(gestartet), 1)
        self.assertIn("videotestsrc", gestartet[0])
        self.assertEqual(d.status()["settings"]["source"], "test")


if __name__ == "__main__":
    unittest.main()
