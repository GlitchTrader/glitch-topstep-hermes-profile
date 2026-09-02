# Insufficient sample report — 2026-09-01

**Gerado:** 2026-09-01T23:54:28.871724Z
**Recomendação:** `more_collection`

## Resumo

| Métrica | Valor |
|---------|-------|
| comparable_pairs_found | 2 / 5 |
| independent_pairs_estimate | 2 |
| insufficient_sample | True |

> 5 pares comparáveis = limiar mínimo de processo (gate frozen), NÃO prova de superioridade estatística cognitiva.

## Cenários (bilateral thesis_quality)

- **Cobertos:** prac_directed_test, reconciliation
- **Faltando:** operator_minute_frame, timeout, restart, preflight

## Regimes

- **Cobertos:** CHOP, TRANSITION
- **Faltando:** TREND_DOWN, TREND_UP

## Exclusões (breakdown)

| motivo | contagem |
|--------|----------|
| `historical_normalization_drift` | 2 |
| `schema_invalid` | 1 |
| `thesis_quality_without_bilateral_pair` | 2 |

## Por run (populações separadas)

| run_id | comparable_pairs | insufficient |
|--------|------------------|------------|
| `scenario-live-2026-09-01-r7-contract` | 1 | True |
| `scenario-live-2026-09-01-r10-v2` | 1 | True |
| `scenario-live-2026-09-01-r11-v2` | 0 | True |

## Artefatos

- Plano de amostragem: `evaluation/SAMPLING-PLAN-2026-09-01.md`
- Cohort manifest: `evaluation/runs/cohort-quality-manifest-2026-09-01.json`
- Coverage gaps: `evaluation/runs/corpus-coverage-gaps-2026-09-01.json`
- Gate result: `evaluation/runs/sample-quality-gate-result-2026-09-01.json`

Promoção e veredito de superioridade cognitiva permanecem **bloqueados**.
