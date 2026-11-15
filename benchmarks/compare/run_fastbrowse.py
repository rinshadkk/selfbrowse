"""Run one task with fastbrowse. Prints one JSON line.

fastbrowse picks each action with a separate decision model (Jev), not with the chat model. Jev runs on
OpenRouter and needs OPENROUTER_API_KEY in the environment (never put the key in a file in this repo). The chat
model, which fastbrowse uses for the start page, field values and the composed answer, is the local Ollama model,
reached through the benchmark's counting proxy.
"""
import time
PROC_START = time.time()
import asyncio
import json
import os
import sys
from pathlib import Path

task, proxy, model, chrome, max_steps = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])


async def main() -> dict:
    out = {"lib": "fastbrowse"}
    t0 = time.perf_counter()
    try:
        from fastbrowse import run_task
        from fastbrowse.models import Limits, LocalChrome
        settings = {
            "OPENROUTER_API_KEY": os.environ["OPENROUTER_API_KEY"],      # Jev, the action picker
            "FASTBROWSE_LLM_BASE_URL": proxy.rstrip("/") + "/v1",       # the chat model: local, through the proxy
            "FASTBROWSE_LLM_MODEL": model,
            "FASTBROWSE_LLM_STRICT": "0",
            # fastbrowse gives a model 30 s of silence per call; qwen3.8 thinks for longer than that before its
            # first token, so thinking is off for this role (it only writes short text, not the action choices)
            "FASTBROWSE_LLM_REASONING": "none",
        }
        video = os.environ.get("BENCH_VIDEO_DIR")
        rec = None
        if video:
            Path(video).mkdir(parents=True, exist_ok=True)
            rec = Path(video) / "fastbrowse.mp4"
        out["video_start"] = time.time()
        # The other libraries get Chrome for Testing (argv chrome). fastbrowse's screenshots hang on it (Page.captureScreenshot
        # exceeds its deadline on every page), so it drives the installed Google Chrome instead, headless.
        res = await run_task(
            task, chrome=LocalChrome(), settings=settings,
            limits=Limits(max_steps=max_steps, max_seconds=float(os.environ.get("BENCH_RUN_SECONDS", "600"))),
            record=rec,
        )
        cost = res.cost
        out.update(answer=res.answer or "", agent_success=res.succeeded, steps=len(res.steps),
                   error=None if res.succeeded else f"{res.status.value}: {(res.error or '')[:240]}",
                   jev_and_llm_dollars=round(float(getattr(cost, "known_dollars", 0) or 0), 5))
    except Exception as exc:
        out.update(answer="", agent_success=False, steps=0, error=f"{type(exc).__name__}: {exc}"[:300])
    out["seconds"] = round(time.perf_counter() - t0, 2)
    out["proc_start"] = PROC_START
    return out


line = "RESULT " + json.dumps(asyncio.run(main()))
if os.environ.get("BENCH_RESULT_FILE"):
    Path(os.environ["BENCH_RESULT_FILE"]).write_text(line)
if not os.environ.get("BENCH_LIVE"):
    print(line)
