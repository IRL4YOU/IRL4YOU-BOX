"""Link with "via": the data goes to a relay (helper phone) instead of the receiver, the relay passes it on."""
import signal
import socket
import threading
import time
import unittest

from test_protocol import Base, setUpModule  # noqa: F401  (setUpModule baut das Programm)


class Relay:
    """Like the helper phone: takes packets only from one source address, forwards them to the target, brings answers back."""

    def __init__(self, allowed_ip):
        self.allowed_ip = allowed_ip
        self.down = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.down.bind(("127.0.0.1", 0))
        self.down.settimeout(0.2)
        self.port = self.down.getsockname()[1]
        self.up = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.up.bind(("127.0.0.1", 0))
        self.up.settimeout(0.2)
        self.target = None
        self.client = None
        self.to_target = 0
        self.to_client = 0
        self.wrong_source = 0
        self.running = True
        for fn in (self._down_loop, self._up_loop):
            threading.Thread(target=fn, daemon=True).start()

    def _down_loop(self):
        while self.running:
            try:
                buf, addr = self.down.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            if addr[0] != self.allowed_ip:
                self.wrong_source += 1
                continue
            self.client = addr
            if self.target:
                self.up.sendto(buf, self.target)
                self.to_target += 1

    def _up_loop(self):
        while self.running:
            try:
                buf, _ = self.up.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            if self.client:
                self.down.sendto(buf, self.client)
                self.to_client += 1

    def close(self):
        self.running = False
        time.sleep(0.3)
        self.down.close()
        self.up.close()


class TestVia(Base):
    def relay(self, ip):
        r = Relay(ip)
        self.addCleanup(r.close)
        return r

    def test_link_via_relay_joins_and_carries_data(self):
        relay = self.relay("127.0.0.2")
        r = self.rig([f"127.0.0.2 via 127.0.0.1:{relay.port}", "127.0.0.3"], "-m", "all")
        relay.target = ("127.0.0.1", r.rx.port)
        r.wait_up(["127.0.0.2", "127.0.0.3"])
        self.assertEqual(r.link("127.0.0.2")["via"], f"127.0.0.1:{relay.port}")
        self.assertNotIn("via", r.link("127.0.0.3"))
        self.assertEqual(r.rx.group_count(), 1)
        r.stream(1000, 2000)
        got = r.drain_server(1.5)
        self.assertEqual(sorted(set(got)), list(range(1000, 3000)))
        self.assertGreater(relay.to_target, 100)
        self.assertGreater(relay.to_client, 0)
        self.assertEqual(relay.wrong_source, 0)

    def test_device_and_via_in_one_line(self):
        relay = self.relay("127.0.0.2")
        r = self.rig([f"127.0.0.2 lo via 127.0.0.1:{relay.port}"])
        relay.target = ("127.0.0.1", r.rx.port)
        r.wait_up(["127.0.0.2"])
        self.assertEqual(r.link("127.0.0.2")["dev"], "lo")

    def test_same_address_direct_and_via_are_two_links(self):
        relay = self.relay("127.0.0.2")
        r = self.rig(["127.0.0.2", f"127.0.0.2 via 127.0.0.1:{relay.port}"], "-m", "all")
        relay.target = ("127.0.0.1", r.rx.port)
        r.wait(lambda: len((r.status() or {}).get("links", [])) == 2 and
               all(l["state"] in ("used", "reserve") for l in r.status()["links"]), msg="zwei Leitungen")

    def test_changed_via_replaces_link(self):
        relay1 = self.relay("127.0.0.2")
        relay2 = self.relay("127.0.0.2")
        r = self.rig([f"127.0.0.2 via 127.0.0.1:{relay1.port}"])
        relay1.target = relay2.target = ("127.0.0.1", r.rx.port)
        r.wait_up(["127.0.0.2"])
        r.write_links([f"127.0.0.2 via 127.0.0.1:{relay2.port}"])
        r.proc.send_signal(signal.SIGHUP)
        r.wait(lambda: (r.link("127.0.0.2") or {}).get("via") == f"127.0.0.1:{relay2.port}", msg="neues Ziel")
        r.wait_up(["127.0.0.2"])
        r.stream(1, 200)
        r.drain_server(1.0)
        self.assertGreater(relay2.to_target, 50)

    def test_relay_gone_link_drops_and_comes_back(self):
        relay = self.relay("127.0.0.2")
        r = self.rig([f"127.0.0.2 via 127.0.0.1:{relay.port}", "127.0.0.3"])
        relay.target = ("127.0.0.1", r.rx.port)
        r.wait_up(["127.0.0.2", "127.0.0.3"])
        relay.target = None  # Hilfshandy schickt nichts mehr weiter
        r.wait(lambda: r.link("127.0.0.2")["state"] not in ("used", "reserve"), timeout=10, msg="Leitung getrennt")
        relay.target = ("127.0.0.1", r.rx.port)
        r.wait_up(["127.0.0.2"], timeout=12)
        r.stream(1, 200)
        self.assertEqual(len(set(r.drain_server(1.0))), 200)

    def test_bad_via_line_is_ignored(self):
        r = self.rig(["127.0.0.2 via", "127.0.0.2 via nicht-ip:5", "127.0.0.2 via 127.0.0.1:0", "127.0.0.3"])
        r.wait_up(["127.0.0.3"])
        self.assertEqual([l["ip"] for l in r.status()["links"]], ["127.0.0.3"])
        self.assertGreaterEqual(len(r.events("warn")), 3)


if __name__ == "__main__":
    unittest.main()
