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
import shlex
import shutil
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


TERM_SIZE = "88x32"


def video_seconds(path: Path) -> float:
    cp = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                        capture_output=True, text=True, timeout=30)
    return float(cp.stdout.strip() or 0)


def join_videos(browser_video: Path, cast: Path, out: Path, lead: float) -> "Path | None":
    """Browser video on the left, the recorded terminal on the right, both from the start of the run.

    Playwright's recording only begins at the first painted frame, so the browser video is padded with `lead`
    seconds of blank page to line it up with the terminal, which is shown from its first moment."""
    gif = cast.with_suffix(".gif")
    try:
        subprocess.run(["agg", "--font-size", "15", "--fps-cap", "15", "--theme", "monokai", str(cast), str(gif)],
                       check=True, capture_output=True, timeout=300)
        tmp = out.with_name(out.stem + "_tmp.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(browser_video), "-i", str(gif),
                        "-filter_complex",
                        f"[0:v]fps=15,scale=-2:720,tpad=start_duration={lead:.2f}:start_mode=add:color=white[b];"
                        "[1:v]fps=15,scale=-2:720[t];[b][t]hstack=inputs=2,pad=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p",
                        "-c:v", "libx264", "-crf", "26", "-preset", "veryfast", "-movflags", "+faststart", str(tmp)],
                       check=True, capture_output=True, timeout=300)
        tmp.replace(out)
        return out
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"  (could not join the videos: {str(exc)[:120]})", flush=True)
        return None
    finally:
        gif.unlink(missing_ok=True)


