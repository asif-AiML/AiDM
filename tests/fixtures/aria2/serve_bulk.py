"""Throttled loopback fixtures for manual M18 checks; no internet or disk inputs.

Run from the repository: python3 tests/fixtures/aria2/serve_bulk.py
Paste the printed URLs into AiDM, choose a fresh destination, then either mode.
Content-Disposition supplies runtime names different from the URL filenames.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import re
import time
from urllib.parse import urlsplit


class BulkHandler(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *args):
        pass

    def respond(self, body):
        url = urlsplit(self.path)
        match = re.fullmatch(r'/([1-6])\.bin', url.path)
        if match is None:
            self.send_error(404)
            return
        index = int(match[1])
        size = index * 524288
        unknown = url.query == 'unknown=1'
        start = 0
        byte_range = self.headers.get('Range')
        if byte_range:
            match = re.fullmatch(r'bytes=(\d+)-(\d*)', byte_range)
            if match:
                start = int(match[1])
            if start >= size:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.end_headers()
                return
        self.send_response(206 if start else 200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Disposition', f'attachment; filename="runtime-{index}.bin"')
        self.send_header('Accept-Ranges', 'bytes')
        if not unknown:
            self.send_header('Content-Length', str(size - start))
        if start:
            self.send_header('Content-Range', f'bytes {start}-{size-1}/{size}')
        self.end_headers()
        if body:
            self.requests.append((url.path, start))
            try:
                for offset in range(start, size, 16384):
                    self.wfile.write(b'x' * min(16384, size - offset))
                    self.wfile.flush()
                    time.sleep(.1)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Expected when testing Abort.

    def do_HEAD(self):
        self.respond(False)

    def do_GET(self):
        self.respond(True)


if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', 8765), BulkHandler)
    print(' '.join(f'http://127.0.0.1:8765/{i}.bin' for i in range(1, 5)), flush=True)
    print('Optional: add /5.bin and /6.bin; use /4.bin?unknown=1 for unknown size.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
