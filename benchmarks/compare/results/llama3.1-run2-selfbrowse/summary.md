# Benchmark: model `llama3.1-bench`, 2 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| selfbrowse-json | 6/16 (38%) | 10.8 | 23,041 | 18,810 | 826 | 22 |
| selfbrowse-native | 10/16 (62%) | 9.4 | 23,344 | 15,421 | 1,006 | 25 |

## Per task (successes / runs, avg sent tokens)

| Task | selfbrowse-json | selfbrowse-native |
|---|---|---|
| T1-read-text | 2/2 · 20,247 tok · 12.0 calls | 2/2 · 3,580 tok · 3.0 calls |
| T2-search | 0/2 · 12,366 tok · 10.0 calls | 2/2 · 13,847 tok · 9.0 calls |
| T3-navigate | 2/2 · 6,497 tok · 6.0 calls | 0/2 · 13,758 tok · 9.0 calls |
| T4-cart | 0/2 · 7,792 tok · 7.0 calls | 2/2 · 26,733 tok · 15.0 calls |
| T5-login | 2/2 · 9,058 tok · 8.0 calls | 2/2 · 8,093 tok · 6.0 calls |
| T6-paginate | 0/2 · 21,875 tok · 15.0 calls | 0/2 · 37,949 tok · 15.0 calls |
| T7-live-hn (live) | 0/2 · 72,824 tok · 13.0 calls | 2/2 · 9,089 tok · 3.0 calls |
| T8-live-wiki (live) | 0/2 · 33,668 tok · 15.0 calls | 0/2 · 73,701 tok · 15.0 calls |

## Failures

- rep1 T2-search selfbrowse-json: wrong answer: '$34.50'
- rep1 T3-navigate selfbrowse-native: wrong answer: 'done with success=true'
- rep1 T4-cart selfbrowse-json: wrong answer: 'Desk Lamp added'
- rep1 T6-paginate selfbrowse-json: stopped after 15 steps without finishing
- rep1 T6-paginate selfbrowse-native: stopped after 15 steps without finishing
- rep1 T7-live-hn selfbrowse-json: stopped after 15 steps without finishing
- rep1 T8-live-wiki selfbrowse-json: stopped after 15 steps without finishing
- rep1 T8-live-wiki selfbrowse-native: stopped after 15 steps without finishing
- rep2 T2-search selfbrowse-json: wrong answer: '$34.50'
- rep2 T3-navigate selfbrowse-native: wrong answer: 'done with success=true'
- rep2 T4-cart selfbrowse-json: wrong answer: 'Desk Lamp added'
- rep2 T6-paginate selfbrowse-json: stopped after 15 steps without finishing
- rep2 T6-paginate selfbrowse-native: stopped after 15 steps without finishing
- rep2 T7-live-hn selfbrowse-json: wrong answer: 'What I run on my $10 USD OpenStick homelab'
- rep2 T8-live-wiki selfbrowse-json: stopped after 15 steps without finishing
- rep2 T8-live-wiki selfbrowse-native: stopped after 15 steps without finishing
