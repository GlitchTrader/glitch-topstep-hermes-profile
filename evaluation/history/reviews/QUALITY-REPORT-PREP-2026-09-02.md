# Relatório de qualidade — preparação para próximos pares

**Data:** 2026-09-02  
**Gate atual:** 2/5 comparáveis · `insufficient_sample`  
**Script:** `report-evaluation-quality.py` · `apply-sample-quality-gate.py`

## Baseline congelado

| Métrica | Valor |
|---------|-------|
| Pares canônicos | 2 |
| Mínimo gate | 5 |
| Invocações históricas (r7–r13) | 66 |
| `no_edge_rate` agregado | ~70% |
| Novos pares necessários | **≥3** espontâneos bilaterais |

## Critério de par (frozen)

`comparable_pair` exige baseline **e** structure em `thesis_quality` (candidate/held comparáveis no mesmo `snapshot_hash`).

**Não contam:**

- `no_edge` ↔ `no_edge`
- `candidate` ↔ `no_edge` (unilateral)
- `not_comparable` / `data_quality_insufficient`
- `prac_directed_execution`

## Template pós-replay (v5+)

Após replay autorizado, regenerar:

```powershell
python scripts/apply-sample-quality-gate.py
python scripts/report-evaluation-quality.py
```

Artefatos esperados:

- `evaluation/runs/sample-quality-gate-result-<date>.json`
- `evaluation/runs/evaluation-quality-report-<date>.json`

## Campos a monitorar por envelope novo

| Campo | Pass |
|-------|------|
| `normalized.state` válido | schema |
| Ambos perfis `comparable: true` | capacity gate |
| `thesis_quality` bilateral | par candidato |
| `session_cost_usd` | dentro budget |
| Proveniência | 0 drift novo |

## Projeção v5

Se 3 novos frames espontâneos gerarem bilateral `thesis_quality`:

- Gate: 2 + 3 = **5/5** → reavaliar `insufficient_sample` (ainda sem promoção automática).

Se apenas `no_edge` bilateral:

- Gate inalterado — continuar `more_collection`.
