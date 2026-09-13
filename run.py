#!/usr/bin/env python3
"""Run Loony to Westminster locally: starts the API + frontend and opens a browser."""
from __future__ import annotations

import threading
import webbrowser

import uvicorn

HOST = "127.0.0.1"
PORT = 2026


def _open_browser() -> None:
    webbrowser.open(f"http://{HOST}:{PORT}")


def main() -> None:
    print("=" * 62)
    print("  LOONY TO WESTMINSTER — a satirical democracy game")
    print("  For humour only. Not affiliated with any party or person.")
    print(f"  Serving on http://{HOST}:{PORT}  (Ctrl+C to stop)")
    print("=" * 62)
    threading.Timer(1.2, _open_browser).start()
    uvicorn.run("backend.main:app", host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
