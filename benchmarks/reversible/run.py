"""Does a local model use redaction placeholders correctly?

For each trial the model must copy the account email and holder name from a profile page into a
newsletter form. The page shows real personal data; the model is only ever sent placeholders.

Checks, per trial:
  filled      the form on the page received the REAL email and name (not a placeholder, not blank)
  leaked      the real email or name appears anywhere in the text sent to the model
Usage:
  python benchmarks/reversible/run.py --model ollama:qwen3.6-bench --trials 5 [--mode reversible|masked|both]
"""
import argparse
import functools
import json
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from selfbrowse import BrowseAgent, Browser
from selfbrowse.guardrails import PresidioRedact, RedactPII

ROOT = Path(__file__).resolve().parents[2]
REAL_EMAIL, REAL_NAME = "priya.raman@acme.com", "Priya Raman"
TASK = ("This is an account page. Subscribe the account's own email address to the newsletter: type the email on file "
        "into 'Newsletter email', type the account holder's name into 'Your name', and click Subscribe. "
        "Then call done with what you submitted.")


def serve():
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(ROOT / "tests" / "fixtures"))
    handler.log_message = lambda *a, **k: None
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}/profile.html"


def trial(model, url, mode, home):
    sent: list[str] = []
    guards = [RedactPII(restore=(mode == "reversible")), PresidioRedact(restore=(mode == "reversible"))]
    t0 = time.time()
    with Browser() as b:
        b.goto(url)
        agent = BrowseAgent(TASK, llm=model, browser=b, learn=False, home=home, guardrails=guards, max_steps=12,
                            on_llm_request=lambda **kw: sent.append(json.dumps(kw.get("messages"), default=str)),
                            handoff=False)
        res = agent.run()
        result = b.page.inner_text("#o")
        email_v, name_v = b.page.input_value("#e"), b.page.input_value("#n")
    blob = "\n".join(sent)
    return {
        "mode": mode, "success": res.success, "steps": res.steps, "calls": res.usage.calls, "seconds": round(time.time() - t0),
        "tokens": res.usage.total_input + res.usage.output_tokens,
        "submitted": result,
        "filled": email_v == REAL_EMAIL and name_v == REAL_NAME and result.startswith("subscribed:"),
        "leaked": REAL_EMAIL in blob or REAL_NAME in blob,
        "leak_context": [blob[max(0, m - 60):m + 40] for v in (REAL_EMAIL, REAL_NAME) if (m := blob.find(v)) >= 0],
        "typed": [s.input.get("text") for s in res.history if s.tool == "type"],
        "answer": res.output[:120],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--mode", choices=["reversible", "masked", "both"], default="both")
    ap.add_argument("--out")
    a = ap.parse_args()
    url, rows = serve(), []
    for mode in (["reversible", "masked"] if a.mode == "both" else [a.mode]):
        for i in range(a.trials):
            r = trial(a.model, url, mode, Path("/tmp/selfbrowse-reversible-home"))
            rows.append(r)
            print(json.dumps(r), flush=True)
    for mode in sorted({r["mode"] for r in rows}):
        rs = [r for r in rows if r["mode"] == mode]
        print(f"\n{mode}: filled {sum(r['filled'] for r in rs)}/{len(rs)}, leaked {sum(r['leaked'] for r in rs)}/{len(rs)}, "
              f"median {sorted(r['calls'] for r in rs)[len(rs)//2]} calls, median {sorted(r['tokens'] for r in rs)[len(rs)//2]} tokens")
    if a.out:
        Path(a.out).write_text(json.dumps({"model": a.model, "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
