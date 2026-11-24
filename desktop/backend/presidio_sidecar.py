"""Presidio as a separate program, for the packaged app.

The packaged backend has no Python to pip install into, so Presidio ships as an add-on the person downloads
from the app: this file frozen together with Presidio, spaCy and the ``en_core_web_sm`` model. The backend
starts it, sends it page text over 127.0.0.1, and gets back where the personal data is.

It listens only on the loopback address, on a random port, and needs a token that only the backend knows
(``SB_ADDON_TOKEN``). It writes the chosen port on its first output line, and quits after ``IDLE_SECONDS``
without a request so the language model does not sit in memory; the backend starts it again when needed.
"""
from __future__ import annotations

import hmac
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

IDLE_SECONDS = int(os.environ.get("SB_ADDON_IDLE", "600"))
MODEL = "en_core_web_sm"
MAX_BODY = 4_000_000
_engine = None
_lock = threading.Lock()
_last = time.monotonic()


def engine():
    global _engine
    with _lock:
        if _engine is None:
            import logging
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider
            logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)
            nlp = NlpEngineProvider(nlp_configuration={
                "nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": MODEL}]}).create_engine()
            _engine = AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])
        return _engine


class Handler(BaseHTTPRequestHandler):
    token = ""

    def log_message(self, *args):          # keep page text and addresses out of any log
        pass

    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _allowed(self) -> bool:
        return hmac.compare_digest(self.headers.get("X-Addon-Token", ""), self.token)

    def do_GET(self):
        global _last
        if not self._allowed():
            return self._send(401, {"error": "unauthorized"})
        _last = time.monotonic()
        if self.path == "/health":
            return self._send(200, {"status": "ok", "model": MODEL})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        global _last
        if not self._allowed():
            return self._send(401, {"error": "unauthorized"})
        if self.path != "/analyze":
            return self._send(404, {"error": "not found"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > MAX_BODY:
                return self._send(413, {"error": "text too long"})
            body = json.loads(self.rfile.read(size) or b"{}")
            text = str(body.get("text", ""))
            entities = [str(e) for e in body.get("entities") or []] or None
            found = engine().analyze(text=text, language="en", entities=entities,
                                     score_threshold=float(body.get("threshold", 0.4)))
            _last = time.monotonic()
            self._send(200, {"results": [{"entity_type": r.entity_type, "start": r.start, "end": r.end,
                                          "score": float(r.score)} for r in found]})
        except Exception as exc:           # a bad request must not kill the program
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"[:300]})


def main() -> None:
    token = os.environ.get("SB_ADDON_TOKEN", "")
    if len(token) < 16:
        sys.exit("SB_ADDON_TOKEN is required")
    Handler.token = token
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    print(server.server_address[1], flush=True)           # the backend reads the port from this line

    def watchdog() -> None:
        while True:
            time.sleep(5)
            if time.monotonic() - _last > IDLE_SECONDS or os.getppid() == 1:      # idle, or the backend is gone
                os._exit(0)
    threading.Thread(target=watchdog, daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
