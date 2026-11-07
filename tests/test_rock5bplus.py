"""ROCK 5B+: Takt ohne Deckel, Firmware-Werkzeug, Lüfter, RTMPS-Zertifikat, Image-Bau."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL = os.path.join(ROOT, "irl4you", "install")
CPUCAP = os.path.join(INSTALL, "cpucap", "irl4you-cpucap.sh")
BOOT = os.path.join(INSTALL, "bootloader")
BOOTTOOL = os.path.join(BOOT, "irl4you-bootloader.sh")
FAN = os.path.join(INSTALL, "fan")
CERT = os.path.join(INSTALL, "rtmps")


def _text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestSkripte(unittest.TestCase):
    SH = [CPUCAP, BOOTTOOL, os.path.join(CERT, "irl4you-rtmps-cert.sh"), os.path.join(INSTALL, "system-base-fixes.sh")]
    BASH = [os.path.join(FAN, "rock5bplus-fan-kupfer.sh"), os.path.join(FAN, "rock5bplus-fan-alu.sh")]

    def test_lf_und_syntax(self):
        for shell, files in (("sh", self.SH), ("bash", self.BASH)):
            exe = shutil.which(shell)
            for p in files:
                self.assertNotIn(b"\r\n", open(p, "rb").read(), "CRLF in " + p)
                if exe:
                    r = subprocess.run([exe, "-n", p], capture_output=True, text=True)
                    self.assertEqual(r.returncode, 0, p + ": " + r.stderr)

    def test_einheiten(self):
        for p in (os.path.join(FAN, "rock5bplus-fan.service"), os.path.join(CERT, "irl4you-rtmps-cert.service")):
            t = _text(p)
            for part in ("[Unit]", "[Service]", "[Install]", "ExecStart="):
                self.assertIn(part, t, p)
        self.assertIn("ConditionPathExists=/sys/devices/platform/pwm-fan", _text(os.path.join(FAN, "rock5bplus-fan.service")))
        self.assertIn("ConditionPathExists=!/etc/nginx/certs/rtmps/privkey.pem", _text(os.path.join(CERT, "irl4you-rtmps-cert.service")))
        self.assertIn("Before=nginx.service", _text(os.path.join(CERT, "irl4you-rtmps-cert.service")))

    def test_installer_richtet_alles_ein(self):
        t = _text(os.path.join(INSTALL, "system-base-fixes.sh"))
        for part in ("fan/rock5bplus-fan.service", "rock5bplus-fan-kupfer.sh", "rtmps/irl4you-rtmps-cert.service",
                     "cp -R \"$HERE/bootloader/rock-5b-plus\""):
            self.assertIn(part, t)

    def test_fan_kurve_kupfer_standard(self):
        t = _text(os.path.join(INSTALL, "system-base-fixes.sh"))
        self.assertIn("ln -s /usr/share/irl4you/fan/rock5bplus-fan-kupfer.sh /usr/local/bin/rock5bplus-fan.sh", t)
        for f, on in (("rock5bplus-fan-kupfer.sh", "ON_MC=52000"), ("rock5bplus-fan-alu.sh", "ON_MC=48000")):
            self.assertIn(on, _text(os.path.join(FAN, f)))
            self.assertIn("MIN_PWM=182", _text(os.path.join(FAN, f)), "darunter steht der Lüfter der ROCK 5B+ auf Kernel 6.1 (170 und 178 stehen, 180 grenzwertig)")


class TestTakt(unittest.TestCase):
    def _dry(self, model):
        with tempfile.TemporaryDirectory() as d:
            mf = os.path.join(d, "model")
            with open(mf, "wb") as f:
                f.write(model.encode() + b"\0")
            env = dict(os.environ, MODEL_FILE=mf, CPUCAP_DRYRUN="1")
            r = subprocess.run(["sh", CPUCAP], capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            return dict(x.split("=") for x in r.stdout.split())

    @unittest.skipIf(os.path.exists("/etc/irl4you/cpucap.conf"), "cpucap.conf der Box würde die Prüfung verändern")
    def test_rock_kein_deckel(self):
        for name in ("Radxa ROCK 5B+", "Radxa ROCK 5B Plus"):
            v = self._dry(name)
            self.assertEqual((v["BIG_MAX_KHZ"], v["BIG_SW_MAX_KHZ"], v["DMC_MAX_HZ"]), ("0", "0", "0"), name)

    @unittest.skipIf(os.path.exists("/etc/irl4you/cpucap.conf"), "cpucap.conf der Box würde die Prüfung verändern")
    def test_orange_pi_unveraendert(self):
        v = self._dry("Orange Pi 5 Plus")
        self.assertEqual(v["BIG_MAX_KHZ"], "1416000")


@unittest.skipUnless(sys.platform == "linux", "dd, stat und sha256sum wie unter Linux")
class TestFirmwareWerkzeug(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        tool = os.path.join(self.tmp, "tool")
        os.makedirs(os.path.join(tool, "rock-5b-plus", "armbian"))
        shutil.copy(BOOTTOOL, tool)
        self.region = os.urandom(512 * 40)
        with open(os.path.join(tool, "rock-5b-plus", "armbian", "region.bin"), "wb") as f:
            f.write(self.region)
        self.dev = os.path.join(self.tmp, "dev.img")
        with open(self.dev, "wb") as f:
            f.write(b"\0" * (1 << 20))
        self.model = os.path.join(self.tmp, "model")
        with open(self.model, "wb") as f:
            f.write(b"Radxa ROCK 5B+\0")
        self.script = os.path.join(tool, "irl4you-bootloader.sh")
        self.env = dict(os.environ, DEV=self.dev, MODEL_FILE=self.model, DEV_TEST="1", BK=os.path.join(self.tmp, "bk"))

    def run_tool(self, *args):
        return subprocess.run(["sh", self.script, *args], capture_output=True, text=True, env=self.env)

    def test_status_apply_status(self):
        r = self.run_tool("status")
        self.assertTrue(r.stdout.startswith("unbekannt"), r.stdout + r.stderr)
        r = self.run_tool("apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(self.dev, "rb") as f:
            f.seek(64 * 512)
            self.assertEqual(f.read(len(self.region)), self.region)
            f.seek(0)
            self.assertEqual(f.read(64 * 512), b"\0" * (64 * 512), "Sektor 0 bis 63 bleiben unberührt")
        self.assertTrue(self.run_tool("status").stdout.startswith("aktiv: rock-5b-plus-armbian"))
        self.assertIn("schon aktiv", self.run_tool("apply").stdout)
        self.assertEqual(len(os.listdir(os.path.join(self.tmp, "bk"))), 1, "Sicherung des Ist-Stands")
        self.assertEqual(os.path.getsize(self.dev), 1 << 20, "Gerät bleibt gleich groß")

    def test_unbekanntes_board(self):
        with open(self.model, "wb") as f:
            f.write(b"Raspberry Pi 5\0")
        r = self.run_tool("status")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nicht unterstützt", r.stdout)

    def test_stand_ist_mitgeliefert(self):
        p = os.path.join(BOOT, "rock-5b-plus", "armbian", "region.bin")
        self.assertTrue(os.path.getsize(p) > (1 << 20) and os.path.getsize(p) % 512 == 0)
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(p), "QUELLE.md")))
        with open(p, "rb") as f:
            self.assertEqual(f.read(4), b"RKNS", "Rockchip-Kopf des Startabbilds")


class TestLueftertakt(unittest.TestCase):
    def test_pwm_periode_im_boot_hook(self):
        t = _text(os.path.join(INSTALL, "zz-irl4you-boot"))
        self.assertIn("rk3588-rock-5b-plus.dtb", t)
        self.assertIn('fdtput -t x "$f" /pwm-fan pwms "$1" "$2" c350 "$4"', t)
        self.assertTrue(t.rstrip().endswith("exit 0"))
        sh = shutil.which("sh")
        if sh:
            r = subprocess.run([sh, "-n", os.path.join(INSTALL, "zz-irl4you-boot")], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)


class TestImageBau(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(os.path.join(ROOT, "build", "12-box-image.sh")), "Die Skripte zum Image-Bau liegen nicht im Repository")
    def test_rock_vorgaben(self):
        d = open(os.path.join(ROOT, "build", "12-box-image.sh"), "rb").read()
        self.assertIn(b"rock-5b-plus/armbian/region.bin", d)
        self.assertIn(b"FDT /boot/dtb/rockchip/rk3588-rock-5b-plus.dtb", d)

    @unittest.skipUnless(os.path.exists(os.path.join(ROOT, "build", "12-box-image.sh")), "Die Skripte zum Image-Bau liegen nicht im Repository")
    def test_erststart_vergroessert_karte(self):
        scrub = open(os.path.join(ROOT, "build", "12-box-image-scrub.sh"), "rb").read()
        self.assertIn(b"ExecStart=-/usr/libexec/irl4you/grow-rootfs.sh", scrub)
        self.assertIn(b"After=local-fs.target", scrub)
        fixes = open(os.path.join(INSTALL, "system-base-fixes.sh"), "rb").read()
        self.assertIn(b'install -D -m 755 "$HERE/grow-rootfs.sh" /usr/libexec/irl4you/grow-rootfs.sh', fixes)

    def test_wlan_aspm_aus_nur_rock(self):
        fixes = open(os.path.join(INSTALL, "system-base-fixes.sh"), encoding="utf-8").read()
        i = fixes.index("options rtw89_pci disable_clkreq=Y disable_aspm_l1=Y disable_aspm_l1ss=Y")
        # liegt im ROCK-Zweig (nach der Modellprüfung, vor dem Ende des case-Blocks)
        self.assertLess(fixes.rindex("ROCK 5B+", 0, i), i)
        self.assertLess(i, fixes.index("esac", i))

    @unittest.skipUnless(os.path.exists(os.path.join(ROOT, "build", "12-box-image.sh")), "Die Skripte zum Image-Bau liegen nicht im Repository")
    def test_image_ohne_geraetekennungen(self):
        scrub = open(os.path.join(ROOT, "build", "12-box-image-scrub.sh"), "rb").read()
        self.assertIn(b'etc/systemd/network/10-irl4you-*.link', scrub)
        self.assertIn(b'etc/.resolv.conf*.bak', scrub)
        self.assertIn(b'var/lib/systemd/rfkill/*', scrub)
        bau = open(os.path.join(ROOT, "build", "12-box-image.sh"), "rb").read()
        self.assertIn(b'tune2fs -O ^has_journal', bau)
        self.assertIn(b'.nullfill', bau)
        # Journal und Nullen kommen nach dem Aushängen, vor dem Packen
        self.assertLess(bau.index(b'sync; umount "$M"'), bau.index(b'tune2fs -O ^has_journal'))
        self.assertLess(bau.index(b'tune2fs -O ^has_journal'), bau.index(b'Packen (.img.zip)'))
        sh = shutil.which("bash")
        if sh:
            for f in ("12-box-image.sh", "12-box-image-scrub.sh"):
                r = subprocess.run([sh, "-n", os.path.join(ROOT, "build", f)], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_luefter_nur_auf_der_rock(self):
        svc = _text(os.path.join(FAN, "rock5bplus-fan.service"))
        self.assertIn('ExecCondition=/bin/grep -a -q -F -e "ROCK 5B+" -e "ROCK 5B Plus" /proc/device-tree/model', svc)
        for f in ("rock5bplus-fan-kupfer.sh", "rock5bplus-fan-alu.sh"):
            skript = os.path.join(FAN, f)
            self.assertIn('Keine ROCK 5B+', _text(skript))
            with tempfile.TemporaryDirectory() as d:
                for modell, soll_start in (("Orange Pi 5 Plus", False), ("Radxa ROCK 5B+", True), ("Radxa ROCK 5B Plus", True)):
                    mf = os.path.join(d, "model")
                    with open(mf, "wb") as fh:
                        fh.write(modell.encode() + b"\0")
                    r = subprocess.run(["bash", skript], env=dict(os.environ, MODEL_FILE=mf), capture_output=True, text=True, timeout=20)
                    if soll_start:
                        # läuft auf der ROCK weiter bis zur Suche nach dem Lüfter (hier nicht vorhanden) und meldet das
                        self.assertIn("Luefter nicht eindeutig gefunden", r.stderr, (f, modell, r.stderr))
                    else:
                        self.assertEqual(r.returncode, 0, (f, modell, r.stderr))
                        self.assertIn("Keine ROCK 5B+", r.stderr)
                        self.assertNotIn("Luefter nicht eindeutig", r.stderr)

    def test_boards_getrennt(self):
        fixes = _text(os.path.join(INSTALL, "system-base-fixes.sh"))
        # Firmware-Dateien: nur die ROCK bekommt ihren Ordner, andere Boards keine, alte Orange-Pi-Dateien werden entfernt
        i = fixes.index('cp -R "$HERE/bootloader/rock-5b-plus"')
        self.assertLess(fixes.rindex('*"ROCK 5B+"*', 0, i), i)
        self.assertLess(i, fixes.index("esac", i))
        self.assertNotIn('bootloader/*.bin', fixes)
        self.assertIn('rm -f /usr/share/irl4you/bootloader/fit-opi5plus-*.bin', fixes)
        # andere Boards: ROCK-Lüfter und ASPM-Datei werden entfernt, nie gesetzt
        self.assertIn("rm -f /etc/modprobe.d/irl4you-rtw89.conf ;;", fixes)
        self.assertIn("systemctl disable --now rock5bplus-fan.service", fixes)


if __name__ == "__main__":
    unittest.main()
