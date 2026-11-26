# Selfbrowse learning evaluation (qwen3.8-bench)

One run per cell. Success is judged by the shop's state. Tokens are the model's own counts, input plus output.
Calls with no usage reported: 0.

## long-repeat

| # | task | learn | calls | tokens | replayed | seconds | ok |
|---|---|---|---|---|---|---|---|
| 1 | find ZX-4471 run 1 | off | 7 | 10687 | 0 | 53.2 | yes |
| 2 | find ZX-4471 run 2 | off | 7 | 10681 | 0 | 29.1 | yes |
| 3 | find ZX-4471 run 3 | off | 7 | 10681 | 0 | 21.4 | yes |
| 4 | find ZX-4471 run 4 | off | 4 | 5165 | 0 | 12.5 | NO |
| 1 | find ZX-4471 run 1 | on | 5 | 6909 | 0 | 15.4 | NO |
| 2 | find ZX-4471 run 2 | on | 5 | 6946 | 0 | 15.0 | NO |
| 3 | find ZX-4471 run 3 | on | 7 | 10680 | 0 | 26.4 | yes |
| 4 | find ZX-4471 run 4 | on | 9 | 14754 | 0 | 38.2 | yes |

learn=off: mean calls 6.2, mean tokens 9,304, success 3/4

learn=on: mean calls 6.5, mean tokens 9,822, success 2/4

## transfer

| # | task | learn | calls | tokens | replayed | seconds | ok |
|---|---|---|---|---|---|---|---|
| 1 | add Desk Lamp | off | 7 | 8651 | 0 | 22.5 | yes |
| 2 | add Bamboo Tray | off | 8 | 10284 | 0 | 21.2 | yes |
| 3 | add Salt Mill | off | 6 | 7212 | 0 | 15.9 | yes |
| 4 | add Desk Lamp again | off | 7 | 8703 | 0 | 18.1 | yes |
| 1 | add Desk Lamp | on | 7 | 8651 | 0 | 14.2 | yes |
| 2 | add Bamboo Tray | on | 8 | 10099 | 0 | 21.2 | yes |
| 3 | add Salt Mill | on | 6 | 7212 | 0 | 16.6 | yes |
| 4 | add Desk Lamp again | on | 7 | 8703 | 0 | 20.4 | yes |

learn=off: mean calls 7.0, mean tokens 8,712, success 4/4

learn=on: mean calls 7.0, mean tokens 8,666, success 4/4

## long-transfer

| # | task | learn | calls | tokens | replayed | seconds | ok |
|---|---|---|---|---|---|---|---|
| 1 | SKU ZX-4471 | off | 4 | 5245 | 0 | 25.0 | NO |
| 2 | SKU ZX-4435 | off | 5 | 6822 | 0 | 23.3 | yes |
| 3 | SKU ZX-4412 | off | 5 | 6781 | 0 | 16.6 | yes |
| 4 | SKU ZX-4471 again | off | 7 | 10689 | 0 | 35.8 | yes |
| 1 | SKU ZX-4471 | on | 7 | 10686 | 0 | 32.2 | yes |
| 2 | SKU ZX-4435 | on | 5 | 6869 | 0 | 17.6 | yes |
| 3 | SKU ZX-4412 | on | 5 | 6781 | 0 | 23.8 | yes |
| 4 | SKU ZX-4471 again | on | 6 | 8916 | 0 | 38.0 | NO |

learn=off: mean calls 5.2, mean tokens 7,384, success 3/4

learn=on: mean calls 5.8, mean tokens 8,313, success 3/4

## long-multi

| # | task | learn | calls | tokens | replayed | seconds | ok |
|---|---|---|---|---|---|---|---|
| 1 | cheapest per category run 1 | off | 11 | 15753 | 0 | 43.3 | yes |
| 2 | cheapest per category run 2 | off | 11 | 15753 | 0 | 37.9 | yes |
| 3 | cheapest per category run 3 | off | 11 | 15740 | 0 | 40.1 | yes |
| 4 | cheapest per category run 4 | off | 11 | 16074 | 0 | 46.7 | NO |
| 1 | cheapest per category run 1 | on | 11 | 15752 | 0 | 38.8 | yes |
| 2 | cheapest per category run 2 | on | 12 | 17773 | 0 | 46.7 | yes |
| 3 | cheapest per category run 3 | on | 12 | 18746 | 4 | 54.7 | yes |
| 4 | cheapest per category run 4 | on | 16 | 27510 | 4 | 86.9 | yes |

learn=off: mean calls 11.0, mean tokens 15,830, success 3/4

learn=on: mean calls 12.8, mean tokens 19,945, success 4/4
