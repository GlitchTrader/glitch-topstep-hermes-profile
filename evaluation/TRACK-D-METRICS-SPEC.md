# Track D — Métricas e análise (spec)

**Status:** spec + relatórios offline; sem alteração de prompts ou perfis  
**Script:** `scripts/report-evaluation-metrics.py`  
**Schema saída:** `glitch.topstep.evaluation_metrics_report.v1`

## Dimensões

### 1. Disponibilidade de evidência

Por `profile_id`, contagem de categorias de `ensemble_compare.classify_candidate`:

- `missing_required_evidence`, `not_comparable`, `no_edge`, `thesis_quality`, etc.

Fonte: `capacity_gate.comparable` + `normalized.state` / `comparability`.

### 2. Comparação contra baseline

Por frame (envelope): `compare_frame_profiles` → `baseline_category`, `challenger_category`, `comparable_pair`, `direction_delta`.

Agregado: `comparable_pair_rate` = frames com par comparável / frames comparados.

### 3. Estabilidade intra-perfil

Requer ≥2 reruns do mesmo `(snapshot_hash, profile_id)`.

Métricas: `direction_agreement`, `state_agreement`.

Thresholds de promoção (config only): `intra_profile_direction_agreement_min` 0.75, `intra_profile_state_agreement_min` 0.80.

### 4. Correlação de decisões

Matriz pairwise `direction_match_rate` entre perfis no mesmo frame.

**Diagnóstico apenas** — `max_pairwise_direction_correlation` não bloqueia promoção v1.

### 5. Custo / latência

Por invocação: `latency_ms`, `cost_accounting` (basis, estimated_cost_usd).

Agregado: p50/p95 latência, `session_cost_usd_max`, `cost_gate_failures`, `cost_basis_counts`.

### 6. Relatórios de reexecução

Quando existirem reruns, `intra_profile_stability.agreements` lista campos instáveis.

## Inputs aceitos

| Schema | Uso |
|--------|-----|
| `glitch.topstep.minimal_cognitive_replay.v1` | Invocação individual |
| `glitch.topstep.scenario_live_replay.v1` | Bundle com paths para artefatos |
| `glitch.topstep.dual_profile_live_replay.v1` | Bundle legado r5 |

## Comando

```powershell
python scripts/report_evaluation_metrics.py evaluation/runs/scenario-live-2026-09-01-r6-*.json --run-id scenario-live-2026-09-01-r6
```

Ou automático via `run-scenario-live-replay.py` → `{run_id}-quality-report.json`.

## Separação de faixas

| Faixa | Módulos | Relação com Track D |
|-------|---------|---------------------|
| Evaluation lane | `ensemble_compare`, `evaluation_cost`, `report-evaluation-metrics` | **Este documento** |
| Trail D operacional | `cycle_empirical.py`, `calibration_metrics.py`, `decision_regret.py` | Bridge futuro; não misturar denominadores |

## Não objetivos

- Implementar thresholds de promoção como gates automáticos
- Alterar skills/prompts durante coleta
- Agregador executável
