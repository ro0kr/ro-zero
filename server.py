"""Local preview for shattered Noto Sans. Seed is the character code."""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent / "sources"))

from svg_pattern import DEFAULT_PIECES, DEFAULT_ROUGHNESS, DEFAULT_WHITE_RATIO, char_seed
from type_shatter import FONT_SIZE, WEIGHTS, black900_radius, render_weight_svg

HOST = "127.0.0.1"
PORT = 48721
ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
DOWNLOADS = ROOT / "downloads"
FONT_FILE = DOWNLOADS / "ro-zero.ttf"
PREVIEW_FONT = DOWNLOADS / "ro-zero-preview.ttf"
STATUS_FILE = DOWNLOADS / "ro-zero.status.json"
_weight_cache: dict[int, bytes] = {}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/font-status":
            if STATUS_FILE.exists():
                self._send(200, STATUS_FILE.read_bytes(), "application/json; charset=utf-8")
            else:
                body = json.dumps({"state": "missing"}).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            return
        if path in ("/download/ro-zero-100-900.zip",):
            zip_path = DOWNLOADS / "ro-zero-100-900.zip"
            if not zip_path.exists():
                self._send(404, b"Zip is still building", "text/plain; charset=utf-8")
                return
            data = zip_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", 'attachment; filename="ro-zero-100-900.zip"')
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if path in ("/download/ro-zero.ttf", "/fonts/ro-zero.ttf", "/fonts/ro-zero-preview.ttf"):
            source = PREVIEW_FONT if path.endswith("preview.ttf") else FONT_FILE
            if not source.exists():
                self._send(404, b"Font is still building", "text/plain; charset=utf-8")
                return
            data = source.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "font/ttf")
            self.send_header("Content-Length", str(len(data)))
            if path.startswith("/download/"):
                self.send_header("Content-Disposition", 'attachment; filename="ro-zero.ttf"')
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/meta":
            payload = {
                "pieces": DEFAULT_PIECES,
                "white_ratio": DEFAULT_WHITE_RATIO,
                "roughness": DEFAULT_ROUGHNESS,
                "radius": round(black900_radius(FONT_SIZE), 3),
                "seed_rule": "ord(char)",
                "example": {"가": char_seed("가"), "a": char_seed("a"), "1": char_seed("1")},
                "weights": list(WEIGHTS),
            }
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        if path.startswith("/weight/") and path.endswith(".svg"):
            try:
                weight = int(path.removeprefix("/weight/").removesuffix(".svg"))
            except ValueError:
                self._send(404, b"Not found", "text/plain; charset=utf-8")
                return
            if weight not in WEIGHTS:
                self._send(404, b"Not found", "text/plain; charset=utf-8")
                return
            if weight not in _weight_cache:
                _weight_cache[weight] = render_weight_svg(weight).encode("utf-8")
            self._send(200, _weight_cache[weight], "image/svg+xml; charset=utf-8")
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        print(f"[{self.log_date_time_string()}] {format % args}")


def main() -> None:
    print(f"Preview: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
