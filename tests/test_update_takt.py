"""Die automatische Update-Prüfung läuft alle 2 Stunden und mit der niedrigsten Priorität, damit sie eine Sendung nie stört."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYSTEMD = os.path.join(ROOT, "updater", "systemd")


def _text(name):
    with open(os.path.join(SYSTEMD, name), encoding="utf-8") as f:
        return f.read()


class TestUpdateTakt(unittest.TestCase):
    def test_alle_zwei_stunden(self):
        t = _text("irl4you-update-auto.timer")
        self.assertIn("OnUnitActiveSec=2h", t)
        self.assertIn("OnBootSec=2min", t)
        self.assertTrue(re.search(r"^RandomizedDelaySec=\d+min$", t, re.M))

    def test_niedrigste_prioritaet(self):
        s = _text("irl4you-update-auto.service")
        self.assertIn("Nice=19", s)
        self.assertIn("IOSchedulingClass=idle", s)
        self.assertIn("CPUSchedulingPolicy=idle", s)

    def test_oberflaeche_stoesst_pruefung_an_wenn_veraltet(self):
        import sys
        import tempfile
        import time
        sys.path.insert(0, os.path.join(ROOT, "irl4you"))
        from webui import updates
        sw = updates.SwUpdate
        with tempfile.TemporaryDirectory() as d:
            helfer = os.path.join(d, "helfer")
            open(helfer, "w").close()
            stf = os.path.join(d, "status.json")
            sw.STATUS, sw.HELPER = stf, helfer

            class Send:
                @staticmethod
                def _active():
                    return False
            u = sw(d, False, Send)
            req = os.path.join(d, "swupdate-request")
            # nach dem Start fehlt der Status: das Öffnen der Karte stößt eine Prüfung an
            u.check()
            self.assertTrue(os.path.exists(req))
            os.remove(req)
            # sofort danach nicht noch einmal (auch bei Fehlern kein Dauerfeuer)
            u.check()
            self.assertFalse(os.path.exists(req))
            # frische Prüfung: keine Anfrage
            u.asked = u.asked_auto = 0
            with open(stf, "w") as f:
                f.write('{"state": "idle", "checked": %d}' % int(time.time()))
            u.check()
            self.assertFalse(os.path.exists(req))
            # alte Prüfung: Anfrage
            with open(stf, "w") as f:
                f.write('{"state": "idle", "checked": %d}' % int(time.time() - 3 * 3600))
            u.check()
            self.assertTrue(os.path.exists(req))
            # während einer Sendung nie
            os.remove(req)
            u.asked = u.asked_auto = 0
            Send._active = staticmethod(lambda: True)
            u.check()
            self.assertFalse(os.path.exists(req))
            # auf Knopfdruck aber auch dann (kleine Abfrage, niedrige Priorität)
            u.check(force=True)
            self.assertTrue(os.path.exists(req))

    def test_meldung_bei_abfragegrenze(self):
        import io
        import sys
        import time
        import urllib.error
        import urllib.request
        from email.message import Message
        sys.path.insert(0, os.path.join(ROOT, "updater"))
        import irl4you_update as U

        class Opener:
            def open(self, req, timeout=30):
                h = Message()
                h["X-RateLimit-Remaining"] = "0"
                h["X-RateLimit-Reset"] = str(int(time.time()) + 25 * 60)
                raise urllib.error.HTTPError(req.full_url, 403, "rate limited", h, io.BytesIO(b"{}"))
        u = U.Updater.__new__(U.Updater)
        u.cfg = type("C", (), {"api": "https://api.github.com", "insecure": False, "token": staticmethod(lambda: "")})()
        u.opener = Opener()
        with self.assertRaises(U.Refuse) as cm:
            u._request("https://api.github.com/repos/x/y/commits", "application/json")
        self.assertIn("bremst", str(cm.exception))
        self.assertRegex(str(cm.exception), r"In etwa 2[56] Minuten")

    def test_abgelehnte_abfrage_ist_kein_dienstfehler(self):
        self.assertIn("SuccessExitStatus=2", _text("irl4you-update-auto.service"))

    def test_laufendes_update_ist_kein_dienstfehler(self):
        # trifft die regelmäßige Prüfung auf ein laufendes Update, endet sie mit Erfolg; ein von Hand gestartetes install meldet es weiter
        import fcntl
        import io
        import sys
        import tempfile
        from contextlib import redirect_stderr
        sys.path.insert(0, os.path.join(ROOT, "updater"))
        import irl4you_update as U
        with tempfile.TemporaryDirectory() as d:
            conf = os.path.join(d, "update.conf")
            with open(conf, "w", encoding="utf-8") as f:
                f.write("[update]\nstate_dir = %s\n" % os.path.join(d, "state"))
            os.makedirs(os.path.join(d, "state"))
            old = U.CONFIG
            U.Config.__init__.__defaults__ = (conf, None)
            try:
                with open(os.path.join(d, "state", "update.lock"), "w") as held:
                    fcntl.flock(held, fcntl.LOCK_EX)
                    with redirect_stderr(io.StringIO()):
                        self.assertEqual(U.main(["auto"]), 0)
                        self.assertEqual(U.main(["request"]), 0)
                        self.assertEqual(U.main(["install"]), 3)
            finally:
                U.Config.__init__.__defaults__ = (old, None)

    def test_liste_alle_aenderungen_holt_50_staende(self):
        # die Liste "Alle Änderungen" zeigt die letzten 50 Stände (vorher 15); die Versionsauswahl bleibt bei den neuesten 15
        with open(os.path.join(ROOT, "updater", "irl4you_update.py"), encoding="utf-8") as f:
            u = f.read()
        self.assertIn("HISTORY = 50", u)
        self.assertIn("commits = self.commits(self.HISTORY)", u)
        with open(os.path.join(ROOT, "irl4you", "webui", "updates.py"), encoding="utf-8") as f:
            w = f.read()
        self.assertIn("for r in rels[:15]:", w)

    def test_prueft_nur(self):
        # Die Prüfung ruft "auto" auf; installiert wird nur mit auto_install in update.conf (Standard: aus)
        self.assertIn("ExecStart=/usr/local/sbin/irl4you-update auto", _text("irl4you-update-auto.service"))
        with open(os.path.join(SYSTEMD, "..", "update.conf.example"), encoding="utf-8") as f:
            self.assertRegex(f.read(), r"(?m)^auto_install\s*=\s*false")


if __name__ == "__main__":
    unittest.main()
