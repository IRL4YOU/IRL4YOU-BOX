"""pipbox-link: Hilfshandy-Protokoll (Cam Link) gegen ein nachgebautes Hilfshandy, alles auf diesem Rechner."""
import hashlib
import hmac
import importlib.util
import json
import os
import socket
import struct
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "irl4you", "pipbox-link.py")


def load(tmp, port):
    os.environ["IRL4YOU_LINK_CONF"] = os.path.join(tmp, "link.json")
    os.environ["IRL4YOU_LINK_SRTLA"] = os.path.join(tmp, "srtla.json")
    os.environ["IRL4YOU_LINK_RUN"] = os.path.join(tmp, "run")
    os.environ["IRL4YOU_LINK_PORT"] = str(port)
    os.environ["IRL4YOU_LINK_FAKE_IFACE"] = "t0=127.0.0.1"
    spec = importlib.util.spec_from_file_location("pipbox_link_test", SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class FakePhone:
    """Gegenstelle wie die App: HELLO -> CHALLENGE, OPEN prüfen -> OK/ERR, PING -> PONG."""

    def __init__(self, password="geheim", battery=77, mobile=True):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.1)
        self.port = self.sock.getsockname()[1]
        self.password, self.battery, self.mobile = password, battery, mobile
        self.ident = b"\x01\x02\x03\x04\x05\x06\x07\x08"
        self.salts = {}
        self.opens = []
        self.pings = 0
        self.answer_pings = True
        self.error = None            # Fehlercode, den das Hilfshandy statt OK schickt
        self.session = 0x12345678
        self.data_port = 45678
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _send(self, kind, payload, to):
        self.sock.sendto(b"I4YL" + bytes([1, kind]) + payload, to)

    def _loop(self):
        while self.running:
            try:
                buf, addr = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                return
            if buf[:4] != b"I4YL" or buf[4] != 1:
                continue
            kind, data = buf[5], buf[6:]
            if kind == 1:
                salt = os.urandom(16)
                self.salts[addr] = salt
                self._send(2, salt + self.ident, addr)
            elif kind == 3:
                salt = self.salts.pop(addr, None)
                s, port, n = data[:16], *struct.unpack(">HB", data[16:19])
                host = data[19:19 + n]
                given = data[19 + n:19 + n + 32]
                want = hmac.new(self.password.encode() or b"\0", b"I4YL-open" + s + struct.pack(">H", port) + host,
                                hashlib.sha256).digest()
                if salt != s:
                    continue
                self.opens.append((host.decode(), port))
                if not hmac.compare_digest(want, given):
                    self._send(5, bytes([1]), addr)
                elif self.error:
                    self._send(5, bytes([self.error]), addr)
                else:
                    self._send(4, struct.pack(">HI", self.data_port, self.session), addr)
            elif kind == 6:
                self.pings += 1
                if self.answer_pings:
                    self._send(7, struct.pack(">IBBQQ", self.session, self.battery, int(self.mobile), 5_000_000, 2_000_000), addr)

    def close(self):
        self.running = False
        time.sleep(0.2)
        self.sock.close()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="link-test-")
        self.phone = FakePhone()
        self.addCleanup(self.phone.close)
        self.m = load(self.tmp, self.phone.port)
        self.m.HELLO_SEARCH_S = 0.2
        self.m.PING_EVERY_S = 0.2
        self.m.LOST_AFTER_S = 1.2
        self.m.OPEN_TIMEOUT_S = 1.0
        self.m.RETRY_AFTER_ERR_S = 1.0
        self.m.CONF_EVERY_S = 0.05
        self.lk = self.m.Linker()
        self.addCleanup(self.lk.close_all)
        self.write_srtla()
        self.write_conf(enabled=True)

    def write_srtla(self, host="srtla.example.net", port=5000):
        with open(os.path.join(self.tmp, "srtla.json"), "w") as f:
            json.dump({"servers": [{"id": "a", "host": host, "port": port}], "selected": "a"}, f)

    def write_conf(self, **kw):
        c = {"enabled": True, "password": "geheim", "iface": "", "hosts": ["127.0.0.1"]}
        c.update(kw)
        with open(os.path.join(self.tmp, "link.json"), "w") as f:
            json.dump(c, f)

    def run_for(self, seconds, until=None):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.lk.step(timeout=0.05)
            if until and until():
                return True
        return until() if until else None

    def status(self):
        with open(os.path.join(self.tmp, "run", "status.json")) as f:
            return json.load(f)

    def links(self):
        try:
            with open(os.path.join(self.tmp, "run", "links")) as f:
                return f.read().split("\n")[:-1]
        except FileNotFoundError:
            return []


