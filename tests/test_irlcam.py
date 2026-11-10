"""IRL4YOU Cam: Android-Handy mit der App per USB-Kabel als Kamera (Quelle "irlcam"). Bild und Ton gehen unverändert als RTMP an die Box."""
import asyncio
import json
import os
import struct
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from test_irl4you import irl  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "irl4you"))
import android_cam as ac  # noqa: E402
import mobcam_rtmp as mr  # noqa: E402


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class TestIrlcamEinstellungen(unittest.TestCase):
    def setUp(self):
        self.hd = irl("hdmi_daemon")

    def test_quelle_ist_erlaubt_und_mobcam_bleibt(self):
        self.assertIn("irlcam", self.hd.SOURCE_CHOICES)
        self.assertIn("mobcam", self.hd.SOURCE_CHOICES)
        self.assertEqual(self.hd.clean_settings({"source": "irlcam", "audio": "mobcam"})["source"], "irlcam")

    def test_befehl_nimmt_das_android_hilfsprogramm(self):
        cfg = dict(self.hd.DEFAULTS, source="irlcam", audio="mobcam", key="hdmi")
        a = self.hd.irlcam_feeder_argv(cfg, 1935, "publish", helper="/opt/pipbox/android_cam.py")
        self.assertIn("/opt/pipbox/android_cam.py", a)
        self.assertEqual(a[a.index("--key") + 1], "hdmi")
        self.assertEqual(a[a.index("--audio") + 1], "mobcam")
        self.assertTrue(self.hd.irlcam_feeder_argv(cfg)[2].endswith("android_cam.py"))
        self.assertTrue(self.hd.mobcam_feeder_argv(cfg)[2].endswith("mobcam_rtmp.py"))      # die Mobcam bleibt beim iPhone-Hilfsprogramm
        self.assertEqual(self.hd.irlcam_feeder_argv(dict(cfg, audio="none"))[-1], "none")
        with self.assertRaises(ValueError):
            self.hd.irlcam_feeder_argv(cfg, 1935, "../x")

    def test_quellenwechsel_koppelt_den_ton(self):
        d = self.hd.Daemon(tempfile.mkdtemp(), device="/gibt/es/nicht")
        d.cfg = dict(d.cfg, source="hdmi", audio="hdmi")
        r = asyncio.run(d.handle({"cmd": "set", "settings": {"source": "irlcam"}}))
        self.assertEqual((r["settings"]["source"], r["settings"]["audio"]), ("irlcam", "mobcam"))
        r = asyncio.run(d.handle({"cmd": "set", "settings": {"source": "mobcam"}}))
        self.assertEqual((r["settings"]["source"], r["settings"]["audio"]), ("mobcam", "mobcam"))
        r = asyncio.run(d.handle({"cmd": "set", "settings": {"source": "hdmi"}}))
        self.assertEqual(r["settings"]["audio"], "hdmi")


class TestIrlcamErkennung(unittest.TestCase):
    def setUp(self):
        self.hd = irl("hdmi_daemon")
        self.d = tempfile.mkdtemp()
        self.usb = os.path.join(self.d, "usb")

    def _dev(self, name, vid, pid, product="", klasse="00"):
        _write(os.path.join(self.usb, name, "idVendor"), vid + "\n")
        _write(os.path.join(self.usb, name, "idProduct"), pid + "\n")
        _write(os.path.join(self.usb, name, "bDeviceClass"), klasse + "\n")
        if product:
            _write(os.path.join(self.usb, name, "product"), product + "\n")

    def test_samsung_wird_gefunden_auch_im_zubehoer_modus(self):
        self._dev("4-1.3", "04e8", "6860", "SAMSUNG_Android")
        p = self.hd.find_android_phone(self.usb)
        self.assertEqual((p["name"], p["id"]), ("SAMSUNG_Android", "04e8:6860"))
        self.d = tempfile.mkdtemp()
        self.usb = os.path.join(self.d, "usb")
        self._dev("4-1.3", "18d1", "2d00", "Cam")
        self.assertEqual(self.hd.find_android_phone(self.usb)["id"], "18d1:2d00")

    def test_hubs_sticks_und_iphone_sind_kein_android(self):
        self._dev("4-1", "04e8", "0000", "Hub", klasse="09")                     # Hub eines bekannten Herstellers
        self._dev("4-1.2", "0b05", "190e", "ASUS USB-BT500")                     # Bluetooth-Stick
        self._dev("4-1.4", "0bda", "c811", "802.11ac NIC")
        self._dev("9-1", "05ac", "12a8", "iPhone")
        self.assertIsNone(self.hd.find_android_phone(self.usb))
        self.assertIsNone(self.hd.find_android_phone(os.path.join(self.d, "fehlt")))

    def test_usb_c_wird_nur_mit_android_liste_fuer_samsung_auf_host_geschaltet(self):
        tc = os.path.join(self.d, "typec")
        _write(os.path.join(tc, "port0", "data_role"), "host [device]\n")
        _write(os.path.join(tc, "port0-partner", "identity", "id_header"), "0xd54004e8\n")
        self.assertFalse(self.hd.typec_make_host(tc))                              # Mobcam (iPhone): Samsung bleibt unberührt
        self.assertTrue(self.hd.typec_make_host(tc, self.hd.ANDROID_VENDORS))
        with open(os.path.join(tc, "port0", "data_role")) as f:
            self.assertEqual(f.read(), "host")
        _write(os.path.join(tc, "port0", "data_role"), "host [device]\n")
        _write(os.path.join(tc, "port0-partner", "identity", "id_header"), "0xd4001234\n")
        self.assertFalse(self.hd.typec_make_host(tc, self.hd.ANDROID_VENDORS))     # fremder Hersteller


