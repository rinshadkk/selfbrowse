# Selfbrowse learning evaluation (qwen3.8-bench)

One run per cell. Success is judged by the shop's state.

## transfer

| # | task | learn | calls | tokens sent | replayed | seconds | ok |
|---|---|---|---|---|---|---|---|
| 1 | add Desk Lamp | off | 7 | 9798 | 0 | 37.2 | yes |
| 2 | add Bamboo Tray | off | 7 | 9908 | 0 | 25.7 | yes |
| 3 | add Salt Mill | off | 7 | 9880 | 0 | 23.2 | yes |
| 4 | add Desk Lamp again | off | 7 | 9860 | 0 | 21.8 | yes |
| 1 | add Desk Lamp | on | 6 | 8308 | 0 | 17.3 | yes |
| 2 | add Bamboo Tray | on | 8 | 11610 | 0 | 27.6 | yes |
| 3 | add Salt Mill | on | 7 | 9907 | 0 | 26.0 | yes |
| 4 | add Desk Lamp again | on | 7 | 9854 | 0 | 34.3 | yes |

learn=off: mean calls 7.0, mean tokens 9,862, success 4/4

learn=on: mean calls 7.0, mean tokens 9,920, success 4/4

## long-repeat

| # | task | learn | calls | tokens sent | replayed | seconds | ok |
|---|---|---|---|---|---|---|---|
| 1 | find ZX-4471 run 1 | off | 6 | 9239 | 0 | 66.1 | NO |
| 2 | find ZX-4471 run 2 | off | 5 | 7441 | 0 | 47.6 | NO |
| 3 | find ZX-4471 run 3 | off | 9 | 15597 | 0 | 79.4 | yes |
| 4 | find ZX-4471 run 4 | off | 7 | 11490 | 0 | 54.6 | yes |
| 1 | find ZX-4471 run 1 | on | 7 | 11197 | 0 | 42.8 | yes |
| 2 | find ZX-4471 run 2 | on | 7 | 11331 | 0 | 36.4 | yes |
| 3 | find ZX-4471 run 3 | on | 3 | 4026 | 4 | 11.9 | yes |
| 4 | find ZX-4471 run 4 | on | 3 | 4025 | 4 | 10.5 | yes |

learn=off: mean calls 6.8, mean tokens 10,942, success 2/4

learn=on: mean calls 5.0, mean tokens 7,645, success 4/4

## long-multi

| # | task | learn | calls | tokens sent | replayed | seconds | ok |
|---|---|---|---|---|---|---|---|
| 1 | cheapest per category run 1 | off | 30 | 70388 | 0 | 200.6 | NO |
| 2 | cheapest per category run 2 | off | 15 | 27287 | 0 | 107.7 | NO |
| 3 | cheapest per category run 3 | off | 13 | 22363 | 0 | 86.2 | NO |
| 4 | cheapest per category run 4 | off | 12 | 20155 | 0 | 64.5 | NO |
| 1 | cheapest per category run 1 | on | 10 | 15628 | 0 | 49.8 | NO |
| 2 | cheapest per category run 2 | on | 13 | 22239 | 0 | 93.8 | NO |
| 3 | cheapest per category run 3 | on | 12 | 19897 | 0 | 64.2 | NO |
| 4 | cheapest per category run 4 | on | 24 | 51757 | 4 | 176.9 | NO |

learn=off: mean calls 17.5, mean tokens 35,048, success 0/4

learn=on: mean calls 14.8, mean tokens 27,380, success 0/4

## long-transfer

| # | task | learn | calls | tokens sent | replayed | seconds | ok |
|---|---|---|---|---|---|---|---|
| 1 | SKU ZX-4471 | off | 5 | 7487 | 0 | 38.7 | NO |
| 2 | SKU ZX-4435 | off | 6 | 9479 | 0 | 33.8 | yes |
| 3 | SKU ZX-4412 | off | 5 | 7506 | 0 | 23.9 | yes |
| 4 | SKU ZX-4471 again | off | 7 | 11520 | 0 | 46.8 | yes |
| 1 | SKU ZX-4471 | on | 9 | 15860 | 0 | 71.4 | yes |
| 2 | SKU ZX-4435 | on | 5 | 7500 | 0 | 29.7 | yes |
| 3 | SKU ZX-4412 | on | 6 | 9493 | 0 | 28.0 | yes |
| 4 | SKU ZX-4471 again | on | 7 | 11357 | 0 | 41.3 | yes |

learn=off: mean calls 5.8, mean tokens 8,998, success 3/4

learn=on: mean calls 6.8, mean tokens 11,052, success 4/4
