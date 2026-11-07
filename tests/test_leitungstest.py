"""Leitungstest: Messung je Leitung (Cloudflare, feste Adresse), Abfragen, Prüfung der Eingaben und Meldungen des Wächters."""
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from test_irl4you import irl  # noqa: E402


def ips():
    return [{"iface": "eth0", "ip": "192.168.1.5", "label": "Kabel"}, {"iface": "wlan0", "ip": "10.42.0.1", "label": "WLAN"},
            {"iface": "eth1", "ip": "", "label": "Kabel 2"}]


class TestLeitungstest(unittest.TestCase):
    def setUp(self):
        irl("hdmi_daemon")
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "irl4you"))
        from webui import uplinktest
        self.u = uplinktest

    def warte(self, t, sekunden=8):
        ende = time.time() + sekunden
        while time.time() < ende:
            if not t.status()["busy"]:
                return
            time.sleep(0.1)
        self.fail("Test wird nicht fertig")

    def test_demo_messung_liefert_werte(self):
        t = self.u.UplinkTests(demo=True, ips=ips)
        s = t.start(["eth0"])
        self.assertTrue(s["busy"])
        self.warte(t)
        r = t.status()["tests"]["eth0"]
        self.assertEqual(r["state"], "fertig")
        self.assertEqual((r["down_mbit"], r["up_mbit"], r["rtt_ms"]), (42.5, 8.3, 31))

    def test_leitung_pruefen(self):
        t = self.u.UplinkTests(demo=True, ips=ips, skip=lambda: {"wlan0"})
        with self.assertRaises(ValueError):
            t.start(["eth0; rm -rf /"])
        with self.assertRaises(ValueError):
            t.start([5])
        with self.assertRaises(ValueError):
            t.start(["wlan0"])
        with self.assertRaises(ValueError):
            t.start([])

    def test_alle_nimmt_nur_leitungen_mit_adresse_ohne_hotspot(self):
        t = self.u.UplinkTests(demo=True, ips=ips, skip=lambda: {"wlan0"})
        t.start([], allow_all=True)
        self.warte(t)
        self.assertEqual(sorted(t.status()["tests"]), ["eth0"])

    def test_zu_kurz_hintereinander_wird_nicht_wiederholt(self):
        t = self.u.UplinkTests(demo=True, ips=ips)
        t.start(["eth0"])
        self.warte(t)
        erste = t.status()["tests"]["eth0"]["finished"]
        t.start(["eth0"])
        self.assertEqual(t.status()["tests"]["eth0"]["finished"], erste)

    def test_ohne_adresse_klare_meldung(self):
        t = self.u.UplinkTests(demo=False, ips=lambda: [{"iface": "eth0", "ip": ""}])
        res = t._one("eth0")
        self.assertEqual(res["state"], "fehler")
        self.assertEqual(res["error"], "keine_adresse")
        self.assertIn("Adresse", res["text"])

    def test_messung_nutzt_nur_die_feste_adresse(self):
        self.assertEqual(self.u.HOST, "speed.cloudflare.com")
        self.assertLessEqual(self.u.DOWN_MAX, 30_000_000)
        self.assertLessEqual(self.u.UP_MAX, 15_000_000)

    def test_waechter_meldung_und_alter(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "status.json")
            json.dump({"ifaces": {"eth0": {"ok": False, "err": "kein_router"}, "ev il": {"ok": False}}}, open(f, "w"))
            h = self.u.read_health(f)
            self.assertEqual(list(h), ["eth0"])
            os.utime(f, (time.time() - 3600, time.time() - 3600))
            self.assertIsNone(self.u.read_health(f))
        self.assertIsNone(self.u.read_health("/gibt/es/nicht"))

    def test_ohne_waechter_keine_meldung(self):
        t = self.u.UplinkTests(demo=True, ips=ips)
        self.assertEqual(t.diagnose(["eth0"], {}, False), {})


if __name__ == "__main__":
    unittest.main()
