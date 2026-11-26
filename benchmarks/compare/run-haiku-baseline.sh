#!/bin/bash
# Clean Haiku 5.5 baseline against the Anthropic API directly: Selfbrowse and browser-use, 13 tasks, 2 reps.
# The key is read at a hidden prompt. It is not written to any file.
set -euo pipefail
cd "$(dirname "$0")/../.."

# Nothing from earlier gateway or OpenRouter runs may leak into this one.
unset BENCH_ANTHROPIC_UPSTREAM ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN VIA_OPENROUTER

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  read -r -s -p "Anthropic API key (input hidden): " ANTHROPIC_API_KEY
  echo
fi
export ANTHROPIC_API_KEY

stamp=$(date +%Y%m%d-%H%M%S)
base=benchmarks/compare/results
common=(--suite all --libs selfbrowse,browser-use --model claude-haiku-5-5 --max-steps 30 --timeout 900)

echo "== Check: one easy task for each library =="
smoke="$base/haiku5.5-check-$stamp"
.venv/bin/python benchmarks/compare/run.py "${common[@]}" --tasks T1-read-text --reps 1 --out "$smoke"
.venv/bin/python - "$smoke/runs.jsonl" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
bad = [r for r in rows if not r["success"] or r["calls_without_usage"] or not r["input_tokens"]]
for r in bad:
    print(f"  {r['lib']}: success={r['success']} input_tokens={r['input_tokens']} error={r['error']}")
if len(rows) != 2 or bad:
    sys.exit("Check failed, so the full run was not started.")
PY

echo "== Full baseline: 13 tasks, 2 reps =="
out="$base/haiku5.5-$stamp"
caffeinate -i .venv/bin/python benchmarks/compare/run.py "${common[@]}" --reps 2 --out "$out" 2>&1 | tee "$out.log"
echo "Results: $out/summary.md"
