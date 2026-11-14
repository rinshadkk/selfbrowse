"""Run one task with browser-use. Prints one JSON line."""
import time
PROC_START = time.time()
import asyncio
import json
import os
import sys
from pathlib import Path

os.environ["ANONYMIZED_TELEMETRY"] = "false"
os.environ["BROWSER_USE_LOGGING_LEVEL"] = "info" if os.environ.get("BENCH_LIVE") else "error"
from browser_use import Agent, Browser
from browser_use.llm import ChatAnthropic, ChatOllama

task, proxy, model, chrome, max_steps = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])


frames: list[tuple[float, bytes]] = []      # (seconds since start, PNG)
T_START = time.perf_counter()
T_START_EPOCH = time.time()


async def sample_frames(browser, store: list, every: float = 0.1) -> None:
    while True:
        try:
            store.append((time.perf_counter() - T_START, await browser.take_screenshot()))
        except asyncio.CancelledError:
            raise
        except Exception:
            pass                                     # the browser is not ready yet, or is closing
        await asyncio.sleep(every)


def write_video(store: list, folder: Path, fps: int = 10) -> None:
    """Encode the samples as real time: for each 1/fps tick, show the latest frame taken by then."""
    if not store:
        return
    import io
    import imageio.v2 as iio
    import numpy as np
    from PIL import Image
    folder.mkdir(parents=True, exist_ok=True)
    end = store[-1][0]
    with iio.get_writer(str(folder / "browser-use.mp4"), fps=fps, codec="libx264", macro_block_size=1) as w:
        i = 0
        for k in range(int(end * fps) + 1):
            t = k / fps
            while i + 1 < len(store) and store[i + 1][0] <= t:
                i += 1
            img = Image.open(io.BytesIO(store[i][1])).convert("RGB").resize((1280, 800))
            w.append_data(np.asarray(img))


async def main() -> dict:
    out = {"lib": "browser-use"}
    t0 = time.perf_counter()
    try:
        if model.startswith("claude"):
            llm = ChatAnthropic(model=model, base_url=proxy, api_key=os.environ["ANTHROPIC_API_KEY"])
        else:
            llm = ChatOllama(model=model, host=proxy)
        video = os.environ.get("BENCH_VIDEO_DIR")
        # Browser Use's own recorder keeps one frame per page change and replays them at a fixed rate, so a
        # run comes out as a fraction of a second. To get a real-time video like Selfbrowse's, sample the
        # page ten times a second from outside and encode that (this adds a little load while recording).
        extra = {"viewport": {"width": 1280, "height": 800}} if video else {}
        browser = Browser(headless=True, executable_path=chrome or None, keep_alive=False, **extra)
        sampler = asyncio.create_task(sample_frames(browser, frames)) if video else None
        # A local reasoning model can take minutes per call; the library's 75 s default would fail it for being slow.
        slow = {} if model.startswith("claude") else {"llm_timeout": 300, "step_timeout": 600}
        agent = Agent(task=task, llm=llm, browser=browser, use_vision=False, **slow)
        hist = await agent.run(max_steps=max_steps)
        if sampler:
            sampler.cancel()
            write_video(frames, Path(video))
        errs = [e for e in hist.errors() if e]
        out.update(answer=hist.final_result() or "", agent_success=bool(hist.is_successful()),
                   steps=len(hist.history), error=(errs[-1][:300] if errs and not hist.is_done() else None))
    except Exception as exc:
        out.update(answer="", agent_success=False, steps=0, error=f"{type(exc).__name__}: {exc}"[:300])
    out["seconds"] = round(time.perf_counter() - t0, 2)
    out["proc_start"], out["video_start"] = PROC_START, T_START_EPOCH   # the sampled video's clock starts after the imports
    return out


line = "RESULT " + json.dumps(asyncio.run(main()))
if os.environ.get("BENCH_RESULT_FILE"):
    Path(os.environ["BENCH_RESULT_FILE"]).write_text(line)
if not os.environ.get("BENCH_LIVE"):
    print(line)
