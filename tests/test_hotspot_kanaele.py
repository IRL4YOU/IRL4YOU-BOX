"""Hotspot-Kanäle je WLAN-Karte: iw-Ausgabe, Prüfung im Wurzel-Helfer und im Server."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl, load_script  # noqa: E402  (liefert auch die Linux-Ersatzmodule für Windows)

H = load_script("pipbox-wifi.py", "pipbox_wifi_kanaele")
W = irl("webui.wifi").Wifi

INTEL = """
                        * 2412 MHz [1] (22.0 dBm)
                        * 2417 MHz [2] (22.0 dBm)
                        * 2422 MHz [3] (22.0 dBm)
                        * 2427 MHz [4] (22.0 dBm)
                        * 2432 MHz [5] (22.0 dBm)
                        * 2437 MHz [6] (22.0 dBm)
                        * 2442 MHz [7] (22.0 dBm)
                        * 2447 MHz [8] (22.0 dBm)
                        * 2452 MHz [9] (22.0 dBm)
                        * 2457 MHz [10] (22.0 dBm)
                        * 2462 MHz [11] (22.0 dBm)
                        * 2467 MHz [12] (22.0 dBm)
                        * 2472 MHz [13] (22.0 dBm)
                        * 2484 MHz [14] (disabled)
                        * 5180 MHz [36] (22.0 dBm) (no IR)
                        * 5200 MHz [40] (22.0 dBm) (no IR)
                        * 5220 MHz [44] (22.0 dBm) (no IR)
                        * 5240 MHz [48] (22.0 dBm) (no IR)
                        * 5260 MHz [52] (22.0 dBm) (no IR, radar detection)
                        * 5280 MHz [56] (22.0 dBm) (no IR, radar detection)
                        * 5340 MHz [68] (disabled)
                        * 5500 MHz [100] (22.0 dBm) (no IR, radar detection)
                        * 5720 MHz [144] (22.0 dBm) (no IR, radar detection)
                        * 5745 MHz [149] (22.0 dBm)
                        * 5765 MHz [153] (22.0 dBm)
                        * 5785 MHz [157] (22.0 dBm)
                        * 5805 MHz [161] (22.0 dBm)
                        * 5825 MHz [165] (22.0 dBm)
                        * 5845 MHz [169] (disabled)
                        * 5865 MHz [173] (disabled)
"""
OPEN_CARD = """
        * 2412.0 MHz [1] (20.0 dBm)
        * 2437.0 MHz [6] (20.0 dBm)
        * 2462.0 MHz [11] (20.0 dBm)
        * 2472.0 MHz [13] (20.0 dBm) (passive scanning)
        * 5180.0 MHz [36] (23.0 dBm)
        * 5200.0 MHz [40] (23.0 dBm)
        * 5220.0 MHz [44] (23.0 dBm)
        * 5240.0 MHz [48] (23.0 dBm)
        * 5260.0 MHz [52] (23.0 dBm) (radar detection)
        * 5745.0 MHz [149] (23.0 dBm)
        * 5955 MHz [1] (12.0 dBm)