class TestIrlcamDienst(unittest.TestCase):
    def setUp(self):
        self.hd = irl("hdmi_daemon")
        self.t = 1000.0

    def _daemon(self, usb, gestartet, proc=False):
        outer = self

        class P:
            returncode = None
            stderr = None

        async def spawn(argv):
            gestartet.append(argv)
            return P()
        d = self.hd.Daemon(tempfile.mkdtemp(), device="/gibt/es/nicht", spawn=spawn, publishing=lambda k: True, sysusb=usb,
                           typec=os.path.join(usb, "tc"), clock=lambda: outer.t)
        d.cfg = dict(d.cfg, source="irlcam", enabled=True, audio="mobcam")
        if proc:
            d.proc = P()
        return d

    def test_ohne_handy_wird_gewartet_mit_handy_gestartet(self):
        usb = tempfile.mkdtemp()
        gestartet = []
        d = self._daemon(usb, gestartet)

        async def lauf():
            await d.tick()
            self.assertEqual(d.state, "waiting")
            self.assertEqual(d.message, self.hd.IRLCAM_PHONE_TEXT)
            self.assertEqual(gestartet, [])
            _write(os.path.join(usb, "4-1.3", "idVendor"), "04e8\n")
            _write(os.path.join(usb, "4-1.3", "product"), "SAMSUNG_Android\n")
            await d.tick()
        asyncio.run(lauf())
        self.assertEqual(len(gestartet), 1)
        self.assertTrue(gestartet[0][2].endswith("android_cam.py"))
        st = d.status()
        self.assertTrue(st["usb"]["present"])
        self.assertEqual(st["usb"]["name"], "SAMSUNG_Android")

    def test_iphone_startet_die_irl4you_cam_nicht(self):
        usb = tempfile.mkdtemp()
        _write(os.path.join(usb, "9-1", "idVendor"), "05ac\n")
        gestartet = []
        d = self._daemon(usb, gestartet)
        asyncio.run(d.tick())
        self.assertEqual(d.state, "waiting")
        self.assertEqual(gestartet, [])

    def test_kurzes_neumelden_nach_dem_umschalten_stoppt_nichts(self):
        usb = tempfile.mkdtemp()
        _write(os.path.join(usb, "4-1.3", "idVendor"), "04e8\n")
        d = self._daemon(usb, [], proc=True)
        asyncio.run(d.read_signal())
        self.assertTrue(d.status()["usb"]["present"])
        os.remove(os.path.join(usb, "4-1.3", "idVendor"))                          # Handy meldet sich gerade neu
        self.t += self.hd.IRLCAM_GAP - 1
        sig = asyncio.run(d.read_signal())
        self.assertTrue(sig["locked"])
        self.t += 2
        sig = asyncio.run(d.read_signal())
        self.assertFalse(sig["locked"])                                           # nach der Toleranz ist es wirklich weg

    def test_warten_auf_die_app_ist_kein_fehler(self):
        usb = tempfile.mkdtemp()
        _write(os.path.join(usb, "4-1.3", "idVendor"), "04e8\n")
        d = self._daemon(usb, [])
        d.tail.append(self.hd.IRLCAM_WAIT_APP + " (IRL4YOU Cam am Handy öffnen)")
        d.started = d.clock() - 100
        asyncio.run(d._watch_stream())
        self.assertEqual(d.state, "starting")
        self.assertEqual(d.message, self.hd.IRLCAM_APP_TEXT)
        self.assertIsNone(d.missing_since)
        d.tail.append("Warte auf das Handy (Gerät kennt AOA nicht)")
        asyncio.run(d._watch_stream())
        self.assertEqual(d.message, self.hd.IRLCAM_SWITCH_TEXT)

    def test_bildgroesse_mit_bildrate_wird_angezeigt(self):
        m = self.hd.MOBCAM_FORMAT_RE.match("Bild: 1920x1080 HEVC 30 fps, Ton: 48000 Hz 2 Kanäle")
        self.assertEqual(m.groups(), ("1920", "1080", "HEVC", "30"))
        self.assertIsNotNone(self.hd.MOBCAM_FORMAT_RE.match("Bild: 1920x1080 HEVC"))                  # Zeile des iPhone-Hilfsprogramms
        self.assertIsNone(self.hd.MOBCAM_FORMAT_RE.match("Bild: 1280x720 VP9"))

    def test_handydaten_nur_mit_angestecktem_handy_und_frischen_werten(self):
        d = self._daemon(tempfile.mkdtemp(), [], proc=True)
        d.usb = dict(d.usb, present=True)
        self.assertIsNone(d.phone_now())
        self.assertNotIn("phone", d.status())                                       # ältere App: keine Kachel
        d._phone_seen(json.dumps({"bat": 97, "chg": 1, "cur": 312, "temp": 31.5}))
        self.assertEqual(d.phone_now(), {"bat": 97, "chg": 1, "cur": 312, "temp": 31.5})
        self.assertEqual(d.status()["phone"]["bat"], 97)
        self.t += self.hd.PHONE_FRESH_S + 1                                          # App meldet sich nicht mehr: Kachel weg
        self.assertIsNone(d.phone_now())
        d._phone_seen(json.dumps({"bat": 96, "chg": 0}))
        self.assertEqual(d.phone_now(), {"bat": 96, "chg": 0})
        d.usb = dict(d.usb, present=False)                                           # Kabel abgezogen: Kachel weg
        self.assertIsNone(d.phone_now())
        d.usb = dict(d.usb, present=True)
        d.cfg = dict(d.cfg, source="mobcam")                                         # andere Quelle: keine Handydaten
        self.assertIsNone(d.phone_now())
        d.cfg = dict(d.cfg, source="irlcam")
        d._phone_seen("kaputt")                                                      # kein JSON, leer, falscher Typ: ignorieren
        d._phone_seen("{}")
        d._phone_seen("[1]")
        self.assertEqual(d.phone_now(), {"bat": 96, "chg": 0})
        d.proc = None                                                                # Einspeisung beendet: Kachel weg
        self.assertIsNone(d.phone_now())

    def test_akkuverlauf_ein_punkt_je_minute_und_neu_nach_langer_pause(self):
        d = self._daemon(tempfile.mkdtemp(), [], proc=True)
        d.usb = dict(d.usb, present=True)
        for i in range(5):                                                           # 5 Meldungen im Sekundentakt: nur ein Punkt
            d._phone_seen(json.dumps({"bat": 97, "chg": 1}))
            self.t += 1
        self.assertEqual(len(d.phone_hist), 1)
        self.assertNotIn("hist", d.phone_now())                                      # ein Punkt ist noch keine Kurve
        self.t += 60
        d._phone_seen(json.dumps({"bat": 96, "chg": 1}))
        self.t += 10
        d._phone_seen(json.dumps({"bat": 96, "chg": 1}))                             # (kein neuer Punkt, hält die Werte frisch)
        h = d.phone_now()["hist"]
        self.assertEqual([b for _, b in h], [97, 96])
        self.assertEqual([a for a, _ in h], [75, 10])                                # Sekunden seit dem Punkt
        for i in range(self.hd.PHONE_HIST_MAX + 20):                                 # höchstens 6 Stunden
            self.t += 61
            d._phone_seen(json.dumps({"bat": 90, "chg": 0}))
        self.assertEqual(len(d.phone_hist), self.hd.PHONE_HIST_MAX)
        self.t += self.hd.PHONE_HIST_GAP_S + 1                                       # lange nichts gehört: neuer Verlauf
        d._phone_seen(json.dumps({"bat": 50, "chg": 0}))
        self.assertEqual([b for _, b in d.phone_hist], [50])

    def test_handystand_im_journal_alle_fuenf_minuten_und_beim_wechsel(self):
        d = self._daemon(tempfile.mkdtemp(), [], proc=True)
        with self.assertLogs("pipbox-hdmi", level="INFO") as cm:
            d._phone_seen(json.dumps({"bat": 97, "chg": 1, "cur": 312, "temp": 31.5}))
            self.t += 60
            d._phone_seen(json.dumps({"bat": 97, "chg": 1}))                          # zu früh, kein Wechsel: nichts
            d._phone_seen(json.dumps({"bat": 96, "chg": 0}))                          # Laden aus: sofort
            self.t += self.hd.PHONE_LOG_S
            d._phone_seen(json.dumps({"bat": 95, "chg": 0}))
        msgs = [r.getMessage() for r in cm.records]
        self.assertEqual(msgs, ["IRL4YOU Cam: Handy Akku 97 %, lädt, 312 mA, 31.5 °C", "IRL4YOU Cam: Handy Akku 96 %, lädt nicht",
                                "IRL4YOU Cam: Handy Akku 95 %, lädt nicht"])
        with self.assertLogs("pipbox-hdmi", level="INFO") as cm:
            self.t += self.hd.PHONE_LOG_S
            d._phone_seen(json.dumps({"bat": 92, "chg": 1, "plug": 1, "cur_cal": 0, "temp": 30.0}))
        self.assertEqual([r.getMessage() for r in cm.records], ["IRL4YOU Cam: Handy Akku 92 %, lädt, Stromrichtung noch nicht erkannt, Kabel, 30.0 °C"])


