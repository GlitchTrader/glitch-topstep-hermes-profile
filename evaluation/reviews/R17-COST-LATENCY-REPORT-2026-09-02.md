# Relatório custo e latência — r17 (coorte v9)

**Run:** `scenario-live-2026-09-02-r17-v9`  
**Data:** 2026-09-02  
**Artefato canônico:** `evaluation/runs/scenario-live-2026-09-02-r17-v9-cost-audit.json`

---

## Resumo executivo

| Métrica | Valor |
|---------|-------|
| Invocações | **8/8** |
| `invalid` | **0** |
| Custo total estimado | **$0.08949** |
| Latência p50 | **11 507.5 ms** (quality report) / **11 515 ms** (cost audit) |
| Latência p95 | **14 781 ms** |
| Soma latência | **92 452 ms** (~92.5 s) |
| Dentro orçamento latência (180 000 ms) | **sim** |
| `audit_gate_passed` | **true** |

---

## Custo por invocação

| # | Perfil | frame_id (sufixo) | Custo USD | Latência ms |
|---|--------|-------------------|-----------|-------------|
| 1 | baseline-current | `92f0a8a8` | 0.011198 | 14 781 |
| 2 | structure | `92f0a8a8` | 0.011208 | 9 577 |
| 3 | baseline-current | `08066af5` | 0.011243 | 11 515 |
| 4 | structure | `08066af5` | 0.011193 | 11 922 |
| 5 | baseline-current | `ab6e5383` | 0.011307 | 11 500 |
| 6 | structure | `ab6e5383` | 0.011267 | 12 344 |
| 7 | baseline-current | `c5f24442` | 0.011017 | 10 954 |
| 8 | structure | `c5f24442` | 0.011057 | 9 859 |

**Modelo:** `gpt-5.6-luna` · custo via `estimated_tokens` (8/8).

---

## `no_edge` por perfil

| Perfil | `no_edge` | Total |
|--------|-----------|-------|
| `baseline-current` | 4 | 4 |
| `structure` | 4 | 4 |

**Taxa bilateral alinhada:** 4/4 frames · divergência categoria **0**.

---

## Divergência baseline vs structure

| Métrica | Valor |
|---------|-------|
| `comparable_pair_count` | **0/4** |
| `direction_delta_count` | **0** |
| `thesis_delta_count` | **0** |
| Categoria em todos os frames | `no_edge` / `no_edge` |

Fonte: `evaluation/runs/scenario-live-2026-09-02-r17-v9-quality-report.json`

---

## Comparação com runs recentes

| Run | Invocações | Custo | p50 ms | `comparable_pair` |
|-----|------------|-------|--------|-------------------|
| r15 v7 | 8 | $0.091 | ~11.5k | 0/4 |
| r16 v8 | 6 | $0.067 | ~11.9k | 0/3 |
| **r17 v9** | **8** | **$0.089** | **~11.5k** | **0/4** |

**Leitura:** custo/latência dentro do envelope histórico; abstinência simétrica persiste sem degradar contrato ou orçamento.
