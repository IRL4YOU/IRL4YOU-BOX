#!/usr/bin/env python3
"""Mobcam-Einspeisung: ein iPhone (Moblin) liefert per USB-Kabel Bild und Ton und wird als Kamera in den RTMP-Eingang der Box gespeist.

Ablauf: mobcam-virtualcam (Schreiber) schreibt in ein v4l2loopback-Gerät "Mobcam". Dort darf genau ein Leser hängen, und der muss gleich nach dem
ersten Bild anhängen, sonst bricht der Schreiber ab. Dieses Programm startet den Schreiber, hängt sofort v4l2-ctl als einzigen Leser an und gibt
die Bilder mit gleichmäßiger Bildrate an GStreamer weiter (Hardware-Kodierer). Der Ton kommt aus der virtuellen Soundkarte "Loopback"."""
import argparse
import fcntl
import os
import re
import signal
import struct
import subprocess
import sys
import threading
import time

MOBCAM_BIN = "/usr/local/bin/mobcam-virtualcam"
SYS_V4L = "/sys/class/video4linux"
CARD = "Mobcam"
WAIT = "Warte auf Moblin"
STALL = 8.0
VIDIOC_QUERYCAP = 0x80685600
VIDIOC_G_FMT = 0xC0D05604
V4L2_CAP_VIDEO_CAPTURE = 0x1
FOURCC_I420 = 0x32315559  # YU12 / I420
KEEP = ("error", "warning: ")
procs = []
stopping = False


def say(text):
    sys.stderr.write(text + "\n")
    sys.stderr.flush()


def find_node(sysfs=SYS_V4L):
    try:
        names = sorted(os.listdir(sysfs), key=lambda n: (len(n), n))
    except OSError:
        return None
    for n in names:
        if re.match(r"^video\d{1,3}$", n):
            try:
                with open(os.path.join(sysfs, n, "name")) as f:
                    if f.read().strip() == CARD:
                        return "/dev/" + n
            except OSError:
                pass
    return None


