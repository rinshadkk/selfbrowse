"""Serve this folder and log each request with the host name it used, so a test can tell a trap fetched on the
forbidden name (localhost) from the same page fetched on the allowed one (127.0.0.1).

    python3 serve.py [port] [folder]        # default: 8000, this folder
"""
import functools
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
folder = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f'{self.command} {self.path} host={self.headers.get("Host", "?").split(":")[0]}', flush=True)


ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Handler, directory=str(folder))).serve_forever()
