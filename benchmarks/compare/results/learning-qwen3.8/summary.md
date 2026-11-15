# Selfbrowse learning evaluation (qwen3.8-bench)

One run per cell. Success is judged by the shop's state.

## repeat

| # | task | learn | calls | tokens sent | replayed | seconds | ok |
|---|---|---|---|---|---|---|---|
| 1 | T3 run 1 | off | 7 | 9859 | 0 | 45.9 | yes |
| 2 | T3 run 2 | off | 6 | 8328 | 0 | 17.3 | yes |
| 3 | T3 run 3 | off | 6 | 8305 | 0 | 17.1 | yes |
| 4 | T3 run 4 | off | 6 | 8360 | 0 | 17.4 | yes |
| 1 | T3 run 1 | on | 6 | 8379 | 0 | 18.9 | yes |
| 2 | T3 run 2 | on | 6 | 8333 | 0 | 16.1 | yes |
| 3 | T3 run 3 | on | 6 | 8367 | 3 | 16.8 | yes |
| 4 | T3 run 4 | on | 6 | 8361 | 0 | 16.1 | yes |

learn=off: mean calls 6.2, mean tokens 8,713, success 4/4

learn=on: mean calls 6.0, mean tokens 8,360, success 4/4

## transfer

| # | task | learn | calls | tokens sent | replayed | seconds | ok |
|---|---|---|---|---|---|---|---|
| 1 | add Desk Lamp | off | 7 | 9833 | 0 | 25.1 | yes |
| 2 | add Bamboo Tray | off | 6 | 8350 | 0 | 20.9 | yes |
| 3 | add Salt Mill | off | 8 | 11506 | 0 | 32.7 | yes |
| 4 | add Desk Lamp again | off | 7 | 10007 | 0 | 35.2 | yes |
| 1 | add Desk Lamp | on | 8 | 11561 | 0 | 37.3 | yes |
| 2 | add Bamboo Tray | on | 6 | 8350 | 0 | 26.4 | yes |
| 3 | add Salt Mill | on | 8 | 11597 | 0 | 29.2 | yes |
| 4 | add Desk Lamp again | on | 6 | 8284 | 0 | 22.0 | yes |

learn=off: mean calls 7.0, mean tokens 9,924, success 4/4

learn=on: mean calls 7.0, mean tokens 9,948, success 4/4