class TestProtocol(unittest.TestCase):
    def test_mac_known_answer(self):
        m = load(tempfile.mkdtemp(), 8390)
        salt = bytes(range(16))
        want = hmac.new(b"pw", b"I4YL-open" + salt + b"\x13\x88" + b"example.net", hashlib.sha256).digest()
        self.assertEqual(m.mac("pw", salt, "example.net", 5000), want)

    def test_empty_password_uses_zero_byte(self):
        m = load(tempfile.mkdtemp(), 8390)
        salt = bytes(16)
        want = hmac.new(b"\0", b"I4YL-open" + salt + b"\x00\x50" + b"1.2.3.4", hashlib.sha256).digest()
        self.assertEqual(m.mac("", salt, "1.2.3.4", 80), want)

    def test_open_layout(self):
        m = load(tempfile.mkdtemp(), 8390)
        msg = m.open_message("x", bytes(16), "ab.de", 99)
        self.assertEqual(msg[:6], b"I4YL\x01\x03")
        self.assertEqual(msg[6:22], bytes(16))
        self.assertEqual(msg[22:25], b"\x00\x63\x05")
        self.assertEqual(msg[25:30], b"ab.de")
        self.assertEqual(len(msg), 6 + 16 + 3 + 5 + 32)

    def test_foreign_packets_are_ignored(self):
        m = load(tempfile.mkdtemp(), 8390)
        self.assertIsNone(m.parse(b"hello"))
        self.assertIsNone(m.parse(b"I4YL\x02\x01"))
        self.assertEqual(m.parse(b"I4YL\x01\x01"), (1, b""))


class TestSession(Base):
    def test_connects_and_writes_link_line(self):
        self.assertTrue(self.run_for(3, lambda: self.links()))
        self.assertEqual(self.links(), [f"127.0.0.1 via 127.0.0.1:{self.phone.data_port}"])
        self.assertEqual(self.phone.opens[0], ("srtla.example.net", 5000))
        st = self.run_for(1, lambda: self.status()["helpers"] and self.status()["helpers"][0].get("battery") == 77) and self.status()
        h = st["helpers"][0]
        self.assertEqual((h["state"], h["battery"], h["mobile"]), ("up", 77, True))
        self.assertEqual((h["mb_up"], h["mb_down"]), (5.0, 2.0))
        self.assertFalse(st["searching"])

    def test_pings_keep_the_session_open(self):
        self.run_for(3, lambda: self.links())
        self.run_for(2.5)
        self.assertEqual(len(self.links()), 1)
        self.assertGreaterEqual(self.phone.pings, 5)
        self.assertEqual(len(self.phone.opens), 1)

    def test_lost_helper_is_removed_and_found_again(self):
        self.run_for(3, lambda: self.links())
        self.phone.answer_pings = False
        self.assertTrue(self.run_for(4, lambda: not self.links()))
        self.phone.answer_pings = True
        self.assertTrue(self.run_for(4, lambda: self.links()))
        self.assertGreaterEqual(len(self.phone.opens), 2)

    def test_wrong_password_shows_error_and_no_link(self):
        self.write_conf(password="falsch")
        self.assertTrue(self.run_for(3, lambda: self.status()["helpers"] and self.status()["helpers"][0]["state"] == "error"))
        self.assertEqual(self.status()["helpers"][0]["error"], "password")
        self.assertEqual(self.links(), [])

    def test_error_codes_of_the_phone(self):
        self.phone.error = 2
        self.assertTrue(self.run_for(3, lambda: self.status()["helpers"] and self.status()["helpers"][0].get("error") == "no_mobile"))
        self.assertEqual(self.links(), [])

    def test_retries_after_error(self):
        self.phone.error = 4
        self.run_for(2, lambda: self.status()["helpers"] and self.status()["helpers"][0].get("error") == "busy")
        self.phone.error = None
        self.assertTrue(self.run_for(5, lambda: self.links()))

    def test_disabled_closes_everything(self):
        self.run_for(3, lambda: self.links())
        self.write_conf(enabled=False)
        self.assertTrue(self.run_for(2, lambda: not self.links() and not self.lk.socks))
        st = self.status()
        self.assertEqual((st["enabled"], st["helpers"]), (False, []))
        pings = self.phone.pings
        self.run_for(0.8)
        self.assertEqual(self.phone.pings, pings)

    def test_no_server_selected_no_open(self):
        os.unlink(os.path.join(self.tmp, "srtla.json"))
        self.run_for(1.5)
        self.assertEqual(self.phone.opens, [])
        self.assertFalse(self.status()["target"])

    def test_new_server_is_used_on_next_open(self):
        self.run_for(3, lambda: self.links())
        self.write_srtla("neu.example.org", 7000)
        self.phone.answer_pings = False
        self.run_for(4, lambda: not self.links())
        self.phone.answer_pings = True
        self.run_for(4, lambda: self.links())
        self.assertEqual(self.phone.opens[-1], ("neu.example.org", 7000))

    def test_clean_end_removes_links(self):
        self.run_for(3, lambda: self.links())
        self.lk.close_all()
        self.lk.remove_links()
        self.assertEqual(self.links(), [])


if __name__ == "__main__":
    unittest.main()
