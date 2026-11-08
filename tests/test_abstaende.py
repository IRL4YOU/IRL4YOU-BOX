"""Einheitliche Abstände: Zwischen Karten und Spalten gilt überall 1rem (--space-4), wie zwischen den Kennzahlen-Kästchen."""
import os
import re
import unittest

CSS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "irl4you", "web", "neu", "app.css")


class TestAbstaende(unittest.TestCase):
    def test_raster_und_spalten_haben_den_gleichen_abstand(self):
        with open(CSS, encoding="utf-8") as f:
            css = f.read()
        for sel in (".view", ".cols-main", ".cols-2", ".col", ".editor", ".lc"):
            m = re.search(r"^\s*" + re.escape(sel) + r" \{[^}]*?gap: (var\(--space-\d\))", css, re.M)
            self.assertIsNotNone(m, sel)
            self.assertEqual(m.group(1), "var(--space-4)", sel)


if __name__ == "__main__":
    unittest.main()
