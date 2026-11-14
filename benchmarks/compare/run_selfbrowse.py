"""Run one task with Selfbrowse (learning off, so runs are independent). Prints one RESULT line."""
import time
PROC_START = time.time()
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from selfbrowse import BrowseAgent, Browser
from selfbrowse.llm import make_llm

task, proxy, model, chrome, max_steps = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
t0 = time.perf_counter()
out = {"lib": "selfbrowse"}
browser = None
try:
    mode = os.environ.get("SB_TOOL_MODE", "auto")          # auto = provider default, json, native
    extra = {} if mode == "auto" else {"json_mode": mode == "json"}
    if model.startswith("claude"):
        llm = make_llm(f"anthropic:{model}", base_url=proxy)          # key comes from ANTHROPIC_API_KEY
    else:
        llm = make_llm(f"ollama:{model}", base_url=proxy + "/v1", **extra)
    live = bool(os.environ.get("BENCH_LIVE"))
    browser = Browser(headless=True, executable_path=chrome or None,
                      record_video_dir=os.environ.get("BENCH_VIDEO_DIR") or None)
    if live:
        print(f"\033[1mselfbrowse\033[0m  model {model}\n\033[2mtask:\033[0m {task}\n", flush=True)

    def show(step):
        print(f"  {step.number:>2}. {step.tool} {json.dumps(step.input, ensure_ascii=False)[:110]}", flush=True)

    if os.environ.get("BENCH_VIDEO_DIR"):
        browser.start()                                    # the recording begins here
        out["video_start"] = time.time()
    res = BrowseAgent(task, llm=llm, browser=browser, max_steps=max_steps, learn=False, handoff=False,
                      on_step=show if live else None).run()
    if live:
        print(f"\n\033[1manswer:\033[0m {res.output}\n\033[2m[{res.steps} steps]\033[0m", flush=True)
    out.update(answer=res.output, agent_success=res.success, steps=res.steps, error=res.error)
except Exception as exc:
    out.update(answer="", agent_success=False, steps=0, error=f"{type(exc).__name__}: {exc}"[:300])
finally:
    if browser:
        browser.close()
        out["video_end"] = time.time()     # Playwright's file starts at the first painted frame and ends here
out["seconds"] = round(time.perf_counter() - t0, 2)
out["proc_start"] = PROC_START
line = "RESULT " + json.dumps(out)
if os.environ.get("BENCH_RESULT_FILE"):
    Path(os.environ["BENCH_RESULT_FILE"]).write_text(line)
if not os.environ.get("BENCH_LIVE"):
    print(line)
