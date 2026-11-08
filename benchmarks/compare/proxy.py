"""
A logging proxy in front of Ollama. Every library talks to this instead of Ollama, so token counts are
measured the same way for all of them, whatever each library reports about itself.

For each model call it records:
  sent_tokens   estimated tokens in everything sent (messages + tool schemas + response-format schema),
                counted with one tokenizer (tiktoken o200k_base) for every library
  prompt_eval / eval_count   what Ollama reports (prompt_eval can exclude prompt-cache hits)
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import tiktoken

ENC = tiktoken.get_encoding("o200k_base")
UPSTREAM = "http://127.0.0.1:11434"
ANTHROPIC_UPSTREAM = "https://api.anthropic.com"


class Recorder:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.lock = threading.Lock()

    def reset(self) -> None:
        with self.lock:
            self.calls = []

    def snapshot(self) -> list[dict]:
        with self.lock:
            return list(self.calls)


REC = Recorder()


def _sent_tokens(body: dict) -> int:
    parts = [body.get("messages"), body.get("tools"), body.get("format"), body.get("response_format"), body.get("system")]
    return len(ENC.encode(json.dumps([p for p in parts if p], ensure_ascii=False), disallowed_special=()))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _forward(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        t0 = time.perf_counter()
        upstream = ANTHROPIC_UPSTREAM if self.path.startswith("/v1/messages") else UPSTREAM
        req = urllib.request.Request(upstream + self.path, data=raw or None, method=self.command,
                                     headers={k: v for k, v in self.headers.items()
                                              if k.lower() not in ("host", "content-length", "accept-encoding")})
        try:
            with urllib.request.urlopen(req, timeout=900) as resp:
                out, status, ctype = resp.read(), resp.status, resp.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            out, status, ctype = e.read(), e.code, "application/json"
        secs = time.perf_counter() - t0
        if self.command == "POST" and ("chat" in self.path or "generate" in self.path or self.path.startswith("/v1/messages")):
            rec = {"path": self.path, "seconds": round(secs, 3), "status": status}
            try:
                body = json.loads(raw)
                rec["sent_tokens"] = _sent_tokens(body)
                last = json.loads(out.decode().strip().splitlines()[-1])
                if self.path.startswith("/v1/messages"):               # Anthropic: input_tokens excludes cache
                    u = last.get("usage", {})
                    rec["cache_read"] = u.get("cache_read_input_tokens") or 0
                    rec["prompt_eval"] = (u.get("input_tokens") or 0) + rec["cache_read"] + (u.get("cache_creation_input_tokens") or 0)
                    rec["eval_count"] = u.get("output_tokens")
                elif "usage" in last:                                 # OpenAI-compatible
                    rec["prompt_eval"], rec["eval_count"] = last["usage"].get("prompt_tokens"), last["usage"].get("completion_tokens")
                else:                                                  # native
                    rec["prompt_eval"], rec["eval_count"] = last.get("prompt_eval_count"), last.get("eval_count")
            except Exception as exc:
                rec["parse_error"] = str(exc)[:100]
            with REC.lock:
                REC.calls.append(rec)
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    do_GET = do_POST = _forward


def serve(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"
