"""Die automatische Update-Prüfung läuft jede Stunde und mit der niedrigsten Priorität, damit sie eine Sendung nie stört."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYSTEMD = os.path.join(ROOT, "updater", "systemd")


def _text(name):
    with open(os.path.join(SYSTEMD, name), encoding="utf-8") as f:
        return f.read()


class TestUpdateTakt(unittest.TestCase):
    def test_stuendlich(self):
        t = _text("irl4you-update-auto.timer")
        self.assertIn("OnUnitActiveSec=1h", t)
        self.assertIn("OnBootSec=10min", t)
        self.assertTrue(re.search(r"^RandomizedDelaySec=\d+min$", t, re.M))

    def test_niedrigste_prioritaet(self):
        s = _text("irl4you-update-auto.service")
        self.assertIn("Nice=19", s)
        self.assertIn("IOSchedulingClass=idle", s)
        self.assertIn("CPUSchedulingPolicy=idle", s)

    def test_prueft_nur(self):
        # Die Prüfung ruft "auto" auf; installiert wird nur mit auto_install in update.conf (Standard: aus)
        self.assertIn("ExecStart=/usr/local/sbin/irl4you-update auto", _text("irl4you-update-auto.service"))
        with open(os.path.join(SYSTEMD, "..", "update.conf.example"), encoding="utf-8") as f:
            self.assertRegex(f.read(), r"(?m)^auto_install\s*=\s*false")


if __name__ == "__main__":
    unittest.main()
