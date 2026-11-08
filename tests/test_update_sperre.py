"""Während ein Software-Update installiert wird, kann nicht live gegangen werden (und umgekehrt installiert das Update nicht während einer Sendung)."""
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402


class TestUpdateSperre(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.mod = irl("webui.send")
        self.send = self.mod.SendControl.__new__(self.mod.SendControl)
        self.send.demo = False
        self.path = os.path.join(self.d.name, "status.json")
        self.send.UPDATE_STATUS = self.path

    def write(self, **kw):
        with open(self.path, "w") as f:
            json.dump(kw, f)

    def test_installation_laeuft(self):
        self.write(state="installing", time=time.time())
        self.assertTrue(self.send.update_running())

    def test_kein_update(self):
        self.assertFalse(self.send.update_running())                      # Datei fehlt
        for st in ("idle", "checking", "done", "failed", "refused"):
            self.write(state=st, time=time.time())
            self.assertFalse(self.send.update_running(), st)

    def test_uebrig_gebliebener_stand_blockiert_nicht(self):
        self.write(state="installing", time=time.time() - 3600)           # Absturz mitten im Update: nach 30 Minuten wieder frei
        self.assertFalse(self.send.update_running())

    def test_kaputte_datei(self):
        with open(self.path, "w") as f:
            f.write("{")
        self.assertFalse(self.send.update_running())

    def test_demo_ohne_sperre(self):
        self.write(state="installing", time=time.time())
        self.send.demo = True
        self.assertFalse(self.send.update_running())

    def test_grund_steht_in_den_gruenden(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "irl4you", "webui", "send.py"), encoding="utf-8") as f:
            src = f.read()
        i = src.index("def reasons(self):")
        self.assertIn('r.append("Es läuft gerade ein Software-Update")', src[i:i + 300])


if __name__ == "__main__":
    unittest.main()
