"""Run one benchmark task with Selfbrowse and print every step, to see why it failed.

    python benchmarks/compare/diagnose.py T3-navigate [model]
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))
import store
from tasks import TASKS
from selfbrowse import BrowseAgent, Browser

CHROME = Path.home() / "Library/Caches/ms-playwright/chromium-1208/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
task = next(t for t in TASKS if t.id == sys.argv[1])
model = sys.argv[2] if len(sys.argv) > 2 else "llama3.1-bench"
_, base = store.serve()
with Browser(executable_path=str(CHROME)) as b:
    agent = BrowseAgent(task.prompt.format(base=base), llm=f"ollama:{model}", browser=b, max_steps=15, learn=False,
                  handoff=False, trace="/tmp/sb_diag_traces")
    res = agent.run()
    for s in res.history:
        print(f"{s.number:>2}. {s.tool} {s.input} -> {s.result[:110]!r}")
    print("\nSTATE:", store.STATE, "\nANSWER:", repr(res.output[:200]), "\nERROR:", res.error, "\nTRACE:", agent.trace_path)
