#!/usr/bin/env python3
"""Serve the built site locally at the same path it is served from in production.

Pages link to /meditation/… because that is where the site lives on the live
domain, so serving the repo root at / breaks every stylesheet and link. This
mounts the repo under the real base path instead.

    python3 scripts/serve.py          # http://localhost:8000/meditation/
    python3 scripts/serve.py --port 9000
"""

import argparse
import functools
import http.server
import socketserver
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from render import BASE_PATH


class BasePathHandler(http.server.SimpleHTTPRequestHandler):
    """Strip the site's base path, and serve directories as index.html."""

    def translate_path(self, path):
        if BASE_PATH != "/" and path.startswith(BASE_PATH.rstrip("/")):
            path = path[len(BASE_PATH.rstrip("/")):] or "/"
        return super().translate_path(path)

    def end_headers(self):
        # No caching, so an edit-and-rebuild is visible on refresh.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        if not args or "200" not in str(args):
            super().log_message(fmt, *args)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    handler = functools.partial(BasePathHandler, directory=str(config.SITE_ROOT))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", args.port), handler) as httpd:
        print(f"Serving {config.SITE_ROOT} at "
              f"http://localhost:{args.port}{BASE_PATH}  (ctrl-c to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
