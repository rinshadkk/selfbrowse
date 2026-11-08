# Benchmark: model `llama3.1-bench` (llama3.1 8B, 16k context, temperature 0), up to 2 runs per task (stopped early: 26 of 32 runs), max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|
| browser-use | 7/13 (54%) | 15.5 | 152,315 | 12,485 | 119 |
| selfbrowse | 1/13 (8%) | 6.7 | 13,872 | 3,827 | 10 |

## Per task (successes / runs, avg sent tokens)

| Task | browser-use | selfbrowse |
|---|---|---|
| T1-read-text | 2/2 · 117,663 tok · 11.5 calls | 0/2 · 10,450 tok · 2.5 calls |
| T2-search | 0/2 · 194,028 tok · 20.5 calls | 0/2 · 3,330 tok · 3.0 calls |
| T3-navigate | 2/2 · 104,134 tok · 10.0 calls | 0/2 · 26,333 tok · 15.0 calls |
| T4-cart | 0/2 · 183,624 tok · 16.0 calls | 0/2 · 26,422 tok · 15.0 calls |
| T5-login | 2/2 · 141,524 tok · 20.5 calls | 0/2 · 2,200 tok · 2.0 calls |
| T6-paginate | 1/1 · 209,455 tok · 24.0 calls | 0/1 · 13,204 tok · 7.0 calls |
| T7-live-hn (live) | 0/1 · 127,678 tok · 10.0 calls | 1/1 · 4,432 tok · 2.0 calls |
| T8-live-wiki (live) | 0/1 · 161,018 tok · 11.0 calls | 0/1 · 25,236 tok · 3.0 calls |

## Failures

- rep1 T1-read-text selfbrowse: wrong answer: '#5 heading "About Demo Store"\nread()\nThe Demo Store was started in 2010.'
- rep1 T2-search selfbrowse: wrong answer: '# Clicked Reject\n--- page ---\n#7 button "Add to cart"     #12 textbox "Search" ('
- rep1 T2-search browser-use: wrong answer: 'The price of the cheapest kettle is $34.50, but the prices of the other two kett'
- rep1 T3-navigate selfbrowse: stopped after 15 steps without finishing
- rep1 T4-cart selfbrowse: stopped after 15 steps without finishing
- rep1 T4-cart browser-use: wrong answer: "Failed to add 'Desk Lamp' to cart. The cart is still empty. I have searched the "
- rep1 T5-login selfbrowse: wrong answer: '{"name": "send_keys", "parameters": {"selector": "#1", "text": "alice"}}'
- rep1 T6-paginate selfbrowse: wrong answer: 'The item with SKU ZX-4471 is named "Item 21"'
- rep1 T7-live-hn browser-use: timeout after 300s
- rep1 T8-live-wiki selfbrowse: wrong answer: 'scroll down and click on "Search Wikipedia" to search for \'Web Browser\''
- rep1 T8-live-wiki browser-use: timeout after 300s
- rep2 T1-read-text selfbrowse: wrong answer: '#5 heading "About Demo Store"\nread()\nThe Demo Store was started in 2010.'
- rep2 T2-search selfbrowse: wrong answer: '# Clicked Reject\n--- page ---\n#7 button "Add to cart"     #12 textbox "Search" ('
- rep2 T2-search browser-use: wrong answer: "Unable to find the price of the cheapest kettle. The search query 'price of the "
- rep2 T3-navigate selfbrowse: stopped after 15 steps without finishing
- rep2 T4-cart selfbrowse: stopped after 15 steps without finishing
- rep2 T4-cart browser-use: wrong answer: "Failed to add 'Desk Lamp' to cart due to uncertain action results. The current U"
- rep2 T5-login selfbrowse: wrong answer: '{"name": "send_keys", "parameters": {"selector": "#1", "text": "alice"}}'
