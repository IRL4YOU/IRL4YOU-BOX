"""IRL4YOU BOX Oberfläche: HTTP-Handler der Oberfläche (setzt die Teile zusammen)."""

from .common import ttl_cached
from .http_base import HttpBase
from .http_stats import HttpStats
from .routes_get import GetRoutes
from .routes_post import PostRoutes


class Handler(HttpBase, HttpStats, GetRoutes, PostRoutes):
    # Teile der Oberfläche; main() setzt sie vor dem Start
    sampler = None
    cams = None
    auth = None
    djisvc = None
    netchoice = None
    names = None
    ckeys = None
    srtla = None
    pipeline = None
    send = None
    preview = None
    twitch = None
    hdmi = None
    uiaccess = None
    statsshare = None
    statsserver = None
    fpsprobe = None
    uplinktest = None

    @classmethod
    def hotspot_ifaces(cls):
        """Karten, auf denen gerade der Hotspot der Box läuft (dort ergibt ein Leitungstest keinen Sinn)."""
        if not getattr(cls, "wifi", None):
            return set()
        try:
            return set(ttl_cached("hotspot_ifaces", 10.0, lambda: {c["iface"] for c in cls.wifi.cards() if c.get("hotspot_running")}) or ())
        except Exception:
            return set()
