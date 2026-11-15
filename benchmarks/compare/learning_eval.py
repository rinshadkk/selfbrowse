"""
Does Selfbrowse's site learning pay off? Same tasks, learning on vs off, on the local demo shop.

    python benchmarks/compare/learning_eval.py --model qwen3.8-bench --out results/learning-qwen3.8

Scenarios (each runs once with learn=False and once with learn=True on a fresh knowledge folder):
  repeat    one navigation task, run N times in a row           (does a routine job get cheaper?)
  transfer  different tasks that share a step (cookie banner)   (does one task's learning help another?)

Per run: model calls and tokens sent (counted by the proxy, the same way for every arm), seconds, replayed
steps, and success judged by the shop's own state, never by the agent's claim. Writes runs.jsonl, summary.md
and the knowledge files each arm ended with.
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics as st
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))
import proxy as px  # noqa: E402
import store  # noqa: E402
from tasks import TASKS  # noqa: E402

from selfbrowse import Browser, BrowseAgent  # noqa: E402
from selfbrowse.llm import make_llm  # noqa: E402

CHROME = Path.home() / "Library/Caches/ms-playwright/chromium-1208/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
BY_ID = {t.id: t for t in TASKS}
PORT = 18765                      # fixed: knowledge is keyed by host:port, so it must survive between runs


def cart_check(item_id: int):
    return lambda answer, state: state.get("cart") == {str(item_id): 1}


# (scenario, [(label, prompt, check)])
SCENARIOS = {
    "repeat": [(f"T3 run {i}", BY_ID["T3-navigate"].prompt, BY_ID["T3-navigate"].check) for i in range(1, 5)],
    "transfer": [
        ("add Desk Lamp", "On {base}, add the 'Desk Lamp' to the cart. Then say done.", cart_check(4)),
        ("add Bamboo Tray", "On {base}, add the 'Bamboo Tray' to the cart. Then say done.", cart_check(7)),
        ("add Salt Mill", "On {base}, add the 'Salt Mill' to the cart. Then say done.", cart_check(8)),
        ("add Desk Lamp again", "On {base}, add the 'Desk Lamp' to the cart. Then say done.", cart_check(4)),
    ],
}


def has_all(*needles: str):
    return lambda answer, state: all(n.lower() in answer.lower() for n in needles)


SKU_PROMPT = "On {base}/list, find the item with SKU {sku} and tell me its name."
SCENARIOS.update({
    # longer tasks: several pages each, so there are more model calls for learning to save
    "long-repeat": [(f"find ZX-4471 run {i}", BY_ID["T6-paginate"].prompt, BY_ID["T6-paginate"].check) for i in range(1, 5)],
    "long-multi": [(f"cheapest per category run {i}",
                    "On {base}, open each category (Kitchen, Home and Garden) and tell me the cheapest product in each one, with its price.",
                    has_all("21.4", "15.25", "12.5")) for i in range(1, 5)],
    "long-transfer": [
        ("SKU ZX-4471", SKU_PROMPT.replace("{sku}", "ZX-4471"), has_all("brass hinge")),
        ("SKU ZX-4435", SKU_PROMPT.replace("{sku}", "ZX-4435"), has_all("item 35")),
        ("SKU ZX-4412", SKU_PROMPT.replace("{sku}", "ZX-4412"), has_all("item 12")),
        ("SKU ZX-4471 again", SKU_PROMPT.replace("{sku}", "ZX-4471"), has_all("brass hinge")),
    ],
})


def state(base: str) -> dict:
    return json.load(urllib.request.urlopen(base + "/__state", timeout=10))


def one_run(base, proxy_url, model, learn, home, prompt, check, max_steps):
    urllib.request.urlopen(base + "/__reset", timeout=10).read()
    px.REC.reset()
    llm = make_llm(f"ollama:{model}", base_url=proxy_url + "/v1")
    browser = Browser(headless=True, executable_path=str(CHROME) if CHROME.exists() else None)
    t0 = time.perf_counter()
    try:
        res = BrowseAgent(prompt.format(base=base), llm=llm, browser=browser, max_steps=max_steps,
                          learn=learn, home=home, handoff=False).run()
        err, answer, ok_agent = res.error, res.output, res.success
        replayed = sum(1 for s in res.history if s.from_cache)
        steps = res.steps
    except Exception as exc:
        err, answer, ok_agent, replayed, steps = f"{type(exc).__name__}: {exc}"[:200], "", False, 0, 0
    finally:
        browser.close()
    seconds = round(time.perf_counter() - t0, 1)
    px.REC.wait_idle()
    calls = px.REC.snapshot()
    return {
        "calls": len(calls), "sent_tokens": sum(c.get("sent_tokens", 0) for c in calls),
        "seconds": seconds, "steps": steps, "replayed": replayed,
        "success": bool(check(answer, state(base))), "agent_success": ok_agent, "error": err, "answer": (answer or "")[:160],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3.8-bench")
    ap.add_argument("--out", default="results/learning")
    ap.add_argument("--scenarios", default="repeat,transfer")
    ap.add_argument("--max-steps", type=int, default=25)
    args = ap.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    base = store.serve(PORT)[1]
    _, proxy_url = px.serve()
    rows = []
    for scen in args.scenarios.split(","):
        for learn in (False, True):
            home = out / "homes" / f"{scen}-{'on' if learn else 'off'}"
            shutil.rmtree(home, ignore_errors=True)
            for i, (label, prompt, check) in enumerate(SCENARIOS[scen], 1):
                r = one_run(base, proxy_url, args.model, learn, home, prompt, check, args.max_steps)
                r.update(scenario=scen, learn=learn, index=i, label=label)
                rows.append(r)
                with (out / "runs.jsonl").open("a") as fh:
                    fh.write(json.dumps(r) + "\n")
                print(f"{scen:8} learn={'on ' if learn else 'off'} #{i} {label:20} calls={r['calls']:>2} "
                      f"tok={r['sent_tokens']:>6} replayed={r['replayed']} {r['seconds']:>5}s ok={r['success']}", flush=True)
    write_summary(out, rows, args.model)


def write_summary(out: Path, rows: list[dict], model: str) -> None:
    md = [f"# Selfbrowse learning evaluation ({model})", "", "One run per cell. Success is judged by the shop's state.", ""]
    for scen in dict.fromkeys(r["scenario"] for r in rows):
        md += [f"## {scen}", "", "| # | task | learn | calls | tokens sent | replayed | seconds | ok |", "|---|---|---|---|---|---|---|---|"]
        for r in (x for x in rows if x["scenario"] == scen):
            md.append(f"| {r['index']} | {r['label']} | {'on' if r['learn'] else 'off'} | {r['calls']} | {r['sent_tokens']} | "
                      f"{r['replayed']} | {r['seconds']} | {'yes' if r['success'] else 'NO'} |")
        for learn in (False, True):
            sel = [x for x in rows if x["scenario"] == scen and x["learn"] == learn]
            if sel:
                md.append(f"\nlearn={'on' if learn else 'off'}: mean calls {st.mean(x['calls'] for x in sel):.1f}, "
                          f"mean tokens {st.mean(x['sent_tokens'] for x in sel):,.0f}, success {sum(x['success'] for x in sel)}/{len(sel)}")
        md.append("")
    (out / "summary.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
