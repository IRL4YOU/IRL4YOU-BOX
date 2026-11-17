"""IRL4YOU BOX Oberfläche: Handys als zusätzliche Sendewege (Dienst pipbox-link, App "IRL4YOU Stream Link")."""

import json
import os
import re

from .common import iface_ips

IFACE_RE = re.compile(r"^[A-Za-z0-9_.:-]{0,15}$")
MAX_PASSWORD = 64
MAX_HELPERS = 8                  # so viele Handys zeigt die Oberfläche (der Dienst pipbox-link hat dieselbe Grenze)


class LinkStore:
    STATUS = "/run/pipbox-link/status.json"

    def __init__(self, state_dir, demo=False):
        self.path = os.path.join(state_dir, "link.json")
        self.demo = demo
        self.names = None           # DeviceNames: eigene Namen der Handys (wird von main gesetzt)
        self.data = {"enabled": False, "password": "", "iface": ""}
        try:
            with open(self.path) as f:
                d = json.load(f)
            if isinstance(d, dict):
                self.data["enabled"] = d.get("enabled") is True
                self.data["password"] = d["password"][:MAX_PASSWORD] if isinstance(d.get("password"), str) else ""
                self.data["iface"] = d["iface"] if isinstance(d.get("iface"), str) and IFACE_RE.match(d["iface"]) else ""
        except (OSError, ValueError):
            pass

    def _live(self):
        try:
            with open(self.STATUS) as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def status(self):
        if self.demo:
            live = {"helpers": [{"id": "0102030405060708", "ip": "192.168.1.50", "iface": "eth0", "state": "up", "battery": 81, "charging": True,
                                 "mobile": True, "mb_up": 12.3, "mb_down": 1.2},
                                {"id": "1112131415161718", "ip": "192.168.1.51", "iface": "eth0", "state": "up", "battery": 47, "charging": False,
                                 "mobile": True, "mb_up": 8.1, "mb_down": 0.9}] if self.data["enabled"] else [],
                    "target": True, "searching": False}
            service = True
        else:
            live = self._live()
            service = bool(live)
        helpers = [dict(h) for h in live.get("helpers", []) if isinstance(h, dict)][:MAX_HELPERS]
        own = self.names.link_names() if self.names else {}
        for h in helpers:
            if own.get(str(h.get("id"))):
                h["name"] = own[str(h.get("id"))]
        return {**self.data, "service": service, "target": live.get("target", True) is not False,
                "searching": live.get("searching") is True, "helpers": helpers,
                "interfaces": [{"iface": o["iface"], "label": o["label"]} for o in iface_ips()]}

    def put(self, d):
        if not isinstance(d, dict):
            raise ValueError("Ungültige Anfrage")
        new = dict(self.data)
        if "enabled" in d:
            if not isinstance(d["enabled"], bool):
                raise ValueError("enabled muss wahr oder falsch sein")
            new["enabled"] = d["enabled"]
        if "password" in d:
            if not isinstance(d["password"], str) or len(d["password"]) > MAX_PASSWORD:
                raise ValueError(f"Das Passwort darf höchstens {MAX_PASSWORD} Zeichen haben")
            new["password"] = d["password"]
        if "iface" in d:
            if not isinstance(d["iface"], str) or not IFACE_RE.match(d["iface"]):
                raise ValueError("Ungültige Netzwerkkarte")
            new["iface"] = d["iface"]
        self.data = new
        if not self.demo:
            tmp = f"{self.path}.tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(new, f)
            os.replace(tmp, self.path)
        return self.status()
