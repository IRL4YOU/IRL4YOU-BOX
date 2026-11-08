"""Alle Sprachdateien enthalten genau dieselben Texte wie Englisch, mit gleichen Platzhaltern und Zeilenumbrüchen."""
import glob
import json
import os
import re
import unittest

I18N = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "irl4you", "web", "i18n")


def _laden(pfad):
    with open(pfad, encoding="utf-8") as f:
        return json.load(f)["exact"]


class TestSprachenVollstaendig(unittest.TestCase):
    def test_alle_sprachen_wie_englisch(self):
        en = _laden(os.path.join(I18N, "en.json"))
        dateien = [p for p in sorted(glob.glob(os.path.join(I18N, "*.json"))) if not p.endswith(("en.json", "languages.json"))]
        self.assertGreaterEqual(len(dateien), 12)
        ph = lambda s: sorted(re.findall(r"\{[^}]*\}|%[sd]", s))
        for p in dateien:
            d = _laden(p)
            name = os.path.basename(p)
            self.assertEqual([k for k in en if k not in d][:3], [], name + ": fehlende Texte")
            self.assertEqual([k for k in d if k not in en][:3], [], name + ": überzählige Texte")
            for k, v in d.items():
                self.assertTrue(v.strip(), name + ": leer: " + k[:50])
                self.assertEqual(ph(k), ph(v), name + ": Platzhalter: " + k[:50])
                self.assertEqual(k.count("\n"), v.count("\n"), name + ": Zeilenumbrüche: " + k[:50])


if __name__ == "__main__":
    unittest.main()
