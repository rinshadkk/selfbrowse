# Benchmark: model `claude-haiku-4-5`, 2 runs per task, max 15 steps

## Overall

| Library | Success | Model calls (avg) | Sent tokens (avg, est.) | API input tokens (avg, billed) | First-call tokens (avg) | Wall s (avg) |
|---|---|---|---|---|---|---|
| browser-use | 7/12 (58%) | 7.3 | 70,133 | 79,060 | 10,282 | 47 |
| selfbrowse | 11/12 (92%) | 6.9 | 11,452 | 13,831 | 925 | 11 |

## Per task (successes / runs, avg sent tokens)

| Task | browser-use | selfbrowse |
|---|---|---|
| T1-read-text | 2/2 · 32,884 tok · 4.0 calls | 2/2 · 3,507 tok · 3.0 calls |
| T2-search | 2/2 · 47,326 tok · 5.5 calls | 2/2 · 23,863 tok · 12.0 calls |
| T3-navigate | 1/2 · 96,622 tok · 10.0 calls | 2/2 · 9,667 tok · 6.5 calls |
| T4-cart | 1/2 · 84,388 tok · 8.5 calls | 1/2 · 12,746 tok · 8.0 calls |
| T5-login | 1/2 · 61,114 tok · 6.5 calls | 2/2 · 6,906 tok · 5.0 calls |
| T6-paginate | 0/2 · 98,464 tok · 9.5 calls | 2/2 · 12,026 tok · 7.0 calls |

## Failures

- rep1 T4-cart selfbrowse: wrong answer: 'The Desk Lamp has been successfully added to the cart.'
- rep1 T5-login browser-use: 1 validation error for AgentOutput
action
  Field required [type=missing, input_value={'thinking': '\nThe user ...les_to_display": []}}]'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing
- rep1 T6-paginate browser-use: 1 validation error for AgentOutput
action
  Field required [type=missing, input_value={'thinking': '\nLet me an...les_to_display": []}}]'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing
- rep2 T3-navigate browser-use: 1 validation error for AgentOutput
action
  Field required [type=missing, input_value={'thinking': '\nLet me an...lay": []}}]\n</invoke>'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing
- rep2 T4-cart browser-use: 1 validation error for AgentOutput
action
  Field required [type=missing, input_value={'thinking': '\nThe user ...s_to_display": []}}]\n'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing
- rep2 T6-paginate browser-use: 1 validation error for AgentOutput
action
  Field required [type=missing, input_value={'thinking': '\nLet me an...les_to_display": []}}]'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing
