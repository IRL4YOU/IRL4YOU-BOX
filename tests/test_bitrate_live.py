"""Bitrate-Grenzen (Netzwerk > Server > Minimum/Maximum) werden in der laufenden Sendung ohne Neustart übernommen."""
import json
import os
import shutil
import signal
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402


class FakeEncoder:
    pid = None

    def __init__(self):
        self.signals = []

    def poll(self):
        return None

    def send_signal(self, sig):
        self.signals.append(sig)


class TestBitrateLive(unittest.TestCase):
    def setUp(self):
        self.ps = irl("pipbox_send")
        self.d = tempfile.mkdtemp()
        self.old = (self.ps.STATE, self.ps.WORK)
        self.ps.STATE = self.ps.WORK = self.d
        self.set_settings(450, 12000)
        sv = {"name": "T", "host": "srtla.example.net", "port": 5000, "streamid": "abc"}
        self.s = self.ps.Sender(sv, 4000, ["10.0.0.2"], {"cfg": {}, "layout": (), "auto": False, "sig": self.ps.server.srtla_signature(self.data())})
        self.enc = FakeEncoder()
        self.s.procs["encoder"] = self.enc
        self.s.write_bitrate(450, 12000)

    def tearDown(self):
        self.ps.STATE, self.ps.WORK = self.old
        shutil.rmtree(self.d)

    def data(self):
        with open(os.path.join(self.d, "srtla.json")) as f:
            return json.load(f)

    def set_settings(self, mn, mx):
        with open(os.path.join(self.d, "srtla.json"), "w") as f:
            json.dump({"servers": [{"id": "a", "host": "h", "port": 1, "streamid": "x"}], "selected": "a",
                       "settings": {"min_kbps": mn, "max_kbps": mx, "latency_ms": 4000, "uplinks": ["eth0"], "spread": "all"}}, f)

    def file(self):
        with open(os.path.join(self.d, "bitrate")) as f:
            return f.read().split()

    def test_bitrate_loest_keine_neustart_meldung_aus(self):
        labels = irl("webui.pipeline_plugins").PENDING_LABELS
        self.assertNotIn("bitrate", [k for k, _ in labels])
        self.assertIn("latency", [k for k, _ in labels], "die Latenz braucht weiter einen Neustart")

    def test_unveraendert_nichts_tun(self):
        self.assertFalse(self.s.refresh_bitrate())
        self.assertEqual(self.enc.signals, [])

    def test_hochdrehen_und_zurueck_ohne_neustart(self):
        self.set_settings(450, 20000)
        self.assertTrue(self.s.refresh_bitrate())
        self.assertEqual(self.file(), ["450", "20000"])
        self.assertEqual(self.enc.signals, [signal.SIGHUP])
        self.assertFalse(self.s.refresh_bitrate(), "gleicher Wert nur einmal übernehmen")
        self.set_settings(450, 12000)
        self.assertTrue(self.s.refresh_bitrate())
        self.assertEqual(self.file(), ["450", "12000"])
        self.assertEqual(self.enc.signals, [signal.SIGHUP, signal.SIGHUP])

    def test_oberflaeche_zeigt_nichts_mehr_als_offen(self):
        pend = lambda: self.ps.server.srtla_signature(self.data())["bitrate"] != self.s.plan["sig"]["bitrate"]
        self.set_settings(450, 20000)
        self.assertTrue(pend())
        self.s.refresh_bitrate()
        self.assertFalse(pend())

    def test_waehrend_des_weichen_starts_nur_merken(self):
        self.s.soft_active = True
        self.s.bitrate_full = (450, 12000)
        self.s.write_bitrate(800, 800)                     # Startbitrate
        self.set_settings(450, 20000)
        self.assertTrue(self.s.refresh_bitrate())
        self.assertEqual(self.file(), ["800", "800"], "die Startbitrate bleibt stehen")
        self.assertEqual(self.enc.signals, [])
        self.assertEqual(self.s.bitrate_full, (450, 20000), "die letzte Phase schreibt die neuen Grenzen")

    def test_ohne_encoder_wartet_auf_den_naechsten_start(self):
        self.s.procs.pop("encoder")
        self.set_settings(450, 20000)
        self.assertFalse(self.s.refresh_bitrate())
        self.assertEqual(self.file(), ["450", "12000"])

    def test_ungueltige_werte_werden_nicht_uebernommen(self):
        for mn, mx in ((450, 450), (600, 500), (50, 8000), (450, 20001)):
            self.set_settings(mn, mx)
            self.assertFalse(self.s.refresh_bitrate(), (mn, mx))
        self.assertEqual(self.file(), ["450", "12000"])
        self.assertEqual(self.enc.signals, [])


if __name__ == "__main__":
    unittest.main()