class FakeRtmp:
    def __init__(self, *a):
        self.sent = []

    def send_data(self, ts, payload):
        self.sent.append(("data", ts, payload))

    def send_video(self, ts, payload):
        self.sent.append(("video", ts, payload))

    def send_audio(self, ts, payload):
        self.sent.append(("audio", ts, payload))

    def close(self):
        pass


class FakeAcc:
    def __init__(self):
        self.out = []

    def send(self, kind, payload=b""):
        self.out.append((kind, payload))

    def close(self):
        pass


def _config(codec="hevc", bitrate=10_000_000, ch=2):
    return json.dumps({"v": 1, "codec": codec, "w": 1920, "h": 1080, "fps": 30, "bitrate": bitrate,
                       "audio": {"codec": "aac", "rate": 48000, "ch": ch}}).encode()


SC = b"\x00\x00\x01"
HEVC_CSD = SC + bytes([0x40, 0x01, 0x0C]) + SC + bytes([0x42, 0x01, 0x01, 0x01, 0x60, 0, 0, 3, 0, 0x90, 0, 0, 3, 0, 0, 3, 0x5D, 0xA0, 0x02]) + SC + bytes([0x44, 0x01, 0xC0])
AVC_CSD = SC + bytes([0x67, 0x64, 0x00, 0x28, 0xAC]) + SC + bytes([0x68, 0xEE, 0x3C, 0x80])


