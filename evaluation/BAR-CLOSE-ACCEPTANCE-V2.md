# Bar Close Acceptance V2

`bar_close_acceptance_v2` mantém o fechamento da barra como gatilho, continua exigindo `prior_completed_bar` e nunca aceita `quote_geometry_invalid` como amostra válida.

Regras operacionais:

- `quote_geometry_invalid` no boundary vira `invalid_quote_sample`;
- a amostra inválida é descartada e nunca vira `no_edge`;
- o gate continua aguardando o próximo quote válido dentro da janela bounded do boundary atual;
- o processo exige 5 amostras válidas;
- boundaries inválidos transitórios não reiniciam a contagem de amostras válidas;
- o processo para com `BLOCKED_DATA_QUALITY` quando estoura `max_total_boundaries` ou `max_total_duration_seconds`;
- timeouts, divergência health/packet, ausência de `prior_completed_bar`, `state_complete=false` sem `quote_geometry_invalid` e outros bloqueios operacionais continuam bloqueando.

Campos novos no relatório:

- `acceptance_policy`;
- `invalid_quote_samples`;
- `total_boundaries_observed`;
- `max_total_boundaries`;
- `max_total_duration_seconds`.
