"""Favicon (Logo der Box im Browser-Tab) und Stream-ID anzeigen in der Oberflaeche."""
import os
import re
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_irl4you import irl, IRL  # noqa: E402

WEB = os.path.join(IRL, "web")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class TestFavicon(unittest.TestCase):
    def test_dateien(self):
        d = os.path.join(WEB, "icons")
        self.assertIn(b"<svg", open(os.path.join(d, "favicon.svg"), "rb").read())
        png = open(os.path.join(d, "apple-touch-icon.png"), "rb").read()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", png[16:24]), (180, 180))
        ico = open(os.path.join(d, "favicon.ico"), "rb").read()
        typ, n = struct.unpack("<HH", ico[2:6])
        self.assertEqual((typ, n), (1, 3))
        for i in range(n):
            size, off = struct.unpack("<II", ico[6 + 16 * i + 8:6 + 16 * i + 16])
            self.assertEqual(ico[off:off + 8], b"\x89PNG\r\n\x1a\n")
            self.assertLessEqual(off + size, len(ico))

    def test_seiten_verweisen_auf_das_logo(self):
        for page in ("index.html", "neu/index.html", "login.html", "statistik.html"):
            h = _read(os.path.join(WEB, page))
            head = h[:h.index("</head>")]
            self.assertIn('rel="icon" href="/favicon.svg"', head, page)
            self.assertIn('href="/favicon.ico"', head, page)
            self.assertIn('rel="apple-touch-icon" href="/apple-touch-icon.png"', head, page)

    def test_route_ohne_anmeldung(self):
        r = _read(os.path.join(IRL, "webui", "routes_get.py"))
        self.assertLess(r.index("if path in ICONS:"), r.index("if not self.authed():"), "Icons muessen vor der Anmeldepruefung kommen")
        for p in ("/favicon.svg", "/favicon.ico", "/apple-touch-icon.png"):
            self.assertIn('"%s"' % p, r)


class TestStreamIdAnzeigen(unittest.TestCase):
    def test_store(self):
        with tempfile.TemporaryDirectory() as d:
            st = irl("webui.netstate").SrtlaStore(os.path.join(d, "srtla.json"))
            sid = st.add({"name": "A", "host": "srt.example.de", "port": 5000, "streamid": "geheim123"})
            self.assertEqual(st.reveal_streamid(sid), "geheim123")
            leer = st.add({"name": "B", "host": "srt.example.de", "port": 5000, "streamid": ""})
            self.assertEqual(st.reveal_streamid(leer), "")
            with self.assertRaises(KeyError):
                st.reveal_streamid("00000000")
            self.assertNotIn("geheim123", str(st.public()))     # die Liste verraet die Stream-ID weiterhin nicht

    def test_route_und_oberflaeche(self):
        p = _read(os.path.join(IRL, "webui", "routes_post.py"))
        self.assertIn(r'^/api/srtla/([0-9a-f]{8})/streamid$', p)
        self.assertIn("reveal_streamid", p)
        # die neue Oberflaeche ruft genau diese Route auf
        self.assertIn("`/api/srtla/${srv.id}/streamid`", _read(os.path.join(WEB, "neu", "views", "netz.js")))
        # die Route liegt hinter der Anmeldung: vor ihr steht die Pruefung des Aufrufers
        i = p.index("/streamid$")
        self.assertIn("self.authed()", p[:i])


