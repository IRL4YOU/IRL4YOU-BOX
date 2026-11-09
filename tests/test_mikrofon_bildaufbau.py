"""Ton vom USB-Mikrofon im Bildaufbau (Seite „Bild“): „Ton von: Mikrofon (USB)“ mit Ton-Versatz, in der Live-Kette und in der Einzelbild-Kette."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402


def _karte(d, nr, cid, usb=True, capture=True):
    base = os.path.join(d, "card%d" % nr)
    os.makedirs(base)
    with open(os.path.join(base, "id"), "w") as f:
        f.write(cid)
    if usb:
        with open(os.path.join(base, "usbbus"), "w") as f:
            f.write("007/002")
    os.makedirs(os.path.join(base, "pcm0c" if capture else "pcm0p"))


class TestMikrofonBildaufbau(unittest.TestCase):
    def setUp(self):
        self.pl = irl("pipbox_live")
        self.pm = irl("webui.pipeline")
        self.send = irl("pipbox_send")
        self.store = self.pm.PipelineStore(os.path.join(tempfile.mkdtemp(), "pipeline.json"))
        self.keys = ["cam1", "cam2"]
        self._dev = self.pl.mic_device
        self.pl.mic_device = lambda asound="/proc/asound": "plughw:CARD=Rx"

    def tearDown(self):
        self.pl.mic_device = self._dev
        self.pl.MIC_BUILT = False

    def cfg(self, **kw):
        c = dict(self.store.DEFAULT, type="pip", main="cam1", pip="cam2", always_ready=True, swap_cams=4)
        c.update(kw)
        return self.store._safe_cfg(c)

    # ---- Einstellung speichern
    def test_speichern_mit_mikrofon_und_versatz(self):
        self.store.set({"type": "single", "main": "cam1", "audio": "mic", "mic_offset_ms": 250}, self.keys)
        self.assertEqual((self.store.cfg["audio"], self.store.cfg["mic_offset_ms"], self.store.cfg["type"]), ("mic", 250, "single"))
        self.store.set({"type": "pip", "main": "cam1", "pip": "cam2", "audio": "mic", "mic_offset_ms": 0}, self.keys)
        self.assertEqual((self.store.cfg["audio"], self.store.cfg["mic_offset_ms"], self.store.cfg["type"]), ("mic", 0, "pip"))
        self.store.set({"type": "pip", "main": "cam1", "pip": "cam2", "audio": "pip"}, self.keys)
        self.assertEqual(self.store.cfg["audio"], "pip")
        self.store.set({"type": "single", "main": "cam1"}, self.keys)
        self.assertEqual((self.store.cfg["audio"], self.store.cfg["mic_offset_ms"]), ("main", 0))

    def test_ungueltiger_versatz(self):
        for bad in (-1, 1501, "abc", 1.5e9):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.store.set({"type": "single", "main": "cam1", "audio": "mic", "mic_offset_ms": bad}, self.keys)
        self.assertEqual(self.cfg(mic_offset_ms=9999)["mic_offset_ms"], 1500, "gespeicherte Werte werden begrenzt")

    # ---- Tonkarte
    def test_tonkarte_suche(self):
        pl = irl("pipbox_live")
        pl.mic_device = self._dev
        d = tempfile.mkdtemp()
        self.assertIsNone(pl.mic_device(d))
        _karte(d, 0, "rockchipes8388", usb=False)
        _karte(d, 1, "Spk", capture=False)
        self.assertIsNone(pl.mic_device(d))
        _karte(d, 5, "Rx")
        self.assertEqual(pl.mic_device(d), "plughw:CARD=Rx")
        self.pl.mic_device = lambda asound="/proc/asound": "plughw:CARD=Rx"

    # ---- Live-Kette
    def test_live_kette_mit_mikrofon_eingang(self):
        text = self.pl.build(self.cfg(audio="mic", mic_offset_ms=300), "rtmp://127.0.0.1:1935/publish")
        self.assertTrue(self.pl.MIC_BUILT)
        self.assertIn("alsasrc name=mic device=plughw:CARD=Rx", text)
        self.assertIn("queue name=micq max-size-time=2300000000 max-size-buffers=0 max-size-bytes=0 min-threshold-time=300000000 ! audiosel.sink_%d" % (self.pl.SLOTS + 1), text)

    def test_live_kette_ohne_mikrofon_wie_vorher(self):
        text = self.pl.build(self.cfg(audio="main"), "rtmp://127.0.0.1:1935/publish")
        self.assertFalse(self.pl.MIC_BUILT)
        self.assertNotIn("alsasrc", text)
        self.pl.mic_device = lambda asound="/proc/asound": None                # gewählt, aber keine Tonkarte: Ton der Kamera, keine Störung
        text = self.pl.build(self.cfg(audio="mic"), "rtmp://127.0.0.1:1935/publish")
        self.assertFalse(self.pl.MIC_BUILT)
        self.assertNotIn("alsasrc", text)

    def _befehle(self, c):
        roles = {0: 0, 1: 1}
        slot_key = ["cam1", "cam2", None, None]
        dims = {0: (1920, 1080), 1: (1920, 1080)}
        lay = self.pl.Layout()
        return lay.commands(c, slot_key, roles, dims, {0, 1}, 0, -1, 0, {"cam1": 0, "cam2": 0})

    def test_live_befehle_waehlen_mikrofon_und_stellen_versatz(self):
        c = self.cfg(audio="mic", mic_offset_ms=120)
        self.pl.build(c, "rtmp://127.0.0.1:1935/publish")
        lines = self._befehle(c)
        self.assertIn("select audiosel sink_%d" % (self.pl.SLOTS + 1), lines)
        self.assertIn("set micq min-threshold-time 120000000", lines)
        c2 = dict(c, mic_offset_ms=0)                                          # Regler im Betrieb auf 0: neuer Befehl, Kette bleibt
        self.assertIn("set micq min-threshold-time 0", self._befehle(c2))
        self.pl.build(self.cfg(audio="main"), "rtmp://127.0.0.1:1935/publish")
        lines = self._befehle(self.cfg(audio="main"))
        self.assertIn("select audiosel sink_1", lines, "ohne Mikrofon: Ton der Hauptkamera")
        self.assertFalse(any("micq" in x for x in lines))

    # ---- Einzelbild-Kette
    def test_einzelbild_kette_mit_mikrofon(self):
        c = self.store._safe_cfg(dict(self.store.DEFAULT, type="single", main="cam1", audio="mic", mic_offset_ms=200))
        text = self.store.build(c)
        self.assertIn("alsasrc device=plughw:CARD=Rx", text)
        self.assertIn("min-threshold-time=200000000", text)
        self.assertIn("opusenc", text)
        self.assertIn("demux.audio !\nqueue max-size-buffers=4 leaky=downstream ! fakesink", text, "Ton der Kamera wird verworfen")
        text0 = self.store.build(self.store._safe_cfg(dict(c, mic_offset_ms=0)))
        self.assertNotIn("min-threshold-time=0", text0)
        self.pl.mic_device = lambda asound="/proc/asound": None
        text1 = self.store.build(c)
        self.assertNotIn("alsasrc", text1)
        self.assertIn("demux.audio !\n", text1)
        self.assertIn("aacparse ! avdec_aac", text1, "ohne Tonkarte: Ton der Kamera")

    # ---- Neustart-Regeln und Failover
    def test_wechsel_zum_mikrofon_braucht_neustart(self):
        a = self.cfg(audio="main")
        b = self.cfg(audio="mic")
        self.assertFalse(self.pm.always_compatible(a, b))
        self.assertFalse(self.pm.always_compatible(b, a))
        alt = self.pl.supported
        self.pl.supported = lambda: True                                        # Live-Kette (Überlagerungs-Baustein vorhanden)
        try:
            self.assertTrue(self.pm.always_compatible(b, dict(b, mic_offset_ms=400)), "Versatz ändern geht im Betrieb")
            self.assertFalse(self.pm.always_compatible(a, b))
        finally:
            self.pl.supported = alt
        self.assertFalse(self.pm.view_only_change(a, b))
        self.assertTrue(self.pm.view_only_change(a, dict(a, audio="pip")), "Tonwahl zwischen Kameras bleibt eine reine Ansicht")

    def test_failover_behaelt_das_mikrofon(self):
        c = self.cfg(audio="mic", mic_offset_ms=90)
        eff, used = self.send.effective_cfg(c, {"cam1", "cam2"})
        self.assertEqual((eff["audio"], eff["mic_offset_ms"]), ("mic", 90))
        eff2, _ = self.send.effective_cfg(c, {"cam2"})
        self.assertEqual(eff2["audio"], "mic")


if __name__ == "__main__":
    unittest.main()