def capture_format(node):
    """(Breite, Höhe) wenn das Gerät Bilder liefern kann (der Schreiber hat das Format gesetzt), sonst None."""
    try:
        fd = os.open(node, os.O_RDWR | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        cap = bytearray(104)
        fcntl.ioctl(fd, VIDIOC_QUERYCAP, cap)
        if not struct.unpack_from("<I", cap, 88)[0] & V4L2_CAP_VIDEO_CAPTURE:
            return None
        fmt = bytearray(208)
        struct.pack_into("<I", fmt, 0, 1)
        fcntl.ioctl(fd, VIDIOC_G_FMT, fmt)
        w, h, pix = struct.unpack_from("<III", fmt, 8)
        if pix != FOURCC_I420 or not w or not h:
            return None
        return w, h
    except OSError:
        return None
    finally:
        os.close(fd)


def gst_argv(a, w, h):
    v = ["fdsrc", "fd=0", "blocksize=%d" % (w * h * 3 // 2), "!", "rawvideoparse", "format=i420", "width=%d" % w, "height=%d" % h, "framerate=%d/1" % a.fps, "!",
         "queue", "max-size-buffers=4", "!", "mpph264enc", "bps=%d" % (a.bitrate * 1000), "gop=%d" % a.fps, "!", "h264parse", "config-interval=-1", "!", "queue", "!", "mux."]
    if a.audio == "mobcam":
        au = ["alsasrc", "device=plughw:CARD=Loopback,DEV=1", "provide-clock=false", "slave-method=resample", "!", "audioconvert", "!", "audioresample", "!",
              "audio/x-raw,rate=48000,channels=2", "!", "voaacenc", "bitrate=128000", "!", "aacparse", "!", "queue", "!", "mux."]
    else:
        au = ["audiotestsrc", "wave=silence", "is-live=true", "!", "audio/x-raw,rate=48000,channels=2", "!", "voaacenc", "bitrate=128000", "!", "aacparse", "!", "queue", "!", "mux."]
    sink = ["flvmux", "name=mux", "streamable=true", "!", "rtmpsink", "location=rtmp://127.0.0.1:%d/%s/%s" % (a.rtmp_port, a.rtmp_app, a.key)]
    return ["gst-launch-1.0", "-q"] + v + au + sink


def forward_errors(pipe):
    for raw in iter(pipe.readline, b""):
        line = raw.decode("utf-8", "replace").strip()
        if line.startswith(KEEP):
            say(line)


def kill_all(*_):
    global stopping
    stopping = True
    for p in procs:
        try:
            if p.poll() is None:
                p.terminate()
        except OSError:
            pass
    deadline = time.time() + 3
    for p in procs:
        try:
            p.wait(max(0.1, deadline - time.time()))
        except Exception:
            try:
                p.kill()
            except OSError:
                pass


def die(code, text):
    say(text)
    kill_all()
    sys.exit(code)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bitrate", type=int, required=True)
    ap.add_argument("--fps", type=int, choices=(25, 30, 50, 60), required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--rtmp-port", type=int, required=True)
    ap.add_argument("--rtmp-app", required=True)
    ap.add_argument("--audio", choices=("mobcam", "none"), default="mobcam")
    a = ap.parse_args()
    if not re.match(r"^[a-z0-9][a-z0-9_-]{0,31}$", a.key) or not re.match(r"^[a-z0-9_]{1,20}$", a.rtmp_app):
        die(2, "Ungültige Einstellung")
    signal.signal(signal.SIGTERM, lambda *_: (kill_all(), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda *_: (kill_all(), sys.exit(0)))
    if not os.path.exists(MOBCAM_BIN):
        die(3, "Mobcam ist nicht eingerichtet (sudo bash /opt/pipbox/install/mobcam/mobcam-setup.sh)")
    subprocess.run(["modprobe", "-q", "v4l2loopback"], check=False)
    subprocess.run(["modprobe", "-q", "snd-aloop"], check=False)
    node = find_node()
    if node is None:
        die(3, "Die virtuelle Kamera „Mobcam“ fehlt (Kernelmodul v4l2loopback)")
    subprocess.run(["pkill", "-x", "mobcam-virtualc"], check=False)
    writer = subprocess.Popen([MOBCAM_BIN, "--audio-backend", "alsa", "--device", node], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    procs.append(writer)
    threading.Thread(target=forward_errors, args=(writer.stderr,), daemon=True).start()
    say(WAIT)
    size = None
    while size is None:
        if writer.poll() is not None:
            die(4, "mobcam-virtualcam wurde beendet")
        size = capture_format(node)
        if size is None:
            time.sleep(0.005)
    w, h = size
    reader = subprocess.Popen(["v4l2-ctl", "-d", node, "--stream-mmap=4", "--stream-to=-"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
    procs.append(reader)
    frame = w * h * 3 // 2
    say("Moblin verbunden: %dx%d" % (w, h))
    gst = subprocess.Popen(gst_argv(a, w, h), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    procs.append(gst)
    threading.Thread(target=forward_errors, args=(gst.stderr,), daemon=True).start()
    try:
        fcntl.fcntl(gst.stdin.fileno(), 1031, 4 * 1024 * 1024)  # F_SETPIPE_SZ
    except OSError:
        pass
    latest = {"data": None, "at": time.monotonic(), "seq": 0}
    lock = threading.Lock()
    end = threading.Event()

    def read_frames():
        buf = bytearray()
        fd = reader.stdout.fileno()
        try:
            while not end.is_set():
                chunk = os.read(fd, 1 << 20)
                if not chunk:
                    break
                buf += chunk
                while len(buf) >= frame:
                    data = bytes(buf[:frame])
                    del buf[:frame]
                    with lock:
                        latest["data"], latest["at"] = data, time.monotonic()
                        latest["seq"] += 1
        finally:
            end.set()

    threading.Thread(target=read_frames, daemon=True).start()
    step = 1.0 / a.fps
    nxt = time.monotonic()
    try:
        while not end.is_set():
            now = time.monotonic()
            if now < nxt:
                time.sleep(nxt - now)
            nxt += step
            if nxt < time.monotonic() - 1:
                nxt = time.monotonic()
            with lock:
                data, at = latest["data"], latest["at"]
            if data is None:
                continue
            if time.monotonic() - at > STALL:
                die(5, "Moblin sendet nicht mehr")
            if gst.poll() is not None or writer.poll() is not None:
                break
            try:
                gst.stdin.write(data)
            except (BrokenPipeError, OSError):
                break
    finally:
        pass
    code = 6
    if writer.poll() is not None:
        say("mobcam-virtualcam wurde beendet")
    elif gst.poll() is not None:
        say("Der Hardware-Kodierer wurde beendet")
    else:
        say("Der Bildstrom vom iPhone ist abgerissen")
    kill_all()
    sys.exit(code)


if __name__ == "__main__":
    main()
