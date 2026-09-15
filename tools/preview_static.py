"""Serve the pure client-side build (frontend/) without the FastAPI server.

With no /api endpoints available, the app auto-detects the absence of a server
and runs 100% in the browser — exactly like the itch.io build. Saves go to your
browser's localStorage, not to saves/.

Usage:
    python tools/preview_static.py [port]     # default port: 8090
"""
import http.server
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend"))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8090


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def translate_path(self, path):
        # /static/... is the canonical prefix inside the app; serve frontend/ at both / and /static/
        if path.startswith("/static/"):
            path = path[len("/static"):]
        return super().translate_path(path)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")  # always fresh while iterating on the UI
        super().end_headers()


if __name__ == "__main__":
    print(f"Client-only build: http://localhost:{PORT}   (no server — the game runs in your browser)")
    print("Ctrl+C to stop")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
