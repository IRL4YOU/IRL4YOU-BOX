#!/usr/bin/env python3
import fcntl
import json
import os
import subprocess
import sys
import time

REQ = "/var/lib/pipbox/send-request"
UPDATE_STATUS = "/run/pipbox-swupdate/status.json"
UPDATE_LOCK = "/var/lib/irl4you/update.lock"
UPDATE_MAX_AGE = 30 * 60          # ein "installing" ohne Lebenszeichen seit so langer Zeit gilt als übrig geblieben (Absturz)


def update_installing():
    """Zweite Sicherung neben der Oberfläche: Während ein Software-Update installiert wird, startet hier keine Sendung."""
    try:
        with open(UPDATE_STATUS) as f:
            d = json.load(f)
        if d.get("state") != "installing":
            return False
        alive = lock_alive()
        if alive is not None:                      # der Installer hält die Sperre, solange er lebt
            return alive
        return time.time() - float(d.get("time", 0)) < UPDATE_MAX_AGE
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def lock_alive():
    """True: der Installer lebt, False: nicht, None: nicht prüfbar."""
    try:
        fd = os.open(UPDATE_LOCK, os.O_RDONLY)
    except FileNotFoundError:
        return False
    except OSError:
        return None
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    except OSError:
        return True
    finally:
        os.close(fd)


def main():
    try:
        with open(REQ) as f:
            mode = f.readline().strip()
    except OSError:
        return 0
    try:
        os.remove(REQ)
    except OSError:
        pass
    if mode in ("start", "restart") and update_installing():
        print(f"send-ctl: {mode} verworfen, es wird gerade ein Software-Update installiert", flush=True)
    elif mode == "start":
        subprocess.run(["systemctl", "start", "--no-block", "pipbox-send.service"])
    elif mode == "restart":
        subprocess.run(["systemctl", "restart", "--no-block", "pipbox-send.service"])
    elif mode == "stop":
        subprocess.run(["systemctl", "stop", "pipbox-send.service"])
    else:
        print(f"send-ctl: unbekannte Anforderung verworfen: {mode[:20]!r}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
