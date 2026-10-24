#!/usr/bin/env python3
"""
Portable app launcher.

Serves a bundled ``app/`` folder over HTTP on a free 127.0.0.1 port, opens the
user's default browser at it, and keeps running until the console window is
closed (or Ctrl+C is pressed).

When frozen by PyInstaller (``--onefile``) the bundled data is unpacked to a
temporary directory exposed as ``sys._MEIPASS``; we resolve ``app/`` from there.
When run as a plain script we fall back to the directory containing this file.
"""

import functools
import os
import socket
import sys
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


def resource_dir() -> str:
    """Directory that holds the bundled ``app/`` folder."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = os.path.join(resource_dir(), "app")


def free_port() -> int:
    """Ask the OS for an unused TCP port on the loopback interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class QuietHandler(SimpleHTTPRequestHandler):
    """Static handler that stays quiet and disables caching."""

    def log_message(self, fmt, *args):  # noqa: D401 - silence request logging
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> int:
    # Python BLOCK-buffers stdout when it is not a terminal, so when this is run
    # with its output redirected (`./app-linux > run.log &`) the banner - including
    # the URL - sat in the buffer and never appeared. Anything that supervises this
    # binary (a smoke test, a wrapper script, a log) was blind to it. Line-buffer.
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass
    if not os.path.isdir(APP_DIR):
        print("ERROR: bundled 'app' folder not found at:", APP_DIR, flush=True)
        try:
            input("Press Enter to exit...")
        except EOFError:
            pass
        return 1

    port = free_port()
    url = "http://127.0.0.1:{}/".format(port)

    handler = functools.partial(QuietHandler, directory=APP_DIR)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)

    print("=" * 60, flush=True)
    print(" Serving :", APP_DIR)
    print(" URL     :", url, flush=True)
    print(" The app should open in your browser automatically.")
    print(" Close this window (or press Ctrl+C) to stop the server.")
    print("=" * 60)

    # Give the server a moment to be ready, then open the browser.
    threading.Timer(0.7, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
