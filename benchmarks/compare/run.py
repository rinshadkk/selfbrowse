"""
Run the comparison.

    python benchmarks/compare/run.py --model llama3.1-bench --reps 2

Writes benchmarks/compare/results/<timestamp>/{runs.jsonl,summary.md}.
Needs: the main venv (selfbrowse + tiktoken) to run this file, .venv-bu (browser-use) for that runner,
and Ollama on localhost:11434.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import proxy as px  # noqa: E402
import store  # noqa: E402
from tasks import TASKS, _hn_top_title  # noqa: E402

CHROME = Path.home() / "Library/Caches/ms-playwright/chromium-1208/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
SB = [sys.executable, str(HERE / "run_selfbrowse.py")]
LIBS = {
    "selfbrowse": (SB, {}),                                         # provider default (JSON mode for ollama)
    "selfbrowse-json": (SB, {"SB_TOOL_MODE": "json"}),
    "selfbrowse-native": (SB, {"SB_TOOL_MODE": "native"}),          # fixes only, native tool calling
    "browser-use": ([str(HERE / ".venv-bu/bin/python"), str(HERE / "run_browseruse.py")], {}),
}
DEFAULT_LIBS = "selfbrowse,browser-use"


def get_state(base: str) -> dict:
    return json.load(urllib.request.urlopen(base + "/__state", timeout=10))


def run_one(lib: str, task, base: str, proxy_url: str, model: str, max_steps: int, timeout: int) -> dict:
    urllib.request.urlopen(base + "/__reset", timeout=10).read()
    px.REC.reset()
    state_extra = {"hn_before": _hn_top_title()} if task.id == "T7-live-hn" else {}
    prompt = task.prompt.format(base=base)
    t0 = time.perf_counter()
    try:
        cmd, extra_env = LIBS[lib]
        cp = subprocess.run(cmd + [prompt, proxy_url, model, str(CHROME), str(max_steps)], cwd=ROOT,
                            capture_output=True, text=True, timeout=timeout, env={**os.environ, **extra_env})
        line = next((l for l in reversed(cp.stdout.splitlines()) if l.startswith("RESULT ")), None)
        res = json.loads(line[7:]) if line else {"answer": "", "agent_success": False, "steps": 0,
                                                 "error": "no result: " + (cp.stderr.strip().splitlines() or ["?"])[-1][:200]}
    except subprocess.TimeoutExpired:
        res = {"lib": lib, "answer": "", "agent_success": False, "steps": 0, "error": f"timeout after {timeout}s"}
    wall = time.perf_counter() - t0
    state = get_state(base)
    state.update(state_extra)
    if task.id == "T7-live-hn":
        state["hn_after"] = _hn_top_title()
    calls = px.REC.snapshot()
    ok = bool(task.check(str(res.get("answer") or ""), state))
    return {
        "lib": lib, "task": task.id, "success": ok, "agent_claimed_success": bool(res.get("agent_success")),
        "answer": str(res.get("answer") or "")[:200], "steps": res.get("steps"), "error": res.get("error"),
        "model_calls": len(calls), "sent_tokens": sum(c.get("sent_tokens", 0) for c in calls),
        "first_call_tokens": calls[0].get("sent_tokens") if calls else None,
        "billed_input": sum(c.get("prompt_eval") or 0 for c in calls), "cache_read": sum(c.get("cache_read") or 0 for c in calls),
        "out_tokens": sum(c.get("eval_count") or 0 for c in calls),
        "model_seconds": round(sum(c["seconds"] for c in calls), 1), "wall_seconds": round(wall, 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama3.1-bench")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--max-steps", type=int, default=15)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--tasks", default="", help="comma list of task ids (default all)")
    ap.add_argument("--libs", default=DEFAULT_LIBS)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    tasks = [t for t in TASKS if not args.tasks or t.id in args.tasks.split(",")]
    libs = args.libs.split(",")
    out_dir = Path(args.out) if args.out else HERE / "results" / time.strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    _, base = store.serve()
    _, proxy_url = px.serve()
    print(f"store {base}  proxy {proxy_url}  model {args.model}  -> {out_dir}", flush=True)

    (out_dir / "meta.json").write_text(json.dumps(versions(args.model), indent=2))
    rows = []
    with open(out_dir / "runs.jsonl", "w") as fh:
        for rep in range(1, args.reps + 1):
            for task in tasks:
                for lib in libs:                       # interleaved: libraries see the same conditions
                    r = run_one(lib, task, base, proxy_url, args.model, args.max_steps, args.timeout)
                    r["rep"] = rep
                    rows.append(r)
                    fh.write(json.dumps(r) + "\n")
                    fh.flush()
                    print(f"rep{rep} {task.id:<14} {lib:<12} {'PASS' if r['success'] else 'FAIL'} "
                          f"calls={r['model_calls']:>2} sent={r['sent_tokens']:>6} wall={r['wall_seconds']:>6}s "
                          f"{(r['error'] or '')[:70]}", flush=True)
    (out_dir / "summary.md").write_text(summarize(rows, args))
    print(f"\nwrote {out_dir/'summary.md'}")


def versions(model: str) -> dict:
    def sh(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=30).stdout.strip()
        except Exception:
            return "?"
    digest = "n/a (hosted)"
    if not model.startswith("claude"):
        tags = json.load(urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=10))["models"]
        digest = next((m["digest"][:12] for m in tags if m["name"].split(":")[0] == model.split(":")[0]), "?")
    settings = ("hosted Anthropic model, provider default sampling settings" if model.startswith("claude") else
                "llama3.1:latest 8B Q4_K_M, num_ctx 16384, temperature 0, seed 42 (Modelfile.llama31)")
    return {
        "selfbrowse_commit": sh(["git", "rev-parse", "--short", "HEAD"]), "selfbrowse_dirty": bool(sh(["git", "status", "--short"])),
        "browser_use": sh([str(HERE / ".venv-bu/bin/python"), "-c", "import importlib.metadata as m;print(m.version('browser-use'))"]),
        "ollama": sh(["ollama", "--version"]), "model": model, "model_digest": digest,
        "model_settings": settings,
        "browser": "Playwright Chromium 1208, headless, same binary for both", "vision": "off for both",
        "date": time.strftime("%Y-%m-%d %H:%M"), "max_steps": 15,
    }


def summarize(rows: list[dict], args) -> str:
    libs = sorted({r["lib"] for r in rows})
    tasks = [t for t in TASKS if any(r["task"] == t.id for r in rows)]

    def agg(lib, key, only_pass=False):
        vals = [r[key] for r in rows if r["lib"] == lib and r[key] is not None and (r["success"] or not only_pass)]
        return st.mean(vals) if vals else float("nan")

    lines = [f"# Benchmark: model `{args.model}`, {args.reps} runs per task, "
             f"max {args.max_steps} steps\n", "## Overall\n",
             "| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |",
             "|---|---|---|---|---|---|---|"]
    for lib in libs:
        rs = [r for r in rows if r["lib"] == lib]
        ok = sum(r["success"] for r in rs)
        lines.append(f"| {lib} | {ok}/{len(rs)} ({100*ok/len(rs):.0f}%) | {agg(lib,'model_calls'):.1f} | "
                     f"{agg(lib,'sent_tokens'):,.0f} | {agg(lib,'billed_input'):,.0f} | {agg(lib,'first_call_tokens'):,.0f} | {agg(lib,'wall_seconds'):.0f} |")
    lines += ["\n## Per task (successes / runs, avg sent tokens)\n", "| Task | " + " | ".join(libs) + " |", "|---|" + "---|" * len(libs)]
    for t in tasks:
        cells = []
        for lib in libs:
            rs = [r for r in rows if r["lib"] == lib and r["task"] == t.id]
            cells.append(f"{sum(r['success'] for r in rs)}/{len(rs)} · {st.mean(r['sent_tokens'] for r in rs):,.0f} tok · "
                         f"{st.mean(r['model_calls'] for r in rs):.1f} calls")
        lines.append(f"| {t.id}{' (live)' if t.live else ''} | " + " | ".join(cells) + " |")
    lines += ["\n## Failures\n"]
    for r in rows:
        if not r["success"]:
            lines.append(f"- rep{r['rep']} {r['task']} {r['lib']}: {r['error'] or 'wrong answer: ' + repr(r['answer'][:80])}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
