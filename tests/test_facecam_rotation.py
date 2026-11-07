"""Facecam und Rotation: die Facecam bleibt auf ihrem Platz, der Ton springt nicht mit der Rotation; Mikrofonsymbol fuer die Tonquelle."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_rotation import make  # noqa: E402
from test_irl4you import IRL  # noqa: E402


def cfg(**kw):
    c = {"type": "pip", "main": "vm-1", "pip": "vm-2", "pip2": "vm-3", "pip3": "vm-4", "auto_failover": True, "audio": "pip", "facecam": "vm-2",
         "rotation": {"on": True, "all": True, "slots": ["pip"], "seconds": 10, "pool": None}}
    c.update(kw)
    return c


class TestFacecamRotation(unittest.TestCase):
    def pubs(self, ctl, *keys):
        ctl.pub = {k: {} for k in keys}
        ctl.alive = set(keys)

    def test_facecam_bleibt_auf_ihrem_platz_bei_allen_wechseln(self):
        live, ctl, logs = make(cfg())
        self.pubs(ctl, "vm-1", "vm-2", "vm-3", "vm-4")
        ctl.rotate(0.0)
        for t in range(10, 200, 10):
            ctl.rotate(float(t) + 0.5)
            self.assertEqual(ctl.desired[1], "vm-2", "Platz 1 gehoert der Facecam, dort liegt auch der Ton")
            shown = [k for k in ctl.desired if k]
            self.assertEqual(len(shown), len(set(shown)))

    def test_die_anderen_kameras_wechseln_weiter(self):
        live, ctl, logs = make(cfg())
        self.pubs(ctl, "vm-1", "vm-2", "vm-3", "vm-4", "vm-5")
        ctl.rotate(0.0)
        seen = set()
        for t in range(10, 200, 10):
            ctl.rotate(float(t) + 0.5)
            seen.add(ctl.desired[0])
        self.assertGreater(len(seen), 1, "das Hauptbild wechselt weiter")
        self.assertNotIn("vm-2", seen)

    def test_ohne_facecam_wechseln_alle_wie_bisher(self):
        live, ctl, logs = make(cfg(facecam=""))
        self.pubs(ctl, "vm-1", "vm-2", "vm-3", "vm-4")
        ctl.rotate(0.0)
        seen = set()
        for t in range(10, 120, 10):
            ctl.rotate(float(t) + 0.5)
            seen.add(ctl.desired[1])
        self.assertGreater(len(seen), 1)

    def test_facecam_im_hauptbild_wird_auch_nicht_getauscht(self):
        live, ctl, logs = make(cfg(main="vm-2", pip="vm-1", facecam="vm-2", audio="main"))
        self.pubs(ctl, "vm-1", "vm-2", "vm-3", "vm-4")
        ctl.rotate(0.0)
        for t in range(10, 120, 10):
            ctl.rotate(float(t) + 0.5)
            self.assertEqual(ctl.desired[0], "vm-2")


class TestMikrofonSymbol(unittest.TestCase):
    def test_tonquelle_zeigt_ein_mikrofon(self):
        t = open(os.path.join(IRL, "web", "neu", "views", "schnell.js"), encoding="utf-8").read()
        self.assertNotIn("'speaker'", t)
        # Tonquelle (Leiste und Liste) und die Stumm-Taste: dreimal Mikrofon, kein Lautsprecher mehr
        self.assertEqual(t.count("a.mute ? 'micoff' : 'mic'"), 3)


if __name__ == "__main__":
    unittest.main()