def run_one(lib: str, task, base: str, proxy_url: str, model: str, max_steps: int, timeout: int,
            video_dir: "Path | None" = None, terminal: bool = False) -> dict:
    if base:
        urllib.request.urlopen(base + "/__reset", timeout=10).read()
    px.REC.reset()
    state_extra = {"hn_before": _hn_top_title()} if task.id == "T7-live-hn" else {}
    prompt = task.prompt.format(base=base)
    t0 = time.perf_counter()
    try:
        cmd, extra_env = LIBS[lib]
        extra_env = dict(extra_env)
        if video_dir:                                    # one folder per run; the biggest file is the run
            tmp = video_dir / f"_{lib}-{task.id}"
            shutil.rmtree(tmp, ignore_errors=True)
            extra_env["BENCH_VIDEO_DIR"] = str(tmp)
        argv = cmd + [prompt, proxy_url, model, str(CHROME), str(max_steps)]
        cast = result_file = None
        if terminal and video_dir:
            # Option 2: record the terminal with asciinema while the runner writes its trace there, then join
            # the browser video and the terminal side by side afterwards.
            cast = video_dir / f"_{lib}-{task.id}.cast"
            result_file = video_dir / f"_{lib}-{task.id}.result"
            for f in (cast, result_file):
                f.unlink(missing_ok=True)
            extra_env.update(BENCH_LIVE="1", BENCH_RESULT_FILE=str(result_file))
            argv = ["asciinema", "rec", "--headless", "--quiet", "--overwrite", "--window-size", TERM_SIZE,
                    "-c", shlex.join(argv), str(cast)]
        t_launch = time.time()
        cp = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=timeout,
                            env={**os.environ, **extra_env})
        out_text = result_file.read_text() if result_file and result_file.exists() else cp.stdout
        line = next((l for l in reversed(out_text.splitlines()) if l.startswith("RESULT ")), None)
        res = json.loads(line[7:]) if line else {"answer": "", "agent_success": False, "steps": 0,
                                                 "error": "no result: " + (cp.stderr.strip().splitlines() or ["?"])[-1][:200]}
    except subprocess.TimeoutExpired:
        res = {"lib": lib, "answer": "", "agent_success": False, "steps": 0, "error": f"timeout after {timeout}s"}
    wall = time.perf_counter() - t0
    state = get_state(base) if base else {}
    state.update(state_extra)
    if task.id == "T7-live-hn":
        state["hn_after"] = _hn_top_title()
    video_file = ""
    if video_dir:
        tmp = video_dir / f"_{lib}-{task.id}"
        found = (sorted([*tmp.glob("*.webm"), *tmp.glob("*.mp4")], key=lambda p: p.stat().st_size, reverse=True)
                 if tmp.exists() else [])
        if found:
            video_file = f"{lib}__{task.id}{found[0].suffix}"
            shutil.move(str(found[0]), str(video_dir / video_file))
        shutil.rmtree(tmp, ignore_errors=True)
        if cast is not None and video_file and cast.exists():
            src = video_dir / video_file
            # when did the browser video begin? Playwright's file ends at close and starts at the first painted
            # frame; Browser Use's sampler is anchored to its own start.
            began = (res["video_end"] - video_seconds(src)) if res.get("video_end") else (res.get("video_start") or t_launch)
            joined = join_videos(src, cast, video_dir / f"{lib}__{task.id}.mp4", lead=max(began - t_launch, 0))
            if joined:
                (video_dir / video_file).unlink(missing_ok=True) if video_file != joined.name else None
                video_file = joined.name
            cast.rename(video_dir / f"{lib}__{task.id}.cast")
            if result_file:
                result_file.unlink(missing_ok=True)
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
        "video": video_file,
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
    ap.add_argument("--record-video", action="store_true", help="record a video of every run into <out>/videos and write an index.html")
    ap.add_argument("--suite", choices=["store", "usecases", "all"], default="store",
                    help="store = the local demo shop (plus two live pages); usecases = real public sites; all = both")
    ap.add_argument("--terminal", action="store_true",
                    help="with --record-video: also record the terminal and join it beside the browser (needs asciinema, agg, ffmpeg)")
    args = ap.parse_args()
    global TASKS
    if args.suite in ("usecases", "all"):
        from usecases import TASKS as USE
        TASKS = USE if args.suite == "usecases" else [*TASKS, *[t for t in USE if t.id not in {x.id for x in TASKS}]]
    if args.terminal and not args.record_video:
        ap.error("--terminal needs --record-video")

    tasks = [t for t in TASKS if not args.tasks or t.id in args.tasks.split(",")]
    libs = args.libs.split(",")
    out_dir = Path(args.out) if args.out else HERE / "results" / time.strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    video_dir = out_dir / "videos" if args.record_video else None
    if video_dir:
        video_dir.mkdir(parents=True, exist_ok=True)
    base = None if args.suite == "usecases" else store.serve()[1]
    _, proxy_url = px.serve()
    print(f"store {base or '(real sites)'}  proxy {proxy_url}  model {args.model}  -> {out_dir}", flush=True)

    (out_dir / "meta.json").write_text(json.dumps(versions(args.model), indent=2))
    rows = []
    with open(out_dir / "runs.jsonl", "w") as fh:
        for rep in range(1, args.reps + 1):
            for task in tasks:
                for lib in libs:                       # interleaved: libraries see the same conditions
                    r = run_one(lib, task, base, proxy_url, args.model, args.max_steps, args.timeout, video_dir, args.terminal)
                    r["rep"] = rep
                    rows.append(r)
                    fh.write(json.dumps(r) + "\n")
                    fh.flush()
                    print(f"rep{rep} {task.id:<14} {lib:<12} {'PASS' if r['success'] else 'FAIL'} "
                          f"calls={r['model_calls']:>2} sent={r['sent_tokens']:>6} wall={r['wall_seconds']:>6}s "
                          f"{(r['error'] or '')[:70]}", flush=True)
    (out_dir / "summary.md").write_text(summarize(rows, args))
    if video_dir:
        (video_dir / "index.html").write_text(video_index(rows, args))
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
    upstream = os.environ.get("BENCH_ANTHROPIC_UPSTREAM")
    settings = ((f"Anthropic model through a gateway at {upstream} (a Claude Code wrapper), provider default sampling settings"
                 if upstream else "hosted Anthropic model, provider default sampling settings") if model.startswith("claude") else
                f"Ollama model {model} (Modelfile.* in this folder): num_ctx 16384, temperature 0, seed 42")
    return {
        "selfbrowse_commit": sh(["git", "rev-parse", "--short", "HEAD"]), "selfbrowse_dirty": bool(sh(["git", "status", "--short"])),
        "browser_use": sh([str(HERE / ".venv-bu/bin/python"), "-c", "import importlib.metadata as m;print(m.version('browser-use'))"]),
        "ollama": sh(["ollama", "--version"]), "model": model, "model_digest": digest,
        "model_settings": settings, "anthropic_upstream": upstream or "https://api.anthropic.com",
        "browser": "Playwright Chromium 1208, headless, same binary for both", "vision": "off for both",
        "date": time.strftime("%Y-%m-%d %H:%M"), "max_steps": 15,
    }


