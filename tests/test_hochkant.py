"""Hochkant-Bild (Seite „Bild“): steht das Handy der IRL4YOU Cam hochkant, füllt es die ganze Höhe, links, Mitte oder rechts; die andere Kamera bleibt daneben sichtbar."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402


class TestHochkant(unittest.TestCase):
    def setUp(self):
        self.pl = irl("pipbox_live")
        self.pm = irl("webui.pipeline")
        self.d = tempfile.mkdtemp()
        self.store = self.pm.PipelineStore(os.path.join(self.d, "pipeline.json"))

    def cfg(self, **kw):
        c = dict(self.store.DEFAULT, type="pip", main="cam1", pip="cam2", always_ready=True, swap_cams=4)
        c.update(kw)
        return self.store._safe_cfg(c)

    def geom(self, c, dims):
        g = self.pl.small_geometry(c, 1)
        return self.pl.portrait_geometry(c, 1, g, dims) if dims[1] > dims[0] else g

    def test_ohne_einstellung_wie_bisher(self):
        c = self.cfg(corner=1, size_pct=25)
        g = self.geom(c, (1080, 1920))
        self.assertEqual(g["h"], self.pl.pip_size(25)[1], "Höhe wie das kleine Bild im Querformat")
        self.assertLess(g["w"], g["h"])

    def test_ganze_hoehe_links_mitte_rechts(self):
        for mode, soll_x in ((1, lambda w: 0), (2, lambda w: (1920 - w) // 2), (3, lambda w: 1920 - w)):
            g = self.geom(self.cfg(portrait=mode, corner=3, size_pct=20), (1080, 1920))
            self.assertEqual(g["h"], 1080, "ganze Höhe")
            self.assertEqual(g["y"], 0)
            self.assertEqual(g["w"], 1080 * 1080 // 1920 & ~1)
            self.assertEqual(g["x"], soll_x(g["w"]) & ~1)
            self.assertEqual(g["crop"], (0, 0, 0, 0))

    def test_querformat_bleibt_unberuehrt(self):
        c = self.cfg(portrait=2, corner=3, size_pct=25)
        self.assertEqual(self.geom(c, (1920, 1080)), self.pl.small_geometry(c, 1), "im Querformat gilt Größe und Ecke")

    def test_zweites_und_drittes_bild_haben_eigene_einstellung(self):
        c = self.cfg(pip2="cam3", corner2=0, portrait=0, portrait2=3)
        g2 = self.pl.portrait_geometry(c, 2, self.pl.small_geometry(c, 2), (1080, 1920))
        self.assertEqual((g2["h"], g2["x"] + g2["w"]), (1080, 1920))
        g1 = self.pl.portrait_geometry(c, 1, self.pl.small_geometry(c, 1), (1080, 1920))
        self.assertLess(g1["h"], 1080)

    def test_hauptbild_hochkant_links_und_rechts(self):
        c = self.cfg(portrait_main=1)
        roles_dims = {0: (1080, 1920), 1: (1920, 1080)}
        me, fill = self.pl.main_portrait_layout(c, roles_dims, 0, 1)
        w = 1080 * 1080 // 1920 & ~1
        self.assertEqual(me, (0, 0, w, 1080), "Handy links in ganzer Höhe")
        self.assertEqual(fill, (w, 0, 1920 - w, 1080), "die andere Kamera füllt den Rest")
        me, fill = self.pl.main_portrait_layout(self.cfg(portrait_main=3), roles_dims, 0, 1)
        self.assertEqual(me, (1920 - w, 0, w, 1080))
        self.assertEqual(fill, (0, 0, 1920 - w, 1080))

    def test_hauptbild_hochkant_nur_bei_hochkant_und_einstellung(self):
        d = {0: (1080, 1920), 1: (1920, 1080)}
        self.assertIsNone(self.pl.main_portrait_layout(self.cfg(portrait_main=0), d, 0, 1), "ausgeschaltet")
        self.assertIsNone(self.pl.main_portrait_layout(self.cfg(portrait_main=2), d, 0, 1), "Mitte gibt es für das Hauptbild nicht")
        self.assertIsNone(self.pl.main_portrait_layout(self.cfg(portrait_main=1), {0: (1920, 1080), 1: (1920, 1080)}, 0, 1), "Querformat bleibt wie bisher")
        self.assertIsNone(self.pl.main_portrait_layout(self.cfg(portrait_main=1), {}, 0, 1), "Größe unbekannt")
        me, fill = self.pl.main_portrait_layout(self.cfg(portrait_main=1), d, 0, None)
        self.assertIsNotNone(me)
        self.assertIsNone(fill, "ohne zweite Kamera nur das Handy am Rand")

    def test_fuellen_ohne_raender(self):
        # 16:9-Bild in den Rest neben dem Handy (1313×1080): links und rechts abschneiden, nichts oben/unten
        l, r, t, b = self.pl.fill_crop(1920, 1080, 1314, 1080)
        self.assertEqual((t, b), (0, 0))
        self.assertEqual(l, r)
        self.assertLessEqual(abs((1920 - l - r) * 1080 - 1314 * 1080), 2 * 1080)
        # schmales Ziel unten/oben: Bild ist höher als das Ziel
        l, r, t, b = self.pl.fill_crop(1920, 1080, 1920, 600)
        self.assertEqual((l, r), (0, 0))
        self.assertEqual(t, b)
        self.assertLessEqual(abs((1080 - t - b) * 1920 - 600 * 1920), 2 * 1920)
        self.assertEqual(self.pl.fill_crop(1920, 1080, 1920, 1080), (0, 0, 0, 0))
        self.assertTrue(all(v % 2 == 0 for v in self.pl.fill_crop(1280, 720, 1313, 1080)))

    def test_befehle_fuer_hauptbild_hochkant(self):
        c = self.cfg(portrait_main=1)
        lay = self.pl.Layout()
        keys = ["camA", "camB", "", "", "", ""][:self.pl.SLOTS]
        roles = {0: 0, 1: 1}
        dims = {0: (1080, 1920), 1: (1920, 1080)}
        lines = lay.commands(c, keys, roles, dims, {0, 1}, 0, -1, False, {})
        txt = "\n".join(lines)
        w = 1080 * 1080 // 1920 & ~1
        self.assertIn("pad mix sink_0 xpos 0", txt)
        self.assertIn("pad mix sink_0 width %d" % w, txt)
        self.assertIn("pad mix sink_0 height 1080", txt)
        self.assertIn("pad mix sink_1 xpos %d" % w, txt)
        self.assertIn("pad mix sink_1 width %d" % (1920 - w), txt)
        self.assertIn("pad mix sink_1 alpha 1.00", txt)
        self.assertIn("set cam1_crop left", txt)
        # Handy wieder quer: normales Bild
        lay2 = self.pl.Layout()
        txt2 = "\n".join(lay2.commands(c, keys, roles, {0: (1920, 1080), 1: (1920, 1080)}, {0, 1}, 0, -1, False, {}))
        self.assertIn("pad mix sink_0 width 1920", txt2)

    def test_speichern_hauptbild_hochkant(self):
        keys = ["cam1", "cam2"]
        base = dict(type="pip", main="cam1", pip="cam2", corner=3, size_pct=25)
        self.store.set(dict(base, portrait_main=3), keys)
        self.assertEqual(self.store.cfg["portrait_main"], 3)
        for bad in (2, 4, -1, "x"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.store.set(dict(base, portrait_main=bad), keys)

    def test_ungueltiger_wert_wird_abgefangen(self):
        self.assertEqual(self.cfg(portrait=9)["portrait"], 3)
        self.assertEqual(self.cfg(portrait=-1)["portrait"], 0)
        g = self.pl.portrait_geometry(dict(self.cfg(), portrait="x"), 1, self.pl.small_geometry(self.cfg(), 1), (1080, 1920))
        self.assertLess(g["h"], 1080)

    def test_speichern_prueft_den_wert(self):
        keys = ["cam1", "cam2"]
        base = dict(type="pip", main="cam1", pip="cam2", corner=3, size_pct=25)
        self.store.set(dict(base, portrait=2, portrait2=0, portrait3=3), keys)
        self.assertEqual((self.store.cfg["portrait"], self.store.cfg["portrait2"], self.store.cfg["portrait3"]), (2, 0, 3))
        for bad in (4, -1, "x"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.store.set(dict(base, portrait=bad), keys)

    def test_aenderung_wirkt_im_betrieb(self):
        a, b = self.cfg(portrait=0), self.cfg(portrait=2)
        self.assertTrue(self.pm.always_compatible(a, b) or not self.pl.supported(), "ohne Neustart der Sendekette, wenn die Live-Kette läuft")

    def test_schalter_nur_fuer_handy_der_irl4you_cam(self):
        with open(os.path.join(self.d, "hdmi.json"), "w") as f:
            json.dump({"source": "irlcam", "key": "hdmi"}, f)
        cams = [{"key": "hdmi", "name": "IRL4YOU Cam"}, {"key": "cam2", "name": "Andere"}]
        phones = {c["key"]: c["phone"] for c in self.store.status(cams)["cameras"]}
        self.assertEqual(phones, {"hdmi": True, "cam2": False})
        with open(os.path.join(self.d, "hdmi.json"), "w") as f:
            json.dump({"source": "usb", "key": "hdmi"}, f)
        self.assertFalse(self.store.status(cams)["cameras"][0]["phone"], "USB-Kamera und HDMI melden keine Hochkant-Lage")
        os.remove(os.path.join(self.d, "hdmi.json"))
        self.assertFalse(self.store.status(cams)["cameras"][0]["phone"])

    def test_handy_kennzeichen_vom_hdmi_dienst(self):
        """Der Webdienst darf hdmi.json nicht lesen (nur root); das Kennzeichen kommt vom HDMI-Dienst und wird übergeben."""
        cams = [{"key": "hdmi", "name": "IRL4YOU Cam"}, {"key": "cam2", "name": "Andere"}]
        phones = {c["key"]: c["phone"] for c in self.store.status(cams, {"hdmi"})["cameras"]}
        self.assertEqual(phones, {"hdmi": True, "cam2": False})
        self.assertFalse(any(c["phone"] for c in self.store.status(cams, set())["cameras"]))


if __name__ == "__main__":
    unittest.main()
