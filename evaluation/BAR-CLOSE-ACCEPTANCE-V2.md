# Bar Close Acceptance V2

`bar_close_acceptance_v2` mantém o fechamento da barra como gatilho, continua exigindo `prior_completed_bar` e nunca aceita `quote_geometry_invalid` como amostra válida.

Status: **aprovado para PR offline** — **não autorizado para execução live**.

## Defaults (bounded)

| Parâmetro | Default | Justificativa |
|-----------|---------|---------------|
| `required_samples` | `5` | Mesmo limiar de estabilidade da v1; cinco closes válidos. |
| `post_close_window_seconds` | `5` | Janela civil pós-close; nunca ampliada silenciosamente. |
| `provider_roll_latency_seconds` | `10` | Grace explícita para roll ProjectX ancorado em `prior_completed_bar`. |
| `max_duration_seconds` | `600` | Orçamento da janela de amostras válidas (10 min). |
| `max_warmup_seconds` | `120` | Sync inicial bounded antes de contar amostras. |
| `max_total_boundaries` | `12` | Teto de closes tentados (≈12 min); impede retry infinito. |
| `max_total_duration_seconds` | `720` | `600 + 120`; teto wall-clock total da corrida v2. |

Nenhum desses defaults é espera indefinida. Estourar boundary/tempo → `BLOCKED_DATA_QUALITY`.

## Regras operacionais

- `quote_geometry_invalid` no boundary vira `invalid_quote_sample` e é descartado;
- a amostra inválida **nunca** vira `no_edge`;
- na lane de evaluation/soak, ciclo com quote inválido → `deferred_data_quality`;
- o gate aguarda o próximo quote válido **somente** dentro da janela pós-close do boundary atual;
- boundaries inválidos transitórios **não** reiniciam a contagem de amostras válidas;
- ausência de `prior_completed_bar` bloqueia;
- timeout de `/packet`, divergência health/packet, `state_complete=false` (sem quote geometry) e capacidade inválida bloqueiam;
- se não houver 5 amostras válidas dentro dos limites → `BLOCKED_DATA_QUALITY`, não PASS.

## Integração (sem segundo orquestrador)

Reutiliza a lane existente:

- runners: `run-trail-a-parallel-live-evaluation.py`, `shadow-observe-live.py`, `run-parallel-ensemble-evaluation.py`;
- lease / HERMES_HOME: `evaluation_lease.py`, `evaluation_owner.py`;
- agregador: `ensemble_aggregator.py` + `aggregator_rules.v1.json`;
- acceptance: `run-product-acceptance-gates.py`.

`scripts/deferred_data_quality_soak_lane.py` só define config + checkpoint/resume + T0 após o primeiro ciclo válido. Não inicia PRAC, não envia intents/orders e não escreve caminhos de produção.

## Campos novos no relatório do gate

- `acceptance_policy`
- `invalid_quote_samples`
- `total_boundaries_observed`
- `max_total_boundaries`
- `max_total_duration_seconds`
