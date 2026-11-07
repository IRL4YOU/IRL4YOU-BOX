"""Der H.264-Encoder der Box (mpph264enc) kennt die Eigenschaft "bps", nicht "bitrate": die MP4-Vorschau startete sonst gar nicht."""
import os
import re
import sys
import unittest
from unittest import mock

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

    def test_vorschau_verkleinert_im_decoder(self):
        # Verkleinern in Software (videoscale) schaffte auf einem schwachen Kern nur etwa 5 Bilder pro Sekunde: das Bild ruckelte stark
        for fmt in ("mp4", "mjpeg"):
            for codec in ("h264", "h265"):
                a = pipbox_preview.gst_argv(codec, 30, 640, fmt=fmt)
                self.assertNotIn("videoscale", a)
                i = a.index("mppvideodec")
                self.assertEqual(a[i + 1:i + 3], ["width=640", "height=360"], a)

    def test_vorschau_nutzt_hardware_skalierung(self):
        # Mit abgeschaltetem RGA (GST_MPP_NO_RGA=1) wich das Verkleinern auf die Software-Grafik (llvmpipe) aus: nur 12 bis 15 Bilder pro Sekunde, vier Kerne belegt
        pv = pipbox_preview.Preview(pipeline_path=None, big_cpus=lambda: [4, 5, 6, 7])
        with mock.patch.object(pipbox_preview.subprocess, "Popen") as popen:
            pv.spawn(30, 640, "mp4")
        env = popen.call_args.kwargs["env"]
        self.assertNotIn("GST_MPP_NO_RGA", env)

    def test_hdmi_dienst_nutzt_bps(self):
        with open(os.path.join(ROOT, "irl4you", "hdmi_daemon.py"), encoding="utf-8") as f:
            t = f.read()
        self.assertEqual(len(re.findall(r'"mpph264enc", "bps=%d"', t)), 4)
        self.assertNotIn('"mpph264enc", "bitrate=', t)


if __name__ == "__main__":
    unittest.main()
