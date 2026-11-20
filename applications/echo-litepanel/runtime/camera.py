"""Serve the latest hardware JPEG using LitePanel's fixed HTTP interfaces."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time


class Camera:
    def __init__(self, path='/tmp/echo-litepanel/frame.jpg'):
        self.path = Path(path)
        self.error = 'camera_starting'
        self.streams = threading.BoundedSemaphore(2)

    def snapshot(self):
        with self.path.open('rb') as stream:
            import os
            stat = os.fstat(stream.fileno())
            if time.time() - stat.st_mtime >= 3:
                raise ValueError('camera_frame_stale')
            jpeg = stream.read(512 * 1024 + 1)
        if len(jpeg) > 512 * 1024 or not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
            raise ValueError('camera_invalid_jpeg')
        return jpeg, stat

    def status(self):
        try:
            _, stat = self.snapshot()
            return dict(ready=True, width=480, height=272,
                        sequence=(stat.st_mtime_ns // 1000000) & 0xffffffff,
                        age_ms=max(0, int((time.time() - stat.st_mtime) * 1000)), error='',
                        snapshot='/snapshot.jpg', stream_port=9003)
        except (OSError, ValueError) as error:
            return dict(ready=False, width=480, height=272, sequence=0, age_ms=-1,
                        error=self.error or str(error), snapshot='/snapshot.jpg', stream_port=9003)

    def start_http(self, host='0.0.0.0', ports=(9002, 9003)):
        camera = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def setup(self):
                super().setup()
                self.connection.settimeout(3)

            def reply(self, body, content_type, code=200):
                self.send_response(code)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = self.path.split('?', 1)[0]
                if path == '/api/camera':
                    self.reply(json.dumps(camera.status()).encode(), 'application/json')
                elif path == '/':
                    self.reply(b'<html><img src="/stream"><p>Echo-Mate LitePanel camera</p></html>', 'text/html')
                elif path in ('/snapshot.jpg', '/stream'):
                    try:
                        jpeg, _ = camera.snapshot()
                    except (OSError, ValueError) as error:
                        self.reply(str(error).encode(), 'text/plain', 503)
                        return
                    if path == '/snapshot.jpg':
                        self.reply(jpeg, 'image/jpeg')
                        return
                    if not camera.streams.acquire(blocking=False):
                        self.reply(b'camera_stream_limit', 'text/plain', 503)
                        return
                    try:
                        self.send_response(200)
                        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
                        self.send_header('Cache-Control', 'no-store')
                        self.end_headers()
                        while True:
                            self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '
                                             + str(len(jpeg)).encode() + b'\r\n\r\n' + jpeg + b'\r\n')
                            self.wfile.flush()
                            time.sleep(.2)
                            jpeg, _ = camera.snapshot()
                    except (OSError, ValueError):
                        pass
                    finally:
                        camera.streams.release()
                else:
                    self.reply(b'not_found', 'text/plain', 404)

        servers = []
        try:
            for port in ports:
                server = ThreadingHTTPServer((host, port), Handler)
                server.daemon_threads = True
                threading.Thread(target=server.serve_forever, daemon=True).start()
                servers.append(server)
        except OSError:
            for server in servers:
                server.shutdown()
                server.server_close()
            raise
        return servers