class TestIrlcamHilfsprogramm(unittest.TestCase):
    def _session(self, audio="mobcam", dry=False):
        args = types.SimpleNamespace(key="hdmi", rtmp_port=1935, rtmp_app="publish", audio=audio, dry=dry)
        acc = FakeAcc()
        s = ac.Session(acc, args)
        fake = FakeRtmp()

        def open_rtmp():
            s.m = mr
            s.rtmp = fake
            s.codec = mr.CODEC_HEVC if s.cfg["codec"] == "hevc" else mr.CODEC_H264
            fake.send_video(0, mr.flv_video(s.codec, True, 0, s.record))
        s.open_rtmp = open_rtmp
        return s, acc, fake

    def test_annexb_wird_umgepackt(self):
        self.assertEqual(ac.split_annexb(SC + b"\x65AB" + b"\x00" + SC + b"\x41C"), [b"\x65AB", b"\x41C"])
        self.assertEqual(ac.to_length_prefixed(SC + b"\x65AB" + SC + b"\x41C"), b"\x00\x00\x00\x03\x65AB\x00\x00\x00\x02\x41C")
        rec = ac.avcc_record(AVC_CSD)
        self.assertEqual((rec[0], rec[1:4], rec[4], rec[5]), (1, bytes([0x64, 0x00, 0x28]), 0xFF, 0xE1))
        self.assertEqual(rec[-4:], bytes([0x68, 0xEE, 0x3C, 0x80]))
        with self.assertRaises(ValueError):
            ac.avcc_record(SC + bytes([0x67, 0x64, 0x00, 0x28]))                  # PPS fehlt
        hv = ac.hvcc_record(HEVC_CSD)
        self.assertEqual(hv[0], 1)
        with self.assertRaises(ValueError):
            ac.hvcc_record(SC + bytes([0x40, 0x01]))

    def test_bild_und_ton_werden_unveraendert_weitergereicht(self):
        s, acc, fake = self._session()
        s.handle(ac.MSG_CONFIG, _config())
        s.handle(ac.MSG_VIDEO_CSD, HEVC_CSD)
        s.handle(ac.MSG_AUDIO_CSD, b"\x11\x90")
        vf = lambda pts, key, data: struct.pack(">BQ", 1 if key else 0, pts) + data
        s.handle(ac.MSG_VIDEO, vf(5_000_000, False, SC + b"\x02P0"))                # vor dem ersten Schlüsselbild: verworfen
        s.handle(ac.MSG_VIDEO, vf(5_010_000, True, SC + b"\x26K1"))
        s.handle(ac.MSG_AUDIO, struct.pack(">Q", 5_012_000) + b"AAC1")
        s.handle(ac.MSG_VIDEO, vf(5_026_667, False, SC + b"\x02P2"))
        kinds = [k for k, *_ in fake.sent]
        self.assertEqual(kinds, ["video", "video", "audio", "audio", "video"])
        self.assertEqual(fake.sent[1], ("video", 0, bytes([0x1C, 1, 0, 0, 0]) + b"\x00\x00\x00\x03\x26K1"))
        self.assertEqual(fake.sent[2], ("audio", 0, bytes([0xAF, 0, 0x11, 0x90])))
        self.assertEqual(fake.sent[3], ("audio", 2, bytes([0xAF, 1]) + b"AAC1"))
        self.assertEqual(fake.sent[4][1], 16)
        self.assertEqual(acc.out, [])                                               # 10 Mbit/s: nichts herunterstellen

    def test_zu_hohe_bitrate_wird_auf_10_mbit_heruntergestellt(self):
        s, acc, fake = self._session()
        s.handle(ac.MSG_CONFIG, _config(bitrate=20_000_000))
        self.assertEqual(acc.out, [(ac.CMD_BITRATE, struct.pack(">I", 10_000_000))])

    def test_beim_start_wird_die_konfiguration_angefordert(self):
        class Ende(Exception):
            pass
        s, acc, fake = self._session()
        s.acc.message = lambda: (_ for _ in ()).throw(Ende())
        with self.assertRaises(Ende):
            s.run()
        self.assertEqual([k for k, _ in acc.out], [ac.CMD_CONFIG, ac.CMD_KEYFRAME])

    def test_zeitsprung_des_bilds_wird_nachgezogen(self):
        zeit = [100.0]
        args = types.SimpleNamespace(key="hdmi", rtmp_port=1935, rtmp_app="publish", audio="mobcam", dry=False)
        s = ac.Session(FakeAcc(), args, clock=lambda: zeit[0])
        zeilen = []
        orig = ac.say
        ac.say = zeilen.append
        try:
            pts = 5_000_000
            for i in range(30):                                    # 60 Bilder/s, Ankunft mit etwas Unruhe: nichts wird verschoben
                s.track_video(pts)
                pts += 16_667
                zeit[0] += 0.016667 + (0.04 if i % 7 == 0 else 0)
                zeit[0] -= 0.04 if i % 7 == 1 else 0
            self.assertEqual(s.vshift, 0)
            self.assertEqual(zeilen, [])
            zeit[0] += 1.4                                         # Pause der App, im Zeitstempel nicht enthalten
            pts += 16_667
            s.track_video(pts)
            self.assertAlmostEqual(s.vshift, 1400, delta=120)
            self.assertTrue(any("nachgezogen" in z for z in zeilen))
            self.assertEqual(s.ts(pts, "v") - 0, s.ts(pts, "v"))
            vor = s.vshift
            for _ in range(10):
                pts += 16_667
                zeit[0] += 0.016667
                s.track_video(pts)
            self.assertEqual(s.vshift, vor)                        # danach läuft es wieder ruhig
        finally:
            ac.say = orig

    def test_pause_mit_passendem_zeitstempel_wird_nicht_verschoben(self):
        zeit = [10.0]
        args = types.SimpleNamespace(key="hdmi", rtmp_port=1935, rtmp_app="publish", audio="mobcam", dry=False)
        s = ac.Session(FakeAcc(), args, clock=lambda: zeit[0])
        s.track_video(1_000_000)
        zeit[0] += 2.0
        s.track_video(3_000_000)                                   # Zeitstempel hat die Pause mitgezählt
        self.assertEqual(s.vshift, 0)

    def _hallo(self, zeit, **kw):
        args = types.SimpleNamespace(key="hdmi", rtmp_port=1935, rtmp_app="publish", audio="mobcam", dry=False, **kw)
        acc = FakeAcc()
        s = ac.Session(acc, args, clock=lambda: zeit[0])
        fake = FakeRtmp()
        opened = []

        def open_rtmp():
            opened.append(1)
            s.m = mr
            s.rtmp = fake
            s.codec = mr.CODEC_HEVC if s.cfg["codec"] == "hevc" else mr.CODEC_H264
            fake.send_video(0, mr.flv_video(s.codec, True, 0, s.record))
        s.open_rtmp = open_rtmp
        return s, acc, fake, opened

    def _start(self, s):
        s.handle(ac.MSG_CONFIG, _config())
        s.handle(ac.MSG_VIDEO_CSD, HEVC_CSD)
        s.handle(ac.MSG_VIDEO, struct.pack(">BQ", 1, 1_000_000) + SC + b"\x26K1")

    def test_gleiche_konfiguration_aendert_nichts(self):
        zeit = [10.0]
        s, acc, fake, opened = self._hallo(zeit)
        self._start(s)
        self.assertIs(s.rtmp, fake)
        s.handle(ac.MSG_CONFIG, _config())                                          # REQUEST_CONFIG: gleiche Werte noch einmal
        self.assertIs(s.rtmp, fake)
        self.assertEqual(s.hold_until, 0.0)

    def test_neue_groesse_schliesst_den_strom_wartet_und_oeffnet_neu(self):
        zeit = [10.0]
        s, acc, fake, opened = self._hallo(zeit)
        self._start(s)
        hoch = dict(json.loads(_config().decode()), w=1080, h=1920)
        zeilen = []
        orig = ac.say
        ac.say = zeilen.append
        try:
            s.handle(ac.MSG_CONFIG, json.dumps(hoch).encode())
        finally:
            ac.say = orig
        self.assertIsNone(s.rtmp)                                                   # Strom ist zu: die Live-Kette kann den Zweig abschalten
        self.assertTrue(any("neu aufgebaut" in z for z in zeilen))
        s.handle(ac.MSG_VIDEO_CSD, HEVC_CSD)
        n = len(opened)
        s.handle(ac.MSG_VIDEO, struct.pack(">BQ", 1, 1_400_000) + SC + b"\x26K2")     # 0,4 s später: Zweig noch nicht sicher aus
        zeit[0] += 2.0
        s.handle(ac.MSG_VIDEO, struct.pack(">BQ", 1, 3_400_000) + SC + b"\x26K3")
        self.assertEqual(len(opened), n)                                            # immer noch gewartet, nichts gesendet
        self.assertIsNone(s.rtmp)
        zeit[0] += 2.0                                                              # Wartezeit (3,5 s) vorbei
        s.handle(ac.MSG_VIDEO, struct.pack(">BQ", 1, 5_400_000) + SC + b"\x26K4")
        self.assertEqual(len(opened), n + 1)
        self.assertIs(s.rtmp, fake)
        self.assertIn(ac.CMD_KEYFRAME, [k for k, _ in acc.out])                      # Schlüsselbild für den neuen Strom angefordert

    def test_hinweis_dreht_gleich_schliesst_sofort_und_verlaengert_nicht(self):
        zeit = [10.0]
        s, acc, fake, opened = self._hallo(zeit)
        self._start(s)
        s.handle(ac.MSG_ROTATE, b"")
        self.assertIsNone(s.rtmp)
        hold = s.hold_until
        self.assertAlmostEqual(hold - zeit[0], ac.HOLD_S, delta=0.01)
        zeit[0] += 0.4                                                               # App baut um: kurze Pause, dann neue Konfiguration
        hoch = dict(json.loads(_config().decode()), w=1080, h=1920)
        s.handle(ac.MSG_CONFIG, json.dumps(hoch).encode())
        self.assertEqual(s.hold_until, hold)                                         # kein zweites Warten obendrauf
        s.handle(ac.MSG_VIDEO_CSD, HEVC_CSD)
        s.handle(ac.MSG_VIDEO, struct.pack(">BQ", 1, 1_500_000) + SC + b"\x26K2")
        self.assertIsNone(s.rtmp)
        zeit[0] += ac.HOLD_S
        s.handle(ac.MSG_VIDEO, struct.pack(">BQ", 1, 5_000_000) + SC + b"\x26K3")
        self.assertIs(s.rtmp, fake)

    def test_nahtloser_wechsel_der_app_laesst_den_strom_offen_ohne_wartezeit(self):
        zeit = [10.0]
        s, acc, fake, opened = self._hallo(zeit)                                      # Standardmodus (restart)
        self._start(s)
        n = len(fake.sent)
        hoch = dict(json.loads(_config().decode()), w=1080, h=1920, seamless=True)
        s.handle(ac.MSG_CONFIG, json.dumps(hoch).encode())
        self.assertIs(s.rtmp, fake)                                                   # Strom bleibt offen
        self.assertEqual(s.hold_until, 0.0)                                           # keine Wartezeit
        s.handle(ac.MSG_VIDEO_CSD, HEVC_CSD)
        zeit[0] += 0.03                                                               # Schlüsselbild kommt 30 ms später
        s.handle(ac.MSG_VIDEO, struct.pack(">BQ", 1, 1_040_000) + SC + b"\x26K2")
        self.assertEqual([k for k, *_ in fake.sent[n:]], ["data", "video", "video"])
        # ohne seamless (ältere App) wird weiter geschlossen und gewartet
        s2, acc2, fake2, opened2 = self._hallo([10.0])
        self._start(s2)
        s2.handle(ac.MSG_CONFIG, json.dumps(dict(json.loads(_config().decode()), w=1080, h=1920)).encode())
        self.assertIsNone(s2.rtmp)
        self.assertGreater(s2.hold_until, 10.0)
        # Codecwechsel ist nie nahtlos
        s3, acc3, fake3, opened3 = self._hallo([10.0])
        self._start(s3)
        s3.handle(ac.MSG_CONFIG, json.dumps(dict(json.loads(_config(codec="avc").decode()), seamless=True)).encode())
        self.assertIsNone(s3.rtmp)

    def test_wachter_fordert_neu_an_wenn_kein_bild_an_die_box_geht(self):
        zeit = [10.0]
        s, acc, fake, opened = self._hallo(zeit)
        s.handle(ac.MSG_CONFIG, _config())                                            # Parametersätze kommen nie an (verpasst)
        n = len(acc.out)
        for _ in range(5):
            zeit[0] += 0.5
            s.handle(ac.MSG_AUDIO, struct.pack(">Q", 1) + b"A")
        self.assertEqual(len(acc.out), n)                                             # noch keine 3 s
        zeit[0] += 1.0
        s.handle(ac.MSG_AUDIO, struct.pack(">Q", 1) + b"A")
        self.assertEqual([k for k, _ in acc.out[n:]], [ac.CMD_CONFIG, ac.CMD_KEYFRAME])
        zeit[0] += 1.0
        s.handle(ac.MSG_AUDIO, struct.pack(">Q", 1) + b"A")
        self.assertEqual(len(acc.out), n + 2)                                         # nicht öfter als alle 2 s
        zeit[0] += 1.5
        s.handle(ac.MSG_STATS, b"{}")
        self.assertEqual(len(acc.out), n + 4)
        # läuft das Bild, bleibt der Wächter still
        s2, acc2, fake2, opened2 = self._hallo(zeit)
        self._start(s2)
        m = len(acc2.out)
        for i in range(10):
            zeit[0] += 0.5
            s2.handle(ac.MSG_VIDEO, struct.pack(">BQ", 0, 2_000_000 + i * 500_000) + SC + b"\x02P")
            s2.handle(ac.MSG_AUDIO, struct.pack(">Q", 1) + b"A")
        self.assertEqual(len(acc2.out), m)

    def test_inband_modus_laesst_den_strom_offen(self):
        zeit = [10.0]
        s, acc, fake, opened = self._hallo(zeit, reconfig="inband")
        self._start(s)
        s.handle(ac.MSG_CONFIG, json.dumps(dict(json.loads(_config().decode()), w=1080, h=1920)).encode())
        self.assertIs(s.rtmp, fake)
        self.assertTrue(s.reconf)
        n = len(fake.sent)
        s.handle(ac.MSG_VIDEO_CSD, HEVC_CSD)
        s.handle(ac.MSG_VIDEO, struct.pack(">BQ", 1, 2_500_000) + SC + b"\x26K2")
        self.assertEqual([k for k, *_ in fake.sent[n:]], ["data", "video", "video"])      # Metadaten, Kopf, Schlüsselbild

    def test_codecwechsel_schliesst_den_strom_auch_im_inband_modus(self):
        zeit = [10.0]
        s, acc, fake, opened = self._hallo(zeit, reconfig="inband")
        self._start(s)
        s.handle(ac.MSG_CONFIG, _config(codec="avc"))
        self.assertIsNone(s.rtmp)
        self.assertIsNone(s.record)

    def test_ohne_ton_wird_kein_ton_gesendet(self):
        s, acc, fake = self._session(audio="none")
        s.handle(ac.MSG_CONFIG, _config(codec="avc"))
        s.handle(ac.MSG_VIDEO_CSD, AVC_CSD)
        s.handle(ac.MSG_AUDIO_CSD, b"\x11\x90")
        s.handle(ac.MSG_VIDEO, struct.pack(">BQ", 1, 1000) + SC + b"\x65K")
        s.handle(ac.MSG_AUDIO, struct.pack(">Q", 1000) + b"AAC")
        self.assertEqual([k for k, *_ in fake.sent], ["video", "video"])
        self.assertEqual(fake.sent[0][2][0], 0x17)                                  # H.264: Kennung 7

    def test_vendorliste_ohne_sticks(self):
        self.assertNotIn("0b05", ac.VENDORS)
        self.assertNotIn("0e8d", ac.VENDORS)
        self.assertIn("04e8", ac.VENDORS)
        hd = irl("hdmi_daemon")
        self.assertEqual(set(hd.ANDROID_VENDORS), ac.VENDORS)                      # Daemon und Hilfsprogramm kennen dieselben Hersteller

    def test_messwerte_der_app_werden_mitgeschrieben(self):
        s, acc, fake = self._session()
        zeilen = []
        orig = ac.say
        ac.say = zeilen.append
        try:
            s.handle(ac.MSG_CONFIG, json.dumps({"v": 1, "codec": "hevc", "w": 1920, "h": 1080, "fps": 60, "bitrate": 10_000_000, "ae": "60-60",
                                                "audio": {"codec": "aac", "rate": 48000, "ch": 2}}).encode())
            s.handle(ac.MSG_STATS, json.dumps({"cam": 50, "out": 49, "dropped": 3, "backlog": 1, "mbit": 7.5, "target": 10, "ae": "60-60"}).encode())
            s.handle(ac.MSG_STATS, b"kaputt")                                       # kein JSON: wird ignoriert
        finally:
            ac.say = orig
        self.assertTrue(any("AE) 60-60" in z for z in zeilen))
        self.assertTrue(any(z.startswith("info: App: Kamera 50/s, gesendet 49/s, verworfen 3") for z in zeilen))
        self.assertEqual(len([z for z in zeilen if "App: Kamera" in z]), 1)

    def test_bildzeile_passt_zum_daemon(self):
        s, acc, fake = self._session()
        zeilen = []
        orig = ac.say
        ac.say = zeilen.append
        try:
            s.handle(ac.MSG_CONFIG, _config())
        finally:
            ac.say = orig
        self.assertTrue(zeilen[0].startswith("Bild: 1920x1080 HEVC 30 fps"))
        self.assertIsNotNone(irl("hdmi_daemon").MOBCAM_FORMAT_RE.match(zeilen[0]))

    def test_handydaten_werden_geprueft_und_nur_selten_gemeldet(self):
        s, acc, fake = self._session()
        t = [100.0]
        s.clock = lambda: t[0]
        zeilen = []
        orig = ac.say
        ac.say = zeilen.append
        try:
            stat = lambda **k: s.handle(ac.MSG_STATS, json.dumps(dict({"cam": 30}, **k)).encode())
            stat()                                                                 # ältere App ohne Handydaten: keine Zeile
            stat(bat=97, chg=1, cur=312, temp=31.46, thermal=0)
            stat(bat=96, chg=1, cur=300, temp=31.5)                                 # gleich danach, Laden unverändert: keine neue Zeile
            t[0] += 1
            stat(bat=96, chg=0, cur=-150, temp=31.5)                                # Laden hat aufgehört: sofort melden
            t[0] += 3.5
            stat(bat=150, chg=1, cur=99999, temp="heiß", thermal=9)                 # Unsinn wird weggelassen, nur chg bleibt
            t[0] += 3.5
            stat(bat=True, temp=float("nan"))                                       # nichts Brauchbares: keine Zeile
            t[0] += 3.5
            stat(bat=92, chg=1, plug=1, cur_cal=0, temp=30.0)                       # Richtung noch nicht erkannt: cur fehlt, cur_cal=0 kommt mit
            t[0] += 3.5
            stat(bat=93, chg=1, plug=True, cur_cal=1, cur=300, temp=30.0, extra=5)  # erkannt; unbekannte Felder fallen weg
        finally:
            ac.say = orig
        z = [x for x in zeilen if x.startswith("Handy: ")]
        self.assertEqual([json.loads(x[7:]) for x in z], [
            {"bat": 97, "cur": 312, "temp": 31.5, "thermal": 0, "chg": 1},
            {"bat": 96, "cur": -150, "temp": 31.5, "chg": 0},
            {"chg": 1},
            {"bat": 92, "temp": 30.0, "chg": 1, "plug": 1, "cur_cal": 0},
            {"bat": 93, "cur": 300, "temp": 30.0, "chg": 1, "plug": 1, "cur_cal": 1}])
        self.assertTrue(irl("hdmi_daemon").PHONE_LINE_RE.match(z[0]))


