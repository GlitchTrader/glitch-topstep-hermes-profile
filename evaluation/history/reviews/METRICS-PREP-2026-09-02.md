# Preparação de métricas — correlação, estabilidade, custo

**Data:** 2026-09-02  
**Escopo:** definir campos pós-r14 v5.1; **não** executar agregador

---

## Scripts existentes

| Métrica | Script | Artefato |
|---------|--------|----------|
| Gate amostra | `apply-sample-quality-gate.py` | `sample-quality-gate-result-*.json` |
| Qualidade agregada | `report-evaluation-quality.py` | `evaluation-quality-report-*.json` |
| Comparação multi-run | `report-evaluation-runs-comparison.py` | `evaluation-runs-comparison-*.json` |
| Custo | `audit-evaluation-cost.py` | custo por run_id |
| Proveniência | `audit-artifact-provenance.py` | drift hashes |
| Diversidade | embutido em quality report | `no_edge_rate`, `valid_output_rate` |

---

## Campos a extrair pós-r14 v5.1

### Correlação / comparabilidade

| Campo | Uso |
|-------|-----|
| `comparable_pair` por frame | numerador gate |
| `thesis_delta` | diversidade narrativa (não desempate agregador) |
| `direction_delta` | raro; auditar se aparecer |
| `baseline_category` / `challenger_category` | diagnóstico `no_edge` |

### Estabilidade

| Campo | Uso |
|-------|-----|
| `normalized.state` por perfil × frame | repetibilidade categoria |
| `manifest_trust` | degraded vs ok |
| `capacity_gate_comparable` | filtro pré-replay |

### Custo

| Campo | Uso |
|-------|-----|
| `estimated_cost_usd` por invocação | budget r14 |
| `session_cost_usd` agregado | vs r13 ($0.18 / 16) |
| `cost_gate_passed` | stop se false |

---

## Baseline r14 (referência)

| Métrica | r14 v5.1 | Histórico r7–r13 |
|---------|----------|------------------|
| `no_edge_rate` | **94.4%** | ~70% |
| `invalid_rate` | **0%** | ~1.5% |
| `comparable_pair` (run) | **0/9** | 2/5 agregado |
| `missing_required` | **0** | esporádico |
| `direction_divergence` | **0** | — |
| Custo / 18 inv | **$0.203** | r13: $0.18/16 |
| Latência média | ~12–16s | similar |

### Métricas a extrair na próxima coorte

| Métrica | Script / fonte |
|---------|----------------|
| `no_edge_rate` por perfil | `*-diversity-metrics.json` |
| `missing_required_evidence` | quality report / normalized |
| `direction_delta` | `scenario_comparisons` |
| Estabilidade intra-perfil | mesmo `frame_id` em runs distintos (futuro) |
| Latência / custo | artefatos por invocação |

### Congelado

- `aggregator_rules.v1.json` · spec MD · fixtures 12/12 — **sem alteração** por n=2 ou r14 `no_edge`.

---

## Pós-r14 (checklist)

```powershell
python scripts/report-evaluation-runs-comparison.py --include-run <r14_run_id>
python scripts/audit-evaluation-cost.py
python scripts/apply-sample-quality-gate.py
python scripts/report-evaluation-quality.py
```

Comparar: `comparable_pairs.count` vs 2; `no_edge_rate` nos 8 espontâneos v5.1.
