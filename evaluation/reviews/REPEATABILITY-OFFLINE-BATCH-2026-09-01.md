# Repeatability offline — batch r7+r8+r9 (2026-09-01)

**Escopo:** pipeline adapter + capacity gate; **sem** Hermes, **sem** LLM.  
**Script:** `scripts/repeatability-offline-check.py --scan-cohort`  
**Relatório:** `evaluation/runs/repeatability-offline-batch-2026-09-01.json`

## Veredito

| Métrica | Valor |
|---------|-------|
| Artefatos | **26/26** |
| Pipeline estável (`adapter_stable`) | **26/26** |
| Hash envelope/snapshot estável | **26/26** |
| `matches_stored_normalized` | **23/26** |
| Drift histórico conhecido (r7) | **3** |
| Drift inesperado | **0** |
| **passed** | **true** |

## Normalização, classificação e métricas idênticas

Para cada artefato, dois re-runs do adapter sobre o mesmo `raw_profile_output` + `capacity_gate` produzem slice idêntico (`state`, `direction`, `comparability`, `error_code`, `capacity_gate_reason`). Campos `envelope_hash_before/after` e `snapshot_hash_before/after` permanecem estáveis em todos os 26.

## Outputs históricos preservados

Três artefatos r7 **não** foram reescritos; o `normalized` armazenado difere do adapter atual por design (`candidate`+`flat` pré-guarda):

1. `scenario-live-2026-09-01-r7-contract-baseline-current-20260901T000528Z-041dc508.json`
2. `scenario-live-2026-09-01-r7-contract-baseline-current-20260901T134026Z-bb50bbe9.json`
3. `scenario-live-2026-09-01-r7-contract-structure-20260901T000528Z-041dc508.json`

`drift_reason`: `candidate_flat_pre_guard_stored_as_candidate`. Pipeline offline continua estável (duplo re-run idêntico); apenas o match com `normalized` persistido falha.

## Separação: drift de versão vs instabilidade LLM

| Tipo | Evidência | Contagem |
|------|-----------|----------|
| Drift de normalização (versão adapter) | 3 artefatos r7 listados acima | 3 |
| Instabilidade LLM | **não medida** neste check | — |
| Drift inesperado pós-coleta | `unexpected_stored_drift_paths` vazio | 0 |

Este batch mede **estabilidade de pipeline**, não variância cognitiva entre invocações live. Divergências r9 (`no_edge` vs `held`) são categoria LLM, não falha de repeatability offline.

## Comando

```powershell
python scripts/repeatability-offline-check.py --scan-cohort `
  --output evaluation/runs/repeatability-offline-batch-2026-09-01.json
```
