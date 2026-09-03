# Gate de amostra e qualidade — spec congelada

**Status:** `frozen_pre_interpretation`  
**Artefato normativo:** `evaluation/sample_quality_gate.v1.json`  
**Referência thresholds:** `evaluation/ensemble_config.json` → `promotion_thresholds`, `promotion_threshold_semantics`

Critérios definidos **antes** de interpretar novos runs. Relatórios offline (`report-evaluation-runs-comparison.py`) devem expor numerator/denominator; este documento define quando conclusões de promoção ou regressão são **permitidas** vs **bloqueadas**.

## 1. Amostra mínima global

| Critério | Valor | Notas |
|----------|-------|-------|
| `min_comparable_pairs_count` | **5** | Pares baseline+challenger com `comparable_pair: true` no bundle |
| `min_scenario_frames` | **7** | Frames distintos no corpus ativo (v2 = 7 cenários) |
| `min_invocations_per_profile` | **7** | Uma invocação por cenário por perfil filtrado |

Condição `insufficient_sample` quando **qualquer** limite global falha.

## 2. Cobertura por dimensão

### `scenario_tag` (obrigatório)

Cada `scenario_tag` presente no corpus ativo (`comparable_scenarios.v2.json`) exige **≥ 1** frame com invocação completa para **ambos** perfis (`baseline-current`, `structure`).

Tags v2: `prac_directed_test`, `operator_minute_frame`, `timeout`, `restart`, `reconciliation`, `preflight`.

### `instrument` (obrigatório quando instrumento identificável)

`min_samples_per_instrument`: **20** (espelha `ensemble_config.promotion_thresholds`).

Abaixo de 20: apenas `instrument_level_stability_review_only` — **não** promoção.

Instrumento derivado de `envelope.instrument` ou `capacity_gate` no artefato; invocações sem instrumento não contam para cobertura por instrumento.

### `regime` (opcional)

Quando `regime` ou `market_regime` está disponível no envelope:

- `min_samples_per_regime`: **30** (espelha `ensemble_config`)
- Abaixo de 30: diagnóstico por regime apenas; **não** conclusão de promoção por regime

Quando regime **não** está disponível: dimensão ignorada; não falha o gate por ausência de campo.

## 3. Denominadores de `thesis_quality`

### Exclusões obrigatórias do denominador de categoria `thesis_quality`

Invocações com categoria `not_comparable` (via `classify_candidate` ou `normalized.comparability == not_comparable`) **não** entram no denominador de taxa de `thesis_quality` por invocação.

Igualmente excluídos do denominador de qualidade de tese por invocação:

- `missing_required_evidence`
- `error`, `timeout`, `invalid` (adapter)
- `schema_invalid`

### Par bilateral (`comparable_pair`)

Métricas de **qualidade de tese comparativa** (direction_delta, thesis_delta, regressão vs baseline) usam denominador **apenas** `comparable_pair: true`:

- `thesis_quality_pair_rate` = pares comparáveis / frames com ambos perfis presentes
- `direction_delta_rate` = direction_delta / comparable_pairs
- `thesis_delta_rate` = thesis_delta / comparable_pairs

Frames onde um perfil é `no_edge` e outro `thesis_quality` produzem `comparable_pair: false` — contam no denominador de frames, **não** no denominador de par comparável.

## 4. `no_edge` — divergência válida, não falha

- `no_edge` com `comparability: comparable` é **saída contratual válida**, não `invalid` nem falha de perfil.
- `no_edge` vs `thesis_quality` no mesmo frame = **divergência cognitiva categórica** (`cognitive_divergence`), não defeito de contrato.
- `no_edge_rate` denominador = invocações com estado normalizado válido (exclui `invalid` adapter-only).
- Divergência `no_edge` ↔ `held`/`candidate` **não** bloqueia gate de contrato; pode bloquear conclusões de **superioridade** de tese.

## 5. Métricas `thesis_quality` (somente `comparable_pair`)

Quando `comparable_pair: true`:

| Métrica | Definição |
|---------|-----------|
| `direction_agreement` | baseline.direction == challenger.direction |
| `thesis_delta` | flag do comparador (`ensemble_compare.compare_frame_profiles`) |
| `geometry_valid` | ambos candidatos com entry+stop quando direction ∈ {long, short} |

Agregado permitido somente com `comparable_pairs_count ≥ min_comparable_pairs_count`.

## 6. Estabilidade intra-perfil

Referência: `promotion_threshold_semantics` em `ensemble_config.json`.

| Métrica | Threshold | Denominador |
|---------|-----------|-------------|
| `intra_profile_direction_agreement_min` | 0.75 | `replays_with_comparable_envelope` excluindo states em `exclude_states` |
| `intra_profile_state_agreement_min` | 0.80 | idem |

`exclude_states` (direction): `missing_required_evidence`, `error`, `timeout`, `invalid`, `data_quality_insufficient`.

`exclude_states` (state): `error`, `timeout`, `invalid`.

Sem reruns intra-perfil (`groups_with_multiple_reruns == 0`): estabilidade **não avaliada** — placeholder; não PASS automático.

## 7. Comparação baseline

- Baseline fixo: `baseline-current` (registry `baseline_policy`).
- Challenger padrão para gate: `structure`.
- `max_regression_vs_baseline_net_return`: 0.15 — fração relativa, `gate_role: promotion_blocker`.
- Regressão só calculável com `comparable_pair` e métrica de retorno disponível; caso contrário: **blocked_insufficient_evidence**.
- Correlação pairwise (`max_pairwise_direction_correlation`): diagnóstico apenas — não bloqueia v1.

## 8. Condição `insufficient_sample`

Emitir quando:

1. `comparable_pairs_count < min_comparable_pairs_count` (5), **ou**
2. Cobertura `scenario_tag` incompleta, **ou**
3. `invocation_count` filtrado < `min_invocations_per_profile` × perfis, **ou**
4. Corpus ativo tem frames sem invocação para ambos perfis.

### Conclusões **BLOQUEADAS** sob `insufficient_sample`

- Promoção de perfil challenger (`structure` → produção ou shadow armado)
- Declaração de **superioridade cognitiva** estruturada vs baseline
- Gate PASS em `qualidade cognitiva` para promoção
- Regressão baseline como blocker de promoção
- Conclusão de estabilidade intra-perfil suficiente para promoção
- Agregador executável / paralelismo / shadow

### Conclusões **PERMITIDAS** sob `insufficient_sample`

- Contrato de saída por invocação (`contract_validity`)
- Custo e latência por sessão
- Divergência categórica observacional (`no_edge` vs `held`) como **hipótese**, não veredito
- Preservação de evidência histórica (r7 canônico)
- Auditoria de proveniência e drift de normalização

## 9. Estado atual (2026-09-01)

| Run | comparable_pairs | insufficient_sample |
|-----|------------------|-------------------|
| r7-contract | 1/3 | sim |
| r8-contract | (ver bundle) | sim |
| r9-v2 | 0/7 | sim |

Nenhum run isolado satisfaz gate de amostra para promoção.

## Comandos

```powershell
python scripts/report-evaluation-runs-comparison.py
python scripts/audit-artifact-provenance.py
python -m unittest tests.test_evaluation_runs_comparison -v
```
