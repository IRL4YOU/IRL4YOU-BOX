"""Der H.264-Encoder der Box (mpph264enc) kennt die Eigenschaft "bps", nicht "bitrate": die MP4-Vorschau startete sonst gar nicht."""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "irl4you"))
import pipbox_preview  # noqa: E402


class TestH264Encoder(unittest.TestCase):
    def test_vorschau_mp4_nutzt_bps(self):
        a = pipbox_preview.gst_argv("h265", 30, 640, fmt="mp4")
        i = a.index("mpph264enc")
        eigenschaften = []
        for x in a[i + 1:]:
            if x == "!":
                break
            eigenschaften.append(x)
        self.assertTrue(any(x.startswith("bps=") for x in eigenschaften), eigenschaften)
        self.assertFalse(any(x.startswith("bitrate=") for x in eigenschaften), eigenschaften)

    def test_hdmi_dienst_nutzt_bps(self):
        with open(os.path.join(ROOT, "irl4you", "hdmi_daemon.py"), encoding="utf-8") as f:
            t = f.read()
        self.assertEqual(len(re.findall(r'"mpph264enc", "bps=%d"', t)), 3)
        self.assertNotIn('"mpph264enc", "bitrate=', t)


if __name__ == "__main__":
    unittest.main()
