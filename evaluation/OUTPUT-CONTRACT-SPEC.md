# Contrato de saída — evaluation replay

**Status:** `approved_for_evaluation_replay`  
**Artefato:** `evaluation/evaluation_output_contract.v1.json`  
**Adapter:** `scripts/evaluation_output_adapter.py`

## Problema revelado pelo r6

O Hermes devolveu `state` como snapshot de mercado (objeto) ou tokens de lifecycle (`frozen`, `active`), não o vocabulário `normalized_candidate.v1`. Isso produziu `schema_invalid` com envelope comparável válido.

## Classificação de saídas (inspeção r6)

| Categoria | Exemplo r6 | Tratamento |
|-----------|------------|------------|
| `contract_violation` | `state` = dict com quote/market | `invalid` + `state_field_contains_snapshot` |
| `ambiguous_output` | `frozen`, `active`, `BEARISH`, `neutral` | `invalid` + código específico |
| `incomplete_output` | `thesis` ausente | `invalid` |
| `directional_without_geometry` | `state=candidate` sem stop/entry | `invalid` |
| `semantic_alias_candidate` | campos explícitos no vocabulário | mapear aliases aprovados |

## Vocabulário canônico (prompt)

**state** (string obrigatória): `candidate`, `held`, `no_edge`, `data_quality_insufficient`, `expired`, `timeout`, `error`

**direction** (string obrigatória): `long`, `short`, `flat`, `hold`

**Geometria obrigatória** quando `state` ∈ `{candidate, held}`: `entry` + `stop`; `target` ou `target_absence_reason` conforme estado.

## Aliases aprovados (adapter apenas)

Estados: `NO_EDGE`→`no_edge`, `DATA_DEGRADED`→`data_quality_insufficient`, etc. — ver JSON.

Direções: `LONG`/`SHORT`/`FLAT`/`HOLD` apenas.

## Proibido

- Inferir `no_edge` a partir de `action: NOTHING`
- Inferir `no_edge` a partir de `direction: flat`
- Mapear `BEARISH`/`BULLISH` para short/long sem geometria
- Default silencioso quando `state` ausente

## Preservação de auditoria

- `raw_profile_output` intacto no artefato
- `profile_declared_state` / `profile_declared_direction` preservam valores brutos (serializados se objeto)
- `invalid` é saída do adapter, não vocabulário do LLM

## manifest_snapshot_hash_stale

Não bloqueia replay quando:

- `packet_id` e timestamps batem com o frame
- `computed_snapshot_hash` == `envelope.snapshot_hash`

Manifest stale é metadata degradada (`manifest_trust: degraded`), não altera comparabilidade do envelope construído a partir do frame.

## Próximo gate

`thesis_quality` somente quando baseline + structure produzirem estados válidos ≠ `invalid`, `comparability: comparable`, geometria válida se direcional.