def video_index(rows: list[dict], args) -> str:
    """One page: for each task, every library's run stacked, each video showing the browser (left) and the
    terminal (right) side by side, with the outcome beside it."""
    import html
    libs = sorted({r["lib"] for r in rows})
    ok_n = {lib: sum(r["success"] for r in rows if r["lib"] == lib) for lib in libs}
    tot = {lib: sum(1 for r in rows if r["lib"] == lib) for lib in libs}
    out = [f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
           f"<title>Runs: {html.escape(args.model)}</title>"
           "<style>body{font:16px/1.5 system-ui,sans-serif;margin:0 auto;max-width:1180px;padding:1.5rem 16px 4rem;color:#1d2420;background:#fbfbf8}"
           "h1{font-size:1.6rem;margin:.2rem 0}h2{font-size:1.15rem;margin:2.4rem 0 .2rem}.sub{color:#555;margin:0 0 .6rem}"
           ".sum{display:flex;gap:2rem;flex-wrap:wrap;margin:1rem 0 0}.sum div{border-left:3px solid #4a7c59;padding-left:.7rem}"
           ".run{margin:.9rem 0 1.4rem}.run b.lib{display:inline-block;min-width:7rem}video{width:100%;display:block;border:1px solid #c9ccc4;"
           "border-radius:4px;background:#111;margin-top:.3rem}.ok{color:#1b6b3a}.bad{color:#b23a26}small{color:#555}"
           "@media(prefers-color-scheme:dark){body{background:#141816;color:#e4e8e2}.sub,small{color:#a3aaa2}video{border-color:#3a403a}"
           ".ok{color:#6fcf97}.bad{color:#f08a76}}</style>"
           f"<h1>{html.escape(args.model)} on real tasks</h1>"
           "<p class=sub>Each video shows the browser on the left and the terminal on the right, from the start of the run. "
           "The same task and the same model for every library; success is judged by a script, not by the agent.</p><div class=sum>"
           + "".join(f"<div><b>{html.escape(l)}</b><br>{ok_n[l]} of {tot[l]} passed</div>" for l in libs) + "</div>"]
    for t in TASKS:
        runs = [(lib, next((x for x in rows if x["lib"] == lib and x["task"] == t.id), None)) for lib in libs]
        if not any(r and r.get("video") for _, r in runs):
            continue
        kind = "real site" if t.live else "demo shop"
        out.append(f"<h2>{html.escape(t.id)}: {html.escape(t.title)}</h2><p class=sub>{kind}. {html.escape(t.prompt.replace('{base}', 'the demo shop'))}</p>")
        for lib, r in runs:
            if not r:
                continue
            tag = f'<b class="{"ok" if r["success"] else "bad"}">{"PASS" if r["success"] else "FAIL"}</b>'
            vid = (f'<video controls preload="metadata" src="{r["video"]}"></video>' if r.get("video") else "<small>no video</small>")
            out.append(f'<div class=run><b class=lib>{html.escape(lib)}</b> {tag} <small>{r["wall_seconds"]}s, {r["model_calls"]} model calls, '
                       f'{r["sent_tokens"]:,} tokens sent</small>{vid}</div>')
    return "".join(out)


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
