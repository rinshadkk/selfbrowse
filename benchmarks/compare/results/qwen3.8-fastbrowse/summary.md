# Benchmark: model `qwen3.8-bench`, 1 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| fastbrowse | 4/6 (67%) | 5.0 | 160,574 | 68,921 | 382 | 171 |
| selfbrowse | 6/6 (100%) | 5.0 | 66,195 | 63,175 | 10,401 | 84 |

## Per task (successes / runs, avg sent tokens)

| Task | fastbrowse | selfbrowse |
|---|---|---|
| U1-github (live) | 0/1 · 198,200 tok · 7.0 calls | 1/1 · 6,850 tok · 3.0 calls |
| U2-pypi (live) | 1/1 · 297,199 tok · 14.0 calls | 1/1 · 8,983 tok · 4.0 calls |
| U3-wikipedia (live) | 1/1 · 250,752 tok · 2.0 calls | 1/1 · 353,787 tok · 11.0 calls |
| U4-books (live) | 0/1 · 394 tok · 1.0 calls | 1/1 · 16,014 tok · 6.0 calls |
| U5-pydocs (live) | 1/1 · 381 tok · 1.0 calls | 1/1 · 6,801 tok · 4.0 calls |
| T7-live-hn (live) | 1/1 · 216,515 tok · 5.0 calls | 1/1 · 4,733 tok · 2.0 calls |

## Failures

- rep1 U1-github fastbrowse: error: LLM transport failed after 6 requests in 202.1s; last: silent for 30s (TimeoutError). This came after steps that may have changed the site (click 162 Tags (Latest commit); click Releases (Forks)), so check the site before running the task a
- rep1 U4-books fastbrowse: stuck: Could not complete the task after HTTP 404 at https://books.toscrape.com/catalogue/category/mystery_3/index.html in this browser session; the cause is unknown.
