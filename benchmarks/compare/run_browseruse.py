"""Run one task with browser-use. Prints one JSON line."""
import asyncio
import json
import os
import sys
import time

os.environ["ANONYMIZED_TELEMETRY"] = "false"
os.environ["BROWSER_USE_LOGGING_LEVEL"] = "error"
from browser_use import Agent, Browser
from browser_use.llm import ChatAnthropic, ChatOllama

task, proxy, model, chrome, max_steps = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])


async def main() -> dict:
    out = {"lib": "browser-use"}
    t0 = time.perf_counter()
    try:
        if model.startswith("claude"):
            llm = ChatAnthropic(model=model, base_url=proxy, api_key=os.environ["ANTHROPIC_API_KEY"])
        else:
            llm = ChatOllama(model=model, host=proxy)
        browser = Browser(headless=True, executable_path=chrome or None, keep_alive=False)
        agent = Agent(task=task, llm=llm, browser=browser, use_vision=False)
        hist = await agent.run(max_steps=max_steps)
        errs = [e for e in hist.errors() if e]
        out.update(answer=hist.final_result() or "", agent_success=bool(hist.is_successful()),
                   steps=len(hist.history), error=(errs[-1][:300] if errs and not hist.is_done() else None))
    except Exception as exc:
        out.update(answer="", agent_success=False, steps=0, error=f"{type(exc).__name__}: {exc}"[:300])
    out["seconds"] = round(time.perf_counter() - t0, 2)
    return out


print("RESULT " + json.dumps(asyncio.run(main())))
