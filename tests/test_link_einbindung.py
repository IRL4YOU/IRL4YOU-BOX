"""Hilfshandy-Link: Einstellung der Oberfläche (LinkStore) und Übernahme der Leitung in die Sendekette (pipbox_send)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402  (liefert auch die Linux-Ersatzmodule für Windows)


class TestLinkStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="linkstore-")
        self.LinkStore = irl("webui.link").LinkStore

    def test_standard_ist_aus(self):
        st = self.LinkStore(self.dir).status()
        self.assertEqual((st["enabled"], st["password"], st["iface"], st["helpers"]), (False, "", "", []))

    def test_speichern_und_neu_laden(self):
        s = self.LinkStore(self.dir)
        s.put({"enabled": True, "password": "abc", "iface": "eth0"})
        s2 = self.LinkStore(self.dir)
        self.assertEqual((s2.data["enabled"], s2.data["password"], s2.data["iface"]), (True, "abc", "eth0"))
        self.assertEqual(os.stat(os.path.join(self.dir, "link.json")).st_mode & 0o777, 0o600)

    def test_teilweise_aenderung_laesst_rest_stehen(self):
        s = self.LinkStore(self.dir)
        s.put({"enabled": True, "password": "abc"})
        s.put({"iface": "wlan0"})
        self.assertEqual((s.data["enabled"], s.data["password"], s.data["iface"]), (True, "abc", "wlan0"))

    def test_ungueltige_werte(self):
        s = self.LinkStore(self.dir)
        for bad in ({"enabled": "ja"}, {"password": 5}, {"password": "x" * 65}, {"iface": "a b"}, {"iface": "x" * 16}, []):
            with self.assertRaises(ValueError, msg=str(bad)):
                s.put(bad)
        self.assertEqual(s.data, {"enabled": False, "password": "", "iface": ""})

    def test_leeres_passwort_ist_erlaubt(self):
        s = self.LinkStore(self.dir)
        s.put({"password": ""})
        self.assertEqual(s.data["password"], "")

    def test_status_aus_dem_dienst(self):
        s = self.LinkStore(self.dir)
        st_file = os.path.join(self.dir, "status.json")
        with open(st_file, "w") as f:
            json.dump({"enabled": True, "target": False, "searching": True, "helpers": [{"id": "01", "state": "up", "battery": 50}, "x"]}, f)
        s.STATUS = st_file
        st = s.status()
        self.assertTrue(st["service"])
        self.assertFalse(st["target"])
        self.assertTrue(st["searching"])
        self.assertEqual(st["helpers"], [{"id": "01", "state": "up", "battery": 50}])

    def test_ohne_dienst_kein_service(self):
        s = self.LinkStore(self.dir)
        s.STATUS = os.path.join(self.dir, "gibt-es-nicht.json")
        self.assertFalse(s.status()["service"])

    def test_kaputte_datei_wird_ignoriert(self):
        with open(os.path.join(self.dir, "link.json"), "w") as f:
            f.write("{kaputt")
        self.assertFalse(self.LinkStore(self.dir).data["enabled"])


class TestLinkLines(unittest.TestCase):
    def setUp(self):
        self.ps = irl("pipbox_send")
        self.f = os.path.join(tempfile.mkdtemp(prefix="linklines-"), "links")

    def write(self, text):
        with open(self.f, "w") as fh:
            fh.write(text)

    def test_zeilen_werden_gelesen(self):
        self.write("192.168.1.20 via 192.168.1.50:45678\n")
        self.assertEqual(self.ps.link_lines(self.f), ["192.168.1.20 via 192.168.1.50:45678"])

    def test_ohne_datei_leer(self):
        self.assertEqual(self.ps.link_lines(self.f + ".nein"), [])

    def test_fremde_und_kaputte_zeilen_fliegen_raus(self):
        self.write("192.168.1.20 via 192.168.1.50:45678\nquatsch\n1.2.3.4 via host:5\n; rm -rf /\n1.2.3.4 via 5.6.7.8\n")
        self.assertEqual(self.ps.link_lines(self.f), ["192.168.1.20 via 192.168.1.50:45678"])

    def test_hoechstens_acht(self):
        self.write("".join(f"10.0.0.1 via 10.0.0.{i}:4000\n" for i in range(2, 14)))
        self.assertEqual(len(self.ps.link_lines(self.f)), 8)


if __name__ == "__main__":
    unittest.main()