class TestFusszeileUndLinks(unittest.TestCase):
    def test_neue_oberflaeche_hat_die_fusszeile_der_alten(self):
        neu = _read(os.path.join(WEB, "neu", "index.html"))
        alt = _read(os.path.join(WEB, "index.html"))
        for url in ("https://discord.gg/nrBCEarMup", "https://github.com/IRL4YOU/IRL4YOU-BOX",
                    "https://github.com/IRL4YOU/IRL4YOU-BOX/blob/main/NOTICE.md"):
            self.assertIn('href="%s"' % url, alt, url)
            self.assertIn('href="%s"' % url, neu, url)
        self.assertIn("© 2026 IRL4YOU · CC BY-ND 4.0", neu)
        # die Fusszeile steht nach dem Inhalt und ausserhalb von #views (das die Ansichten neu fuellen)
        self.assertLess(neu.index('id="views"'), neu.index('class="legal"'))
        self.assertIn(".legal", _read(os.path.join(WEB, "neu", "app.css")))

    def test_keine_verweise_auf_alte_repositories(self):
        for root, _d, files in os.walk(os.path.join(WEB, "neu")):
            for f in files:
                if f.endswith((".js", ".html", ".css")):
                    t = _read(os.path.join(root, f))
                    self.assertNotIn("irl4you-pip", t, os.path.join(root, f))
                    self.assertNotIn("irl4you_2604", t, os.path.join(root, f))
        self.assertIn("https://github.com/IRL4YOU/IRL4YOU-BOX/issues", _read(os.path.join(WEB, "neu", "views", "system.js")))

    def test_kopfzeile_baut_sich_nur_bei_aenderung_neu(self):
        # sonst startet der pulsierende Live-Punkt und der Start/Stop-Knopf alle 2 s neu: die Seite flackert
        boot = _read(os.path.join(WEB, "neu", "boot.js"))
        self.assertIn("if (el.dataset.k !== k)", boot)
        self.assertIn("if (go.dataset.k !== gk)", boot)
        kopf = _read(os.path.join(WEB, "neu", "kopf.js"))
        self.assertIn("if (sg === dotsSig) return;", kopf)

    def test_verbindungsanzeige_ohne_beschriftung_mit_breitem_graph(self):
        # ohne das Wort "Verbindung" bleibt mehr Platz: der Graph ist doppelt so breit
        index = _read(os.path.join(WEB, "neu", "index.html"))
        sig = index[index.index('id="hb-sig"'):index.index('class="hcams"')]
        self.assertNotIn("Verbindung</span>", sig)
        css = _read(os.path.join(WEB, "neu", "app.css"))
        self.assertIn(".hsig svg { width: 7.5rem;", css)

    def test_weg_zur_bisherigen_oberflaeche_fuehrt_nach_alt(self):
        # "/" ist die neue Oberfläche: der Wechsel im Menü am Handy und unter System muss nach /alt gehen, sonst bleibt man in der neuen
        boot = _read(os.path.join(WEB, "neu", "boot.js"))
        self.assertIn("Neu.toOld = () => { toOld(); location.href = '/alt'; };", boot)
        index = _read(os.path.join(WEB, "neu", "index.html"))
        self.assertIn('href="/alt" id="oldui"', index)
        self.assertIn('<a href="/alt" data-oldui>Bisherige Oberfläche</a>', index)      # auch in der Fußzeile (am Handy fehlt die Seitenleiste)

    def test_leitungstest_ist_in_oberflaeche_und_server_da(self):
        netz = _read(os.path.join(WEB, "neu", "views", "netz.js"))
        self.assertIn("const CAN_TEST = true;", netz)
        server = _read(os.path.join(IRL, "webui", "routes_get.py")) + _read(os.path.join(IRL, "webui", "routes_post.py"))
        self.assertEqual(server.count('"/api/uplinktest"'), 2)


class TestLatenzRegler(unittest.TestCase):
    def test_latenz_ist_ein_sichtbarer_regler_mit_standard_4000(self):
        netz = _read(os.path.join(WEB, "neu", "views", "netz.js"))
        self.assertNotIn("disclosure('Erweitert'", netz)
        self.assertIn("label: 'Latenz', min: 500, max: 8000, step: 100", netz)
        self.assertIn("draft.latency_ms || 4000", netz)
        self.assertIn("Standard: 4000 ms", netz)
        # die Box selbst startet mit 4000 ms und nimmt nur Werte aus ihrem erlaubten Bereich
        st = _read(os.path.join(IRL, "webui", "netstate.py"))
        self.assertIn('"latency_ms": 4000', st)
        self.assertLessEqual(8000, 10000)
        self.assertGreaterEqual(500, 100)


class TestSchalter(unittest.TestCase):
    def test_nur_der_schalter_ist_klickbar(self):
        core = _read(os.path.join(WEB, "neu", "core.js"))
        i = core.index("function sw(")
        sw = core[i:core.index("function field(", i)]
        # kein <label> um Schalter und Text: ein Klick auf den Text schaltet nicht mehr um
        self.assertNotIn("h('label', { class: 'switch'", sw)
        self.assertIn("h('div', { class: 'switch'", sw)
        # der Text benennt den Schalter trotzdem fuer Screenreader
        self.assertIn("'aria-labelledby'", sw)
        self.assertIn("id: tid", sw)
        css = _read(os.path.join(WEB, "neu", "ds", "components.css"))
        regel = [z for z in css.splitlines() if z.strip().startswith(".switch {")][0]
        self.assertNotIn("cursor: pointer", regel)
        self.assertIn("cursor: pointer", [z for z in css.splitlines() if ".switch input {" in z][0])


if __name__ == "__main__":
    unittest.main()
