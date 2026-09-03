# Proveniência e drift histórico de normalização

**Status:** `approved_offline_audit`  
**Script:** `scripts/audit-artifact-provenance.py`  
**Sidecar schema:** `glitch.topstep.evaluation_run_provenance.v1`

Registra **como** cada artefato foi normalizado sem alterar JSONs de invocação imutáveis (r7 histórico).

## Princípio

Artefatos `glitch.topstep.minimal_cognitive_replay.v1` em `evaluation/runs/` preservam `raw_profile_output` + `normalized` no momento da gravação. Mudanças no adapter (`evaluation_output_adapter.py`) podem fazer o re-run offline divergir do `normalized` armazenado — isso é **drift de normalização**, não variância LLM.

## Sidecar por run

Para cada bundle run (`r7-contract`, `r8-contract`, `r9-v2`):

`evaluation/runs/{run_id}-provenance.json`

**Não** editar artefatos de invocação existentes; sidecar é metadado auditável.

## Campos de contexto (`normalization_context`)

| Campo | Fonte |
|-------|-------|
| `adapter_version` | `evaluation/evaluation_output_contract.v1.json` → `contract_version` |
| `schema_version` | `glitch.topstep.evaluation_output_contract.v1` |
| `prompt_version` | `evaluation/registry.json` perfil (baseline + structure) |
| `registry_version` | `evaluation/registry.json` → `registry_version` |
| `envelope_schema` | `evaluation/registry.json` → `envelope_schema` |
| `aggregator_rules_version` | `evaluation/aggregator_rules.v1.json` → `rules_version` |
| `normalization_version` | tag operacional atual, ex. `2026-09-01-post-candidate-flat-rule` |

## Classificação por artefato

Para cada artefato listado no sidecar:

| `stored_normalization_version` | Condição |
|--------------------------------|----------|
| `2026-09-01-post-candidate-flat-rule` | re-run adapter == `normalized` armazenado |
| `historical_normalization_version` | re-run adapter ≠ `normalized` armazenado |

`historical_normalization_version` **não** implica reprocessar o artefato; preserva auditoria histórica.

### Drift conhecido (r7, repeatability tests)

Três artefatos r7 predatam a guarda `candidate`+`flat` → `invalid`:

1. `scenario-live-2026-09-01-r7-contract-baseline-current-20260901T000528Z-041dc508.json`
2. `scenario-live-2026-09-01-r7-contract-baseline-current-20260901T134026Z-bb50bbe9.json`
3. `scenario-live-2026-09-01-r7-contract-structure-20260901T000528Z-041dc508.json`

`drift_reason`: `candidate_flat_pre_guard_stored_as_candidate`

Adapter re-run nesses frames produz `invalid` + `directional_without_geometry` ou estado divergente; pipeline adapter permanece estável (duplo re-run idêntico).

## Auditoria agregada

`evaluation/runs/artifact-provenance-audit.json`:

- `scanned_artifact_count`
- `current_normalization_context`
- `runs[]` com resumo por run_id prefix
- `artifacts[]` per-file: `matches_stored_normalized`, `stored_normalization_version`, paths
- `known_historical_drift_artifacts` (lista canônica)

## Novos artefatos (opcional)

`evaluation_cognitive_replay.py` pode incluir `normalization_version` no dict do artefato **novo** (constante one-line). Artefatos históricos sem o campo continuam válidos; proveniência sidecar cobre retroactivo.

## Comando

```powershell
python scripts/audit-artifact-provenance.py
python scripts/audit-artifact-provenance.py --write-sidecars
```