"""
INTEL_CH = {"bg": list(range(1, 14)), "a": [149, 153, 157, 161, 165]}
OPEN_CH = {"bg": [1, 6, 11], "a": [36, 40, 44, 48, 149]}




class ParseChannels(unittest.TestCase):
    def test_intel_karte_bietet_nur_erlaubte_kanaele(self):
        self.assertEqual(H.parse_channels(INTEL), INTEL_CH)
        self.assertEqual(W.parse_channels(INTEL), INTEL_CH)

    def test_offene_karte_behaelt_36_bis_48_ohne_radar_und_passive(self):
        self.assertEqual(H.parse_channels(OPEN_CARD), OPEN_CH)
        self.assertEqual(W.parse_channels(OPEN_CARD), OPEN_CH)

    def test_unlesbare_ausgabe_gibt_none(self):
        for bad in ("", "Wiphy phy0\n", "nonsense"):
            self.assertIsNone(H.parse_channels(bad))
            self.assertIsNone(W.parse_channels(bad))

    def test_alles_gesperrt_gibt_leere_listen(self):
        txt = "        * 2412 MHz [1] (disabled)\n        * 5180 MHz [36] (disabled)\n"
        self.assertEqual(H.parse_channels(txt), {"bg": [], "a": []})

    def test_ohne_iw_oder_phy_gibt_none(self):
        with mock.patch.object(H, "IW_PATHS", ("/gibt/es/nicht",)):
            self.assertIsNone(H.wifi_channels("wlan0"))
        self.assertIsNone(H.wifi_channels("wlan_gibt_es_nicht"))

    def test_iw_wird_mit_dem_phy_der_karte_gerufen(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "wlan7", "phy80211"))
        with open(os.path.join(d, "wlan7", "phy80211", "name"), "w") as f:
            f.write("phy3\n")
        run = mock.Mock(return_value=mock.Mock(returncode=0, stdout=INTEL))
        with mock.patch.object(H, "SYS_NET", d), mock.patch.object(H, "IW_PATHS", (sys.executable,)), mock.patch.object(H.subprocess, "run", run):
            self.assertEqual(H.wifi_channels("wlan7"), INTEL_CH)
        self.assertEqual(run.call_args[0][0], [sys.executable, "phy", "phy3", "info"])


class HelperChecks(unittest.TestCase):
    def check(self, band, ch, channels):
        with mock.patch.object(H, "wifi_caps", lambda i: {"ap": True, "2ghz": True, "5ghz": True}), \
                mock.patch.object(H, "wifi_channels", lambda i: channels):
            H.hs_check_caps("wlan0", band, ch)

    def test_gesperrter_kanal_wird_klar_abgelehnt(self):
        for ch in (36, 48):
            with self.assertRaises(ValueError) as e:
                self.check("a", ch, INTEL_CH)
            self.assertIn("nicht erlaubt", str(e.exception))

    def test_freie_kanaele_und_automatik(self):
        for ch in (149, 161, 165):
            self.check("a", ch, INTEL_CH)
        self.check("bg", 0, INTEL_CH)
        self.check("bg", 11, INTEL_CH)
        with self.assertRaises(ValueError) as e:
            self.check("a", 0, INTEL_CH)
        self.assertIn("festen Kanal", str(e.exception))
        self.check("a", 0, OPEN_CH)
        self.check("a", 36, OPEN_CH)
        with self.assertRaises(ValueError):
            self.check("a", 100, OPEN_CH)

    def test_ohne_kanalinfo_aendert_sich_nichts(self):
        for ch in (0, 36, 149):
            self.check("a", ch, None)

    def test_startfehler_ist_lesbar(self):
        d = tempfile.mkdtemp()

        def nm(*args, stdin=None, timeout=60):
            bad = args[:2] == ("con", "up")
            return mock.Mock(returncode=1 if bad else 0, stdout="", stderr="Error: Connection activation failed: 802.1X supplicant took too long to authenticate" if bad else "")
        with mock.patch.multiple(H, HOTSPOT_FILE=os.path.join(d, "hotspot.json"), STATE=d), \
                mock.patch.object(H, "check_iface", lambda i: None), mock.patch.object(H, "nm", nm), \
                mock.patch.object(H, "wifi_caps", lambda i: {"ap": True, "2ghz": True, "5ghz": True}), \
                mock.patch.object(H, "wifi_channels", lambda i: None), mock.patch.object(H, "connection_names", lambda: []):
            with self.assertRaises(RuntimeError) as e:
                H.do_hotspot_start({"iface": "wlan0", "ssid": "Box", "password": "geheim1234", "band": "a", "channel": 36})
        self.assertIn("Kanal", str(e.exception))
        self.assertNotIn("802.1X", str(e.exception))


class ServerChecks(unittest.TestCase):
    REQ = {"action": "hotspot_start", "iface": "wlan1", "ssid": "Box", "password": "geheim1234", "band": "a", "channel": 149}

    def make(self, channels):
        card = {"iface": "wlan1", "ip": "", "camera_net": False, "up": False, "ssid": "", "signal": None, "ap": True, "band24": True, "band5": True,
                "hotspot": None, "channels": channels}
        w = W(tempfile.mkdtemp(), False, mock.Mock(iface="eth2"), None, mock.Mock(data={"settings": {"uplinks": ["eth0"]}}))
        st = {"helper_installed": True, "cards": [card], "state": "idle", "message": "", "time": 0}
        p = mock.patch.object(w, "status", lambda: st)
        p.start()
        self.addCleanup(p.stop)
        return w

    def request(self, w, **kw):
        # _hotspot_request prüft alles vor dem Schreiben der Anfrage; das Schreiben selbst ist hier nicht Thema
        with mock.patch.object(W, "_send", create=True, return_value=None):
            return w._hotspot_request(dict(self.REQ, **kw), w.status(), w.status()["cards"][0])

    def test_server_lehnt_gesperrte_kanaele_ab(self):
        w = self.make(INTEL_CH)
        for bad in (36, 48, 0):
            with self.assertRaises(ValueError, msg=str(bad)):
                self.request(w, channel=bad)
        self.assertEqual(self.request(w)["channel"], 149)
        self.assertEqual(self.request(w, channel=165)["channel"], 165)
        w = self.make(OPEN_CH)
        self.assertEqual(self.request(w, channel=0)["channel"], 0)
        with self.assertRaises(ValueError):
            self.request(w, channel=100)

    def test_ohne_kanalinfo_gilt_die_feste_liste(self):
        w = self.make(None)
        for ch in (0, 36, 149, 165):
            self.request(w, channel=ch)
        with self.assertRaises(ValueError):
            self.request(w, channel=100)

    def test_hinweis_zur_sendeleistung_muss_beim_speichern_bestaetigt_werden(self):
        w = self.make(INTEL_CH)
        save = dict(self.REQ, action="hotspot_save")
        with self.assertRaises(ValueError) as e:
            self.request(w, **save)
        self.assertIn("Sendeleistung", str(e.exception))
        self.assertEqual(self.request(w, **save, power_ack=True)["channel"], 149)
        w = self.make(OPEN_CH)
        self.request(w, **dict(save, channel=36))       # 36-48: kein Hinweis nötig
        self.request(w, action="hotspot_start")         # Start nutzt das Gespeicherte, keine neue Bestätigung

    def test_karten_tragen_die_kanallisten(self):
        with mock.patch.object(W, "channels", staticmethod(lambda i: INTEL_CH)), \
                mock.patch.object(W, "caps", staticmethod(lambda i: {"ap": True, "band24": True, "band5": True})), \
                mock.patch("os.listdir", return_value=["wlan0"]), mock.patch("os.path.isdir", return_value=True):
            w = W(tempfile.mkdtemp(), False, mock.Mock(iface=""))
            try:
                cards = w.cards()
            except Exception as e:  # Umgebung ohne nmcli/dji-Geräte: nur die Kanalliste ist hier wichtig
                self.skipTest(str(e))
        self.assertEqual(cards[0]["channels"], INTEL_CH)


if __name__ == "__main__":
    unittest.main()
