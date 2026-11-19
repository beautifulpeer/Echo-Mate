#!/usr/bin/env python3
import io
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

BOARD_IP = os.environ.get("BOARD_IP", "192.168.31.58")
BOARD_PORT = os.environ.get("BOARD_PORT", "22")
BOARD_KEY = os.environ.get("BOARD_KEY", os.path.expanduser("~/.ssh/id_ed25519_rv1106"))
WIDTH = 320
HEIGHT = 240
FRAME_BYTES = WIDTH * HEIGHT * 2

latest_jpeg = None
frame_lock = threading.Lock()


def rgb565_to_jpeg(raw):
    # Linux framebuffer is little-endian RGB565. Pillow's raw decoder converts it directly.
    image = Image.frombytes("RGB", (WIDTH, HEIGHT), raw, "raw", "BGR;16")
    out = io.BytesIO()
    image.save(out, "JPEG", quality=82)
    return out.getvalue()


def capture_loop():
    global latest_jpeg
    command = [
        "ssh", "-p", BOARD_PORT, "-i", BOARD_KEY,
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=5",
        "-o", "ServerAliveInterval=5",
        "-o", "StrictHostKeyChecking=no",
        f"root@{BOARD_IP}",
        "while true; do dd if=/dev/fb0 bs=153600 count=1 2>/dev/null; sleep 0.08; done",
    ]
    while True:
        proc = None
        try:
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, bufsize=FRAME_BYTES * 2)
            while True:
                raw = proc.stdout.read(FRAME_BYTES)
                if len(raw) != FRAME_BYTES:
                    break
                jpeg = rgb565_to_jpeg(raw)
                with frame_lock:
                    latest_jpeg = jpeg
        except Exception as exc:
            print(f"capture error: {exc}", flush=True)
        finally:
            if proc:
                proc.kill()
        time.sleep(2)


PAGE = """<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>
<title>Echo-Mate YOLO</title><style>
body{margin:0;background:#111;color:#eee;font-family:sans-serif;text-align:center}
h2{margin:18px 0 8px}.wrap{display:inline-block;background:#222;padding:12px;border-radius:12px}
img{width:min(92vw,960px);height:auto;image-rendering:auto;border-radius:6px}
p{color:#aaa;margin:9px}
</style></head><body><h2>Echo-Mate YOLO 实时画面</h2>
<div class='wrap'><img src='/stream.mjpg' alt='YOLO stream'></div>
<p>请在开发板上打开 YOLO 页面；本页会同步显示开发板屏幕。</p></body></html>""".encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)
            return
        if self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                while True:
                    with frame_lock:
                        frame = latest_jpeg
                    if frame:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " +
                                         str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
                    time.sleep(0.1)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        self.send_error(404)

    def log_message(self, fmt, *args):
        print(f"{self.client_address[0]} - {fmt % args}", flush=True)


if __name__ == "__main__":
    threading.Thread(target=capture_loop, daemon=True).start()
    print("YOLO web viewer: http://0.0.0.0:8001", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8001), Handler).serve_forever()
