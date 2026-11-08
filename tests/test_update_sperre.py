"""Während ein Software-Update installiert wird, kann nicht live gegangen werden; ein tot übrig gebliebenes "installiert gerade" blockiert nicht; ein hängendes Update lässt sich abbrechen."""
import fcntl
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl  # noqa: E402


class Sperre:
    """Hält die Sperrdatei des Installers (wie der laufende Helfer) oder lässt sie los."""

    def __init__(self, path):
        self.path, self.fd = path, None

    def halten(self):
        if self.fd is not None:
            return
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def loslassen(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class Basis(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.status = os.path.join(self.d.name, "status.json")
        self.lock = os.path.join(self.d.name, "update.lock")
        self.sperre = Sperre(self.lock)
        self.addCleanup(self.sperre.loslassen)

    def schreibe(self, **kw):
        with open(self.status, "w") as f:
            json.dump(kw, f)


class TestSendeSperre(Basis):
    def setUp(self):
        super().setUp()
        mod = irl("webui.send")
        self.send = mod.SendControl.__new__(mod.SendControl)
        self.send.demo = False
        self.send.UPDATE_STATUS, self.send.UPDATE_LOCK = self.status, self.lock

    def test_installer_lebt(self):
        self.schreibe(state="installing", time=time.time())
        self.sperre.halten()
        self.assertTrue(self.send.update_running())

    def test_installer_lebt_nicht_mehr(self):
        self.schreibe(state="installing", time=time.time())
        open(self.lock, "w").close()                                       # Datei da, aber niemand hält sie: Absturz
        self.assertFalse(self.send.update_running())
        os.remove(self.lock)
        self.assertFalse(self.send.update_running())                       # Datei fehlt

    def test_nicht_pruefbar_dann_nach_alter(self):
        with mock.patch.object(self.send, "_lock_alive", return_value=None):
            self.schreibe(state="installing", time=time.time())
            self.assertTrue(self.send.update_running())
            self.schreibe(state="installing", time=time.time() - 3600)
            self.assertFalse(self.send.update_running())

    def test_kein_update(self):
        self.sperre.halten()
        self.assertFalse(self.send.update_running())                       # Datei fehlt
        for st in ("idle", "checking", "done", "failed", "refused"):
            self.schreibe(state=st, time=time.time())
            self.assertFalse(self.send.update_running(), st)

    def test_kaputte_datei(self):
        with open(self.status, "w") as f:
            f.write("{")
        self.assertFalse(self.send.update_running())

    def test_demo_ohne_sperre(self):
        self.schreibe(state="installing", time=time.time())
        self.sperre.halten()
        self.send.demo = True
        self.assertFalse(self.send.update_running())

    def test_grund_steht_in_den_gruenden(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "irl4you", "webui", "send.py"), encoding="utf-8") as f:
            src = f.read()
        i = src.index("def reasons(self):")
        self.assertIn('r.append("Es läuft gerade ein Software-Update")', src[i:i + 300])


class TestWurzelAusloeser(Basis):
    """Zweite Sicherung im Root-Dienst, der die Sendung wirklich startet."""

    def setUp(self):
        super().setUp()
        self.ctl = irl("pipbox_send_ctl")
        self.req = os.path.join(self.d.name, "req")
        self.ctl.REQ, self.ctl.UPDATE_STATUS, self.ctl.UPDATE_LOCK = self.req, self.status, self.lock

    def run_mode(self, mode, update=None, lebt=True):
        with open(self.req, "w") as f:
            f.write(mode + "\n")
        if update is not None:
            self.schreibe(state=update, time=time.time())
        if lebt:
            self.sperre.halten()
        with mock.patch.object(self.ctl.subprocess, "run") as run:
            self.ctl.main()
        return [c.args[0] for c in run.call_args_list]

    def test_start_und_neustart_werden_waehrend_des_updates_verworfen(self):
        self.assertEqual(self.run_mode("start", "installing"), [])
        self.assertEqual(self.run_mode("restart", "installing"), [])
        self.assertFalse(os.path.exists(self.req))                         # die Anforderung ist trotzdem abgeräumt

    def test_stopp_geht_immer(self):
        self.assertEqual(self.run_mode("stop", "installing"), [["systemctl", "stop", "pipbox-send.service"]])

    def test_ohne_update_startet_die_sendung(self):
        self.assertEqual(self.run_mode("start", "idle"), [["systemctl", "start", "--no-block", "pipbox-send.service"]])

    def test_toter_installer_blockiert_nicht(self):
        self.assertEqual(self.run_mode("start", "installing", lebt=False), [["systemctl", "start", "--no-block", "pipbox-send.service"]])


class TestOberflaecheUpdates(Basis):
    """Die Oberfläche erkennt ein totes Update und erlaubt das Abbrechen erst nach 5 Minuten Stillstand, nie beim Umschalten."""

    def setUp(self):
        super().setUp()
        mod = irl("webui.updates")
        self.up = mod.SwUpdate.__new__(mod.SwUpdate)
        self.up.demo = False
        self.up.LOCK = self.lock
        self.up.CANCEL = os.path.join(self.d.name, "cancel")

    def test_lock_alive(self):
        self.assertFalse(self.up.lock_alive())                             # Datei fehlt
        open(self.lock, "w").close()
        self.assertFalse(self.up.lock_alive())                             # niemand hält sie
        self.sperre.halten()
        self.assertTrue(self.up.lock_alive())

    def abbrechen(self, **st):
        with mock.patch.object(self.up, "status", return_value=st):
            return self.up.cancel(True)

    def test_abbrechen_erst_wenn_frei(self):
        for st, msg in (({"state": "idle"}, "kein Update"), ({"state": "installing", "cancel_in": None}, "nicht abgebrochen"), ({"state": "installing", "cancel_in": 180}, "5 Minuten")):
            with self.assertRaises(ValueError) as cm:
                self.abbrechen(**st)
            self.assertIn(msg, str(cm.exception))
        self.assertFalse(os.path.exists(self.up.CANCEL))
        self.abbrechen(state="installing", cancel_in=0)
        self.assertTrue(os.path.exists(self.up.CANCEL))                    # der Auslöser für den Abbruch-Dienst

    def test_abbrechen_braucht_bestaetigung(self):
        with self.assertRaises(ValueError):
            self.up.cancel(False)

    def test_aktion_cancel_ist_bekannt(self):
        with mock.patch.object(self.up, "cancel", return_value=None) as c:
            self.up.request("cancel", True)
        c.assert_called_once_with(True)


class TestDateien(unittest.TestCase):
    def test_einheiten_und_hook(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for n in ("irl4you-update-cancel.path", "irl4you-update-cancel.service"):
            self.assertTrue(os.path.exists(os.path.join(root, "updater", "systemd", n)), n)
        with open(os.path.join(root, "updater", "systemd", "irl4you-update-cancel.path"), encoding="utf-8") as f:
            self.assertIn("PathExists=/var/lib/pipbox/swupdate-cancel", f.read())
        with open(os.path.join(root, "release", "hooks", "install"), encoding="utf-8") as f:
            h = f.read()
        self.assertIn("irl4you-update-cancel.path", h)


if __name__ == "__main__":
    unittest.main()
