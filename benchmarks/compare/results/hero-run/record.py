"""Record one real run for the website hero: benchmark store, qwen3.6 (local, native tools), guardrails on."""
import json, sys, time
sys.path.insert(0, ".")          # run from benchmarks/compare
from store import serve, STATE
from selfbrowse import Agent, Browser
from selfbrowse.guardrails import AllowedDomains, ConfirmRisky, RedactPII, Budget
from selfbrowse.llm import make_llm

out = sys.argv[1]
server, base = serve()
task = f"Go to {base}, search for 'kettle', open the cheapest kettle and add it to the cart. Then tell me its name and price."
llm = make_llm("ollama:qwen3.6-bench", json_mode=False)
t0 = time.time()
with Browser(headless=True) as b:
    res = Agent(task, llm=llm, browser=b, learn=False, max_steps=20, trace=out,
                guardrails=[AllowedDomains(["127.0.0.1"]), ConfirmRisky(), RedactPII(), Budget(max_tokens=100_000)]).run()
wall = time.time() - t0
print(json.dumps({"task": task.replace(base, "{base}"), "success": res.success, "answer": res.output, "error": res.error,
                  "cart": STATE["cart"], "steps": res.steps, "calls": res.usage.calls, "input": res.usage.total_input,
                  "output": res.usage.output_tokens, "wall": round(wall, 1),
                  "history": [(s.tool, s.input, s.result[:90]) for s in res.history]}, indent=1))
server.shutdown()
