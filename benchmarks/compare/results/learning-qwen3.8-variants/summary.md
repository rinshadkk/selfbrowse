# Selfbrowse learning evaluation (qwen3.8-bench)

One run per cell. Success is judged by the shop's state.

## repeat

| # | task | learn | calls | tokens sent | replayed | seconds | ok |
|---|---|---|---|---|---|---|---|
| 1 | T3 run 1 | off | 6 | 8306 | 0 | 40.7 | yes |
| 2 | T3 run 2 | off | 6 | 8357 | 0 | 17.7 | yes |
| 3 | T3 run 3 | off | 6 | 8319 | 0 | 16.6 | yes |
| 4 | T3 run 4 | off | 6 | 8341 | 0 | 17.3 | yes |
| 1 | T3 run 1 | on | 6 | 8332 | 0 | 17.6 | yes |
| 2 | T3 run 2 | on | 6 | 8347 | 0 | 17.7 | yes |
| 3 | T3 run 3 | on | 7 | 10001 | 3 | 20.1 | yes |
| 4 | T3 run 4 | on | 6 | 8341 | 3 | 17.2 | yes |

learn=off: mean calls 6.0, mean tokens 8,331, success 4/4

learn=on: mean calls 6.2, mean tokens 8,755, success 4/4

## transfer

| # | task | learn | calls | tokens sent | replayed | seconds | ok |
|---|---|---|---|---|---|---|---|
| 1 | add Desk Lamp | off | 6 | 8274 | 0 | 21.3 | yes |
| 2 | add Bamboo Tray | off | 6 | 8350 | 0 | 20.1 | yes |
| 3 | add Salt Mill | off | 8 | 11551 | 0 | 28.1 | yes |
| 4 | add Desk Lamp again | off | 6 | 8285 | 0 | 26.0 | yes |
| 1 | add Desk Lamp | on | 5 | 6705 | 0 | 23.8 | yes |
| 2 | add Bamboo Tray | on | 8 | 11631 | 0 | 34.8 | yes |
| 3 | add Salt Mill | on | 6 | 8329 | 1 | 26.4 | NO |
| 4 | add Desk Lamp again | on | 7 | 9858 | 1 | 34.4 | NO |

learn=off: mean calls 6.5, mean tokens 9,115, success 4/4

learn=on: mean calls 6.5, mean tokens 9,131, success 2/4