def _adts(payload, sri=3, ch=2, profile=1):
    n = 7 + len(payload)
    return bytes([0xFF, 0xF1, (profile << 6) | (sri << 2) | (ch >> 2), ((ch & 3) << 6) | (n >> 11), (n >> 3) & 0xFF, ((n & 7) << 5) | 0x1F, 0xFC]) + payload


class TestUsbMikrofon(unittest.TestCase):
    """Ton vom USB-Mikrofon (DJI-Empfänger o. ä.) statt vom Handy: AAC von der Tonkarte, Zeitstempel auf der Zeitachse des Bilds, Ton-Versatz."""

    def setUp(self):
        self.hd = irl("hdmi_daemon")

    def _session(self, offset=0):
        args = types.SimpleNamespace(key="hdmi", rtmp_port=1935, rtmp_app="publish", audio="usb", dry=False, audio_offset=offset)
        s = ac.Session(FakeAcc(), args)
        s.m = mr
        s.rtmp = FakeRtmp()
        s.last = {"v": 1000, "a": 0}
        s.last_v_sent = 100.0
        return s

    def test_adts_wird_zerlegt_auch_in_stuecken(self):
        a, b, c = b"A" * 100, b"B" * 7, b"C" * 300
        strom = _adts(a) + _adts(b) + _adts(c)
        frames, rest = ac.adts_split(strom[:110])
        self.assertEqual([f[0] for f in frames], [a])
        self.assertTrue(rest)
        frames2, rest2 = ac.adts_split(rest + strom[110:])
        self.assertEqual([f[0] for f in frames2], [b, c])
        self.assertEqual(rest2, b"")
        self.assertEqual(frames[0][1], bytes([0x11, 0x90]))                           # AudioSpecificConfig AAC-LC, 48 kHz, Stereo
        self.assertEqual(frames[0][2], 48000)
        frames3, _ = ac.adts_split(b"\x00\xff\x12\x34" + _adts(a))                      # Müll vor dem Rahmen wird übersprungen
        self.assertEqual([f[0] for f in frames3], [a])

    def test_tonkarte_wird_gefunden(self):
        d = tempfile.mkdtemp()
        self.assertIsNone(ac.usb_capture_card(d))
        _write(os.path.join(d, "card0", "id"), "rockchipes8388")                      # eingebaut, kein USB
        os.makedirs(os.path.join(d, "card0", "pcm0c"))
        _write(os.path.join(d, "card1", "usbbus"), "007/002")                           # USB, aber nur Wiedergabe
        _write(os.path.join(d, "card1", "id"), "Spk")
        os.makedirs(os.path.join(d, "card1", "pcm0p"))
        self.assertIsNone(ac.usb_capture_card(d))
        _write(os.path.join(d, "card5", "usbbus"), "007/002")
        _write(os.path.join(d, "card5", "id"), "Rx")
        os.makedirs(os.path.join(d, "card5", "pcm0c"))
        self.assertEqual(ac.usb_capture_card(d), "plughw:CARD=Rx")
        _write(os.path.join(d, "card5", "id"), "böse; rm")                              # ungültige Kennung: nicht nehmen
        self.assertIsNone(ac.usb_capture_card(d))

    def test_aufruf_der_aufnahme(self):
        a = ac.usb_audio_argv("plughw:CARD=Rx")
        self.assertEqual(a[:4], ["gst-launch-1.0", "-q", "alsasrc", "device=plughw:CARD=Rx"])
        self.assertIn("voaacenc", a)
        self.assertIn("audio/mpeg,mpegversion=4,stream-format=adts", a)
        self.assertEqual(a[-2:], ["fdsink", "fd=1"])
        with self.assertRaises(ValueError):
            ac.usb_audio_argv("plughw:CARD=Rx; rm -rf /")

    def test_zeitstempel_folgen_dem_bild_mit_versatz(self):
        s = self._session(offset=50)
        s.on_mic_frame(b"r1", bytes([0x11, 0x90]), 48000, 100.5)                       # 0,5 s nach dem letzten Bild: 1000 + 500 + 50
        s.on_mic_frame(b"r2", bytes([0x11, 0x90]), 48000, 100.5213)
        s.on_mic_frame(b"r3", bytes([0x11, 0x90]), 48000, 100.5427)
        audio = [x for x in s.rtmp.sent if x[0] == "audio"]
        self.assertEqual(audio[0][2], mr.flv_audio(0, bytes([0x11, 0x90])))             # erst der Kopf der Tonspur
        self.assertEqual([x[1] for x in audio[1:]], [1550, 1571, 1592])                 # lückenlos, 1024 Abtastwerte = 21,3 ms
        self.assertEqual(audio[1][2], mr.flv_audio(1, b"r1"))
        s.on_mic_frame(b"r4", bytes([0x11, 0x90]), 48000, 101.5)                        # 1 s Sprung: neu ansetzen statt nachzuhinken
        self.assertEqual([x for x in s.rtmp.sent if x[0] == "audio"][-1][1], 2550)

    def test_negativer_versatz_und_nie_rueckwaerts(self):
        s = self._session(offset=-200)
        s.on_mic_frame(b"r", bytes([0x11, 0x90]), 48000, 100.5)
        self.assertEqual([x for x in s.rtmp.sent if x[0] == "audio"][-1][1], 1300)
        s.last["a"] = 5000
        s.on_mic_frame(b"r", bytes([0x11, 0x90]), 48000, 100.52)
        self.assertGreaterEqual([x for x in s.rtmp.sent if x[0] == "audio"][-1][1], 5000)

    def test_ohne_bild_oder_in_der_pause_kein_ton(self):
        s = self._session()
        s.last_v_sent = 0.0                                                             # noch kein Bild gesendet
        s.on_mic_frame(b"r", bytes([0x11, 0x90]), 48000, 100.5)
        s.last_v_sent = 100.0
        s.hold_until = 999.0                                                            # Pause nach Umstellung
        s.on_mic_frame(b"r", bytes([0x11, 0x90]), 48000, 100.5)
        s.hold_until = 0.0
        s.rtmp = None
        s.on_mic_frame(b"r", bytes([0x11, 0x90]), 48000, 100.5)                         # kein RTMP-Strom
        self.assertEqual(s.a_next, None)

    def test_handyton_wird_im_usb_modus_verworfen(self):
        s = self._session()
        s.cfg = json.loads(_config())
        s.acsd = b"\x11\x90"
        s.handle(ac.MSG_AUDIO, struct.pack(">Q", 1000) + b"phone")
        self.assertEqual([x for x in s.rtmp.sent if x[0] == "audio"], [])
        self.assertTrue(s.has_audio())                                                  # Metadaten kündigen die Tonspur trotzdem an

    def test_aufnahme_laeuft_weiter_nach_abziehen(self):
        d = tempfile.mkdtemp()
        _write(os.path.join(d, "card5", "usbbus"), "007/002")
        _write(os.path.join(d, "card5", "id"), "Rx")
        os.makedirs(os.path.join(d, "card5", "pcm0c"))
        import io
        got, starts = [], []

        class P:
            def __init__(self, data):
                self.stdout = io.BytesIO(data)

            def kill(self):
                pass

            def wait(self, timeout=None):
                pass
        sess = types.SimpleNamespace(closed=False, clock=lambda: 10.0, on_mic_frame=lambda raw, asc, rate, t: got.append((raw, asc, rate)))

        def spawn(argv, **kw):
            starts.append(argv)
            return P(_adts(b"x" * 40) + _adts(b"y" * 40))
        pausen = []

        def sleep(sec):
            pausen.append(sec)
            if len(starts) >= 2:
                sess.closed = True
        ac.UsbMic(sess, asound=d, spawn=spawn, sleep=sleep).run()
        self.assertEqual(len(starts), 2, "nach dem Abbruch (Ende der Daten) wird neu gestartet")
        self.assertEqual(len(got), 4)
        self.assertEqual(got[0], (b"x" * 40, bytes([0x11, 0x90]), 48000))
        self.assertEqual(starts[0][3], "device=plughw:CARD=Rx")

    def test_ohne_ton_sendet_stille(self):
        """„Ohne Ton“: die Box braucht eine Tonspur (sonst steht die Sendekette), also kommt Stille statt keinem Ton, und es wird keine Tonkarte gesucht."""
        import io
        got, starts = [], []

        class P:
            def __init__(self, data):
                self.stdout = io.BytesIO(data)

            def kill(self):
                pass

            def wait(self, timeout=None):
                pass
        sess = types.SimpleNamespace(closed=False, clock=lambda: 10.0, on_mic_frame=lambda raw, asc, rate, t: got.append(raw))

        def spawn(argv, **kw):
            starts.append(argv)
            return P(_adts(b"s" * 20))

        def sleep(sec):
            sess.closed = True
        ac.UsbMic(sess, asound="/gibt/es/nicht", spawn=spawn, sleep=sleep, silent=True).run()
        self.assertEqual(len(starts), 1)
        self.assertIn("audiotestsrc", starts[0])
        self.assertIn("wave=silence", starts[0])
        self.assertNotIn("alsasrc", starts[0])
        self.assertEqual(got, [b"s" * 20])
        self.assertTrue(ac.Session.has_audio(types.SimpleNamespace(args=types.SimpleNamespace(audio="none"), cfg={"audio": {"ch": 0}})))

    def test_ohne_tonkarte_wird_gewartet(self):
        d = tempfile.mkdtemp()
        sess = types.SimpleNamespace(closed=False, clock=lambda: 0.0, on_mic_frame=lambda *a: None)
        n = []

        def sleep(sec):
            n.append(sec)
            if len(n) >= 3:
                sess.closed = True
        ac.UsbMic(sess, asound=d, spawn=lambda *a, **k: self.fail("ohne Tonkarte darf nichts starten"), sleep=sleep).run()
        self.assertEqual(n, [2, 2, 2])

    def test_einstellung_ton_versatz(self):
        c = self.hd.clean_settings
        self.assertEqual(c({})["audio_offset_ms"], 0)
        self.assertEqual(c({"audio_offset_ms": -120})["audio_offset_ms"], -120)
        self.assertEqual(c({"audio_offset_ms": 1000})["audio_offset_ms"], 1000)
        for bad in (1001, -1001, 1.5, "5", True, None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                c({"audio_offset_ms": bad})

    def test_aufruf_helfer_mit_usb_ton(self):
        cfg = dict(self.hd.DEFAULTS, source="irlcam", audio="usb", audio_offset_ms=-120, key="hdmi")
        a = self.hd.irlcam_feeder_argv(cfg, 1935, "publish", helper="/opt/pipbox/android_cam.py")
        self.assertEqual(a[-4:], ["--audio", "usb", "--audio-offset", "-120"])
        self.assertEqual(self.hd.irlcam_feeder_argv(dict(cfg, audio="mobcam"))[-2:], ["--audio", "mobcam"])
        self.assertEqual(self.hd.irlcam_feeder_argv(dict(cfg, audio="none"))[-2:], ["--audio", "none"])
        self.assertEqual(self.hd.mobcam_feeder_argv(dict(cfg, source="mobcam"))[-2:], ["--audio", "mobcam"], "das iPhone-Hilfsprogramm kennt keinen USB-Ton")

    def test_umstellen_der_quelle_haelt_den_ton_passend(self):
        d = self.hd.Daemon(tempfile.mkdtemp(), device="/gibt/es/nicht")
        d.cfg = dict(d.cfg, source="hdmi", audio="usb")
        r = asyncio.run(d.handle({"cmd": "set", "settings": {"source": "irlcam"}}))
        self.assertEqual((r["settings"]["source"], r["settings"]["audio"]), ("irlcam", "usb"), "USB-Mikrofon gilt auch bei der IRL4YOU Cam")
        r = asyncio.run(d.handle({"cmd": "set", "settings": {"source": "mobcam"}}))
        self.assertEqual((r["settings"]["source"], r["settings"]["audio"]), ("mobcam", "mobcam"), "beim iPhone nicht möglich")
        d.cfg = dict(d.cfg, source="hdmi", audio="analog")
        r = asyncio.run(d.handle({"cmd": "set", "settings": {"source": "irlcam"}}))
        self.assertEqual(r["settings"]["audio"], "mobcam")

    def test_versatz_bei_hdmi_und_webcam(self):
        """Ton von der USB-Tonkarte: positiv = Ton wird gehalten, negativ = Bild wird gehalten; Ton der Kamera selbst bleibt unverändert."""
        hd = self.hd
        teile = lambda a: (a[2:a.index("alsasrc")], a[a.index("alsasrc"):a.index("flvmux")])
        for audio, off, v_erw, a_erw in (("usb", 200, False, True), ("usb", -150, True, False), ("usb", 0, False, False), ("hdmi", 200, False, False),
                                         ("analog", 300, False, True)):
            cfg = dict(hd.DEFAULTS, audio=audio, audio_offset_ms=off)
            a = hd.feeder_argv(cfg, extra_audio="plughw:CARD=Rx")
            v, au = teile(a)
            self.assertEqual(any(x.startswith("min-threshold-time=") for x in v), v_erw, (audio, off, "Bild"))
            self.assertEqual(any(x.startswith("min-threshold-time=") for x in au), a_erw, (audio, off, "Ton"))
        a = hd.feeder_argv(dict(hd.DEFAULTS, audio="usb", audio_offset_ms=200), extra_audio="plughw:CARD=Rx")
        self.assertIn("min-threshold-time=200000000", a)
        self.assertIn("max-size-time=1200000000", a)
        cand = ("mjpeg", 1280, 720, 30)
        u = hd.usb_feeder_argv(dict(hd.DEFAULTS, audio="usb", audio_offset_ms=-100), "/dev/video2", cand, "plughw:CARD=Rx")
        self.assertIn("min-threshold-time=100000000", u[:u.index("alsasrc")])
        self.assertFalse(any(x.startswith("min-threshold-time=") for x in u[u.index("alsasrc"):]))


class TestIrlcamOberflaeche(unittest.TestCase):
    def test_auswahl_und_texte_stehen_da(self):
        def lesen(*p):
            with open(os.path.join(ROOT, "irl4you", *p), encoding="utf-8") as f:
                return f.read()
        js = lesen("web", "neu", "views", "kameras.js")
        self.assertIn("['irlcam', 'IRL4YOU Cam (Android per USB)']", js)
        self.assertIn("Mikrofon des Handys", js)
        self.assertIn("Die App IRL4YOU Cam auf dem Android-Handy", js)
        self.assertIn("irlcam", lesen("web", "partials", "c_cams.html"))
        self.assertIn("Android-Handy nicht gefunden", lesen("web", "neu", "views", "live.js"))

    def test_handykachel_auf_der_live_seite(self):
        def lesen(*p):
            with open(os.path.join(ROOT, "irl4you", *p), encoding="utf-8") as f:
                return f.read()
        js = lesen("web", "neu", "views", "live.js")
        self.assertIn("phoneCard", js)
        self.assertIn("poll('hdmi', '/api/hdmi'", js)
        self.assertIn("data-phone-curve", js.replace("phoneCurve: ''", "data-phone-curve"))
        self.assertNotIn("Neu.t(", js)                                              # Übersetzung läuft über den Text selbst, nicht über eine Funktion
        for sprache in ("en", "ja", "ru"):
            d = json.loads(lesen("web", "i18n", sprache + ".json"))["exact"]
            for k in ("lädt nicht", "Akkuverlauf", "letzte {1}"):
                self.assertIn(k, d, sprache)

    def test_einzelbild_kette_versteht_h264_und_hevc(self):
        """Handy-Apps senden H.265: die Einzelbild-Kette (type single) darf nicht nur h264parse vor den Dekoder setzen (Encoder-Absturz)."""
        irl("hdmi_daemon")
        pipeline = irl("webui.pipeline")
        pl = irl("pipbox_live")
        store = pipeline.PipelineStore(os.path.join(tempfile.mkdtemp(), "pipeline.json"))
        cfg = dict(store.cfg, type="single", main="hdmi", pip="")
        for fix in (True, False):
            orig = pl.flvfix_ok
            pl.flvfix_ok = lambda fix=fix: fix
            try:
                text = store.build(cfg)
            finally:
                pl.flvfix_ok = orig
            self.assertIn("rtmp2src", text)
            self.assertNotIn("rtmpsrc", text)
            self.assertIn("rtmp://127.0.0.1:1935/publish/hdmi", text)
            self.assertIn("mppvideodec", text)
            self.assertIn("demux.audio", text)                                      # Ton hängt weiter am Demuxer "demux"
            if fix:
                self.assertIn("video/x-h264 ! h264parse", text)
                self.assertIn("video/x-h265 ! h265parse", text)
            else:
                self.assertIn("parsebin", text)
            self.assertNotIn("demux.video !\nqueue max-size-time=10000000000 max-size-buffers=1000 max-size-bytes=41943040 !\nh264parse ! mppvideodec", text)

    def test_webdienst_reicht_handydaten_durch(self):
        irl("hdmi_daemon")
        from webui import camservices
        svc = camservices.HdmiService(tempfile.mkdtemp(), None)
        antwort = {"state": "streaming", "settings": {}, "usb": {"present": True},
                   "phone": {"bat": 95, "chg": 1, "plug": 1, "cur_cal": 1, "cur": -308, "temp": 36.6, "thermal": 0, "boese": 1, "x": "text", "y": True}}
        svc._call = lambda req, timeout=4: antwort
        self.assertEqual(svc.status()["phone"], {"bat": 95, "chg": 1, "plug": 1, "cur_cal": 1, "cur": -308, "temp": 36.6, "thermal": 0})
        svc._hit = (0.0, None)
        antwort = {"state": "streaming", "settings": {}, "usb": {"present": True}}      # ohne Handydaten: kein Feld, keine Kachel
        self.assertNotIn("phone", svc.status())
        svc._hit = (0.0, None)
        antwort = {"state": "streaming", "settings": {}, "usb": {"present": True},
                   "phone": {"bat": 95, "hist": [[300, 96], [240, 96], "x", [1, 2, 3], ["a", 1], [0, 95]]}}
        self.assertEqual(svc.status()["phone"]["hist"], [[300, 96], [240, 96], [0, 95]])   # nur Zahlenpaare kommen durch

    def test_standardname_der_kamera(self):
        irl("hdmi_daemon")
        from webui import camservices
        self.assertEqual(camservices.HdmiService.IRLCAM_NAMES, ("IRL4YOU Cam", "IRL4YOU Cam 2"))
        self.assertIn("irl4you cam 3", camservices.HdmiService._auto_names(camservices.HdmiService))


class TestHochkantImLayout(unittest.TestCase):
    """Ein Hochkantbild darf beim Drehen nicht gedehnt werden, bevor die Aufteilung nachzieht."""

    def test_skalierung_haelt_das_seitenverhaeltnis(self):
        live = irl("pipbox_live")
        caps = live.scale_caps(1920, 1080)
        self.assertIn("pixel-aspect-ratio=1/1", caps)
        self.assertTrue(caps.startswith("video/x-raw,format=NV12,width=1920,height=1080"))
        with open(os.path.join(ROOT, "irl4you", "pipbox_live.py"), encoding="utf-8") as f:
            quelle = f.read()
        self.assertIn("{nm}_scc caps=\\\"video/x-raw,format=NV12,width={CANVAS_W},height={CANVAS_H},pixel-aspect-ratio=1/1", quelle)

    def test_hauptbild_hat_immer_die_volle_flaeche(self):
        """Das Einpassen übernimmt videoscale je Bild; die Größe aus dem Empfänger kommt erst später und darf das Bild nicht dehnen."""
        with open(os.path.join(ROOT, "irl4you", "pipbox_live.py"), encoding="utf-8") as f:
            quelle = f.read()
        self.assertNotIn("fit_big", quelle)
        self.assertEqual(quelle.count("x, y, w, h = 0, 0, CANVAS_W, CANVAS_H"), 2)
        self.assertEqual(quelle.count("rtmp2src name={nm}_src"), 2)               # nicht librtmp (stürzt beim Abschalten/Wechsel ab)
        self.assertNotIn("rtmpsrc name={nm}_src", quelle)


if __name__ == "__main__":
    unittest.main()
