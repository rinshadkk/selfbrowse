"""Run one task with Selfbrowse (learning off, so runs are independent). Prints one RESULT line."""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from selfbrowse import Agent, Browser
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
    browser = Browser(headless=True, executable_path=chrome or None)
    res = Agent(task, llm=llm, browser=browser, max_steps=max_steps, learn=False, handoff=False).run()
    out.update(answer=res.output, agent_success=res.success, steps=res.steps, error=res.error)
except Exception as exc:
    out.update(answer="", agent_success=False, steps=0, error=f"{type(exc).__name__}: {exc}"[:300])
finally:
    if browser:
        browser.close()
out["seconds"] = round(time.perf_counter() - t0, 2)
print("RESULT " + json.dumps(out))
