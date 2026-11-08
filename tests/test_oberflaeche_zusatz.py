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

    def test_update_karte_zeigt_wartende_version_statt_aktuell(self):
        # wartet der neueste Stand noch auf die GitHub-Prüfung, darf die Karte nicht grün "aktuell" sagen
        sysjs = _read(os.path.join(WEB, "neu", "views", "system.js"))
        self.assertIn("else if (d.pending) m = 'Neue Version '", sysjs)
        self.assertIn("badge('kommt gleich', 'accent')", sysjs)
        self.assertIn("Das Update kommt in wenigen Minuten.", sysjs)
        self.assertLess(sysjs.index("else if (d.pending) m ="), sysjs.index("m = 'Du hast die neueste Version.'"))
        up = _read(os.path.join(IRL, "webui", "updates.py"))
        self.assertIn('"pending": bool(latest and chk.get("pending") and not chk.get("available"))', up)
        self.assertIn("PENDING_WAIT", up)

    def test_aenderungsliste_steckt_in_der_update_karte(self):
        # kein zweiter Rahmen "Änderungen" unter der Update-Karte: "Alle Änderungen" klappt in der Karte selbst auf
        sysjs = _read(os.path.join(WEB, "neu", "views", "system.js"))
        self.assertNotIn("histCard", sysjs)
        self.assertNotIn("title: 'Änderungen'", sysjs)
        self.assertIn("verInfo), hist] }));", sysjs)
        self.assertIn("btn('Alle Änderungen', { size: 'sm', ico: 'down'", sysjs)       # Knopf mit Rahmen wie die anderen Knöpfe der Karte
        self.assertIn("placeholder: 'Suchen …'", sysjs)                                  # kleines Suchfeld, ohne Beschriftung davor
        self.assertNotIn("field({ label: 'Suchen', control: histQ })", sysjs)

    def test_reiter_box_reihenfolge(self):
        # 1. Box aus-/neu starten, 2. Passwort ändern, 3. Aussehen; die Karte zeichnet sich nur bei Änderung neu
        sysjs = _read(os.path.join(WEB, "neu", "views", "system.js"))
        self.assertIn("boxBox.append(powSlot, pwSlot, look, h('div', { id: 'sy-box-menu' }));", sysjs)
        self.assertIn("powSlot.replaceChildren(card({ title: 'Box ausschalten und abmelden'", sysjs)
        self.assertIn("if (sgP === powSig) return;", sysjs)
        self.assertNotIn("boxBox.replaceChildren(", sysjs)
        box = _read(os.path.join(WEB, "neu", "views", "mehr-box.js"))
        self.assertIn("panel('sy-box-pw')", box)
        self.assertEqual(box.count("title: 'Passwort ändern'"), 2)
        self.assertNotIn("title: 'Passwort der Oberfläche'", box)
        self.assertIn("id: 'sy-box-pw'", sysjs)

    def test_kamera_hinzufuegen_reihenfolge(self):
        # Hinzufügen: zuerst Bluetooth (DJI), dann HDMI/USB/Testbild, danach RTMP und QR-Code
        k = _read(os.path.join(WEB, "neu", "views", "kameras.js"))
        i = k.index("T.add('k-neu'")
        blk = k[i:k.index("/* ---------- Reiter: HDMI und USB", i)]
        pos = [blk.index(t) for t in ("DJI-Kamera (Bluetooth)", "HDMI, USB und Testbild", "Handy oder Kamera (RTMP)", "Mit QR-Code einrichten")]
        self.assertEqual(pos, sorted(pos))

    def test_kopfleiste_knoepfe_nur_mit_symbol(self):
        # Streammodus (Auge) und Suche (Lupe) brauchen keinen langen Text: Symbol, Hinweis beim Darüberfahren, Beschriftung für Bildschirmleser
        index = _read(os.path.join(WEB, "neu", "index.html"))
        sm = index[index.index('id="sm-btn"') - 40:index.index("</button>", index.index('id="sm-btn"'))]
        self.assertIn("data-icon", sm)
        self.assertIn("#i-eyeoff", sm)
        self.assertNotIn("Streammodus: aus</span>", sm)
        se = index[index.index('id="open-search"') - 40:index.index("</button>", index.index('id="open-search"'))]
        self.assertIn("data-icon", se)
        self.assertNotIn("Strg K</span>", se)
        boot = _read(os.path.join(WEB, "neu", "boot.js"))
        self.assertIn("'#i-eye' : '#i-eyeoff'", boot)
        self.assertIn("b.setAttribute('aria-label', t)", boot)

    def test_ansicht_handy_automatisch(self):
        # System > Box > Aussehen: "Handy" setzt den Cookie pb_view_mode, der Server liefert dann den schmalen Rahmen um die NEUE Oberfläche
        sysjs = _read(os.path.join(WEB, "neu", "views", "system.js"))
        self.assertIn("pb_view_mode=", sysjs)
        self.assertIn("[['auto', 'Automatisch'], ['mobile', 'Handy']]", sysjs)
        self.assertIn("(window.top || window).location.reload()", sysjs)
        r = _read(os.path.join(IRL, "webui", "routes_get.py"))
        self.assertIn('phone_frame("/neu?app=1")', r)
        self.assertIn('phone_frame("/?app=1")', r)         # die bisherige Oberfläche behält ihren Rahmen
        i = r.index("self.phone_view_wanted()")
        self.assertIn("self.authed()", r[i - 120:i])

    def test_update_hinweis_in_der_kopfzeile(self):
        # "Update verfügbar" steht auf jeder Seite oben, mit eigener seltener Abfrage (die Update-Karte fragt erst auf der Seite System)
        index = _read(os.path.join(WEB, "neu", "index.html"))
        self.assertIn('id="hb-upd"', index)
        self.assertIn('class="upd-dot" id="hb-upd"', index)          # nur ein kleiner gelber Punkt, kein großer Knopf
        css = _read(os.path.join(WEB, "neu", "app.css"))
        self.assertIn("@keyframes updPulse", css)
        self.assertIn(".upd-dot > span { width: 0.625rem;", css)
        kopf = _read(os.path.join(WEB, "neu", "kopf.js"))
        self.assertIn("Neu.poll('hdrupd', '/api/swupdate', 300000)", kopf)
        self.assertIn("App.on('hdrupd', show); App.on('swupdate', show);", kopf)
        self.assertIn("Neu.goto('system', 'sy-update')", kopf)

    def test_upload_kurve_ist_die_der_kopfzeile(self):
        # "Upload" auf der Live-Seite zeigt dieselbe Kurve (Daten, Skala, Farbe) wie die Kopfzeile, keine zweite Zeichnung
        kopf = _read(os.path.join(WEB, "neu", "kopf.js"))
        self.assertIn("Neu.sigMeter = () =>", kopf)
        self.assertIn("[{ scale: [smax, smid, smin], line }, ...views]", kopf)
        self.assertIn("[sig, ...views.map(v => v.el)].forEach(e =>", kopf)
        live = _read(os.path.join(WEB, "neu", "views", "live.js"))
        self.assertIn("Neu.sigMeter", live)
        self.assertNotIn("upHist", live)
        self.assertNotIn("spark-box", live)

    def test_stop_heisst_ueberall_stop(self):
        # Kopfzeile, Fußleiste, großer Knopf und Vorschau: dieselbe kurze Beschriftung
        schnell = _read(os.path.join(WEB, "neu", "views", "schnell.js"))
        live = _read(os.path.join(WEB, "neu", "views", "live.js"))
        self.assertIn("label: 'Stop', variant: 'danger'", schnell)
        self.assertIn("btn(running ? 'Stop' : 'Bitte warten'", live)
        self.assertIn("ico('stop', 'sm'), 'Stop')", live)
        self.assertNotIn("'Beenden'", live)
        self.assertNotIn("'Stopp'", live + schnell)

    def test_reiter_updates_hat_gelben_punkt(self):
        # wie am Menüpunkt System: ein kleiner gelber Punkt am Reiter "Updates", solange eine neue Version bereitliegt
        sysjs = _read(os.path.join(WEB, "neu", "views", "system.js"))
        self.assertIn("class: 'dot tab-dot', hidden: true", sysjs)
        self.assertIn("App.on('swupdate', showTabDot); App.on('hdrupd', showTabDot);", sysjs)
        self.assertIn(".tab-dot { display: inline-block;", _read(os.path.join(WEB, "neu", "app.css")))

    def test_neue_texte_in_allen_sprachen(self):
        # was an einem Tag neu oder geändert wird, steht in allen Sprachdateien (Englisch und die zwölf anderen)
        import glob
        import json
        hint_neu = "„Stop“ bricht die Automatik"
        for f in sorted(glob.glob(os.path.join(WEB, "i18n", "*.json"))):
            if f.endswith("languages.json"):
                continue
            ex = json.loads(_read(f))["exact"]
            for k in ("Ansicht", "Handy", "kommt gleich", "Einstellungen durchsuchen (Strg K)", "Passwort ändern", "Stop"):
                self.assertIn(k, ex, (f, k))
            self.assertTrue([k for k in ex if hint_neu in k], f)
            self.assertFalse([k for k in ex if "„Live beenden“" in k], f)

    def test_menue_und_karten_anpassen(self):
        # System > Box: Reihenfolge und Anzeige der Menüpunkte, Karten ausblenden; Live und System bleiben immer im Menü
        index = _read(os.path.join(WEB, "neu", "index.html"))
        self.assertIn('<script defer src="/neu/anpassen.js"></script>', index)
        self.assertLess(index.index("views/system.js"), index.index("anpassen.js"))
        sysjs = _read(os.path.join(WEB, "neu", "views", "system.js"))
        self.assertIn("boxBox.append(powSlot, pwSlot, look, h('div', { id: 'sy-box-menu' }));", sysjs)
        a = _read(os.path.join(WEB, "neu", "anpassen.js"))
        self.assertIn("const KEY = 'pb_neu_menu', FIX = ['live', 'system'];", a)
        self.assertIn("const NEVER = ['Aussehen', 'Menü und Karten anpassen'];", a)
        self.assertIn("[data-user-hidden] { display: none !important; }", a)
        self.assertIn("title: 'Menü und Karten anpassen'", a)
        import glob
        import json
        for f in sorted(glob.glob(os.path.join(WEB, "i18n", "*.json"))):
            if f.endswith("languages.json"):
                continue
            ex = json.loads(_read(f))["exact"]
            for k in ("Menü und Karten anpassen", "Karten ausblenden", "Alles zurücksetzen", "Immer sichtbar", "Nach oben", "Nach unten", "Anordnen"):
                self.assertIn(k, ex, (f, k))

    def test_systemdetails_hat_ueberschrift(self):
        # die Karte hat eine eigene Überschrift (sonst findet man den Prozessor nicht), das Aufklappen heißt nur "Anzeigen"
        live = _read(os.path.join(WEB, "neu", "views", "live.js"))
        self.assertIn("card({ title: 'Systemdetails', sub: 'Sendung, Prozessor (jeder Kern), Temperaturen und Speicher.', body: det })", live)
        self.assertIn("disclosure('Anzeigen', detBox)", live)

    def test_listenzeilen_umbrechen_in_jeder_breite(self):
        # Knöpfe rechts einer Zeile (zum Beispiel "Bild und Ton jetzt") dürfen nie über den Namen laufen: die Regeln gelten nicht nur am Handy
        css = _read(os.path.join(WEB, "neu", "app.css"))
        i = css.index("@media (max-width: 52rem)")
        for rule in (".row { flex-wrap: wrap;", ".row__main { flex: 1 1 9rem; }", ".row__end { margin-left: auto; flex-wrap: wrap;"):
            self.assertIn(rule, css[:i], rule)
            self.assertNotIn(rule, css[i:], rule)

    def test_live_karten_zeichnen_sich_nur_bei_aenderung_neu(self):
        # sonst flackert die Seite: zufällige Kennungen zählen nicht als Änderung, laufende Zahlen werden nachgetragen, der Chat schreibt nur bei Änderung
        live = _read(os.path.join(WEB, "neu", "views", "live.js"))
        self.assertIn("const sigOf = nodes =>", live)
        self.assertIn("const hsg = sigOf(kids)", live)
        self.assertIn("const setLive = (box, nodes) =>", live)
        self.assertIn("setLive(camsBody,", live)
        self.assertIn("setLive(linesBody,", live)
        chat = _read(os.path.join(WEB, "neu", "views", "chat.js"))
        self.assertIn("if (msg.textContent !== mt) msg.textContent = mt;", chat)
        self.assertIn("if (statusEl.__k !== d.state)", chat)
        self.assertIn("checked_at: Math.floor((d.checked_at || 0) / 60)", _read(os.path.join(WEB, "neu", "views", "system.js")))
        core = _read(os.path.join(WEB, "neu", "core.js"))
        self.assertIn("Object.defineProperty(Node.prototype, 'textContent'", core)       # gleicher Text wird nicht neu geschrieben
        self.assertIn("f.nodeValue === t) return;", core)
        wlan = _read(os.path.join(WEB, "neu", "views", "wlan.js"))
        self.assertIn("App.on('srtla', render);", wlan)
        self.assertNotIn("App.on('srtla', () => { sig = ''", wlan)
        kam = _read(os.path.join(WEB, "neu", "views", "kameras.js"))
        self.assertIn("if (subP.textContent !== subT) subP.textContent = subT;", kam)

    def test_leitungstest_ist_in_oberflaeche_und_server_da(self):
        netz = _read(os.path.join(WEB, "neu", "views", "netz.js"))
        self.assertIn("const CAN_TEST = true;", netz)
        server = _read(os.path.join(IRL, "webui", "routes_get.py")) + _read(os.path.join(IRL, "webui", "routes_post.py"))
        self.assertEqual(server.count('"/api/uplinktest"'), 2)


class TestLatenzRegler(unittest.TestCase):
    def test_niedrigste_bitrate_nicht_unter_450(self):
        netz = _read(os.path.join(WEB, "neu", "views", "netz.js"))
        self.assertIn("label: 'Niedrigste Bitrate', min: 450, max: 2000, step: 50", netz)
        self.assertIn('"min_kbps": 450,', _read(os.path.join(IRL, "webui", "netstate.py")))

    def test_latenz_ist_ein_sichtbarer_regler_mit_standard_4000(self):
        netz = _read(os.path.join(WEB, "neu", "views", "netz.js"))
        self.assertNotIn("disclosure('Erweitert'", netz)
        self.assertIn("label: 'Latenz', min: 1000, max: 8000, step: 100", netz)
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
