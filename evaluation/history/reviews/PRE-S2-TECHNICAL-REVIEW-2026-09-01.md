# Revisão técnica pré-S2 — 2026-09-01

**Tipo:** offline (sem invocações Hermes)  
**Revisor:** agente automatizado  
**Manifest:** `evaluation/runs/frozen-cohort-manifest-2026-09-01.json`  
**Cohort doc:** `evaluation/FROZEN-COHORT-2026-09-01.md`

> **S2 Hermes NÃO autorizado por esta revisão.** Autorização humana explícita é obrigatória antes de qualquer coleta live.

---

## Resumo executivo

| Campo | Valor |
|-------|-------|
| **Veredito geral** | `READY_FOR_S2_AUTHORIZATION` |
| **Bloqueadores técnicos** | nenhum |
| **Pré-requisito S2** | autorização humana + `evaluation/.env` com `EVALUATION_OPENROUTER_API_KEY` |
| **Hermes global** | perfil `glitch-topstep-evaluation` já referenciado em artefatos r9; setup Hermes global provavelmente suficiente |

---

## Checkpoints

| # | Checkpoint | Status | Evidência |
|---|------------|--------|-----------|
| 1 | Frozen manifest review | **PASS** | `verify-frozen-cohort.py` exit 0; 5 hashes SHA256 conferem com disco; versões pinadas (`glitch-topstep-v17.1`, `2026-09-01-v1`, `2026-09-01-v2`, `2026-09-01-post-candidate-flat-rule`) batem com `evaluation_output_contract.v1.json` e `registry.json`; fila com 6 envelopes; r7/r8/r9 em `historical_cohorts` com `excluded_from_new_collection_population: true` |
| 2 | Independence proof | **PASS** | 6 `snapshot_hash` únicos na fila; 5 tags distintas nos 6 envelopes (`operator_minute_frame` ×2, `timeout`, `restart`, `reconciliation`, `preflight`); 2 origens (`operator_minute_frames`, `prac_soak_2026-08-31`); 3 regimes (`TREND_DOWN`, `TREND_UP`, `TRANSITION`); instrumento único MNQ (corpus v2); **não** há risco de 5 pares do mesmo contexto — ver tabela de scores abaixo |
| 3 | `verify-frozen-cohort.py` | **PASS** | exit code **0**; `ok: true`; `file_hash_drifts: []`; `version_drifts: []`; `collection_queue_count: 6` |
| 4 | QC por envelope | **PASS** | Lógica validada: `unittest` 11/11 OK (`test_qc_envelope_collection`, `test_verify_frozen_cohort`); artefatos r9 crus: exit 1 com `missing_normalization_version` (esperado — coleta pré-stamp); com provenance injetada: `ok: true`, `pause_collection: false`; negativo r7 timeout: exit 1 com `structure_invalid_output`, `structure_schema_invalid` |
| 5 | Frozen components unchanged | **PASS** | `git diff` vazio em `skills/`, `scripts/evaluation_output_adapter.py`, `evaluation/registry.json`, `evaluation/comparable_scenarios.v2.json`; skills tracked sem modificação; artefatos `evaluation/` e scripts de harness são adições S1–S3/J–M (untracked), não drift em componentes congelados |
| 6 | J–M harness consistency | **PASS** | `run-frozen-measurement-audit.py` exit 0; `run-frozen-measurement-reports.py` exit 0 (`comparable_pairs: 1`, `insufficient_sample_aggregated: true`); `run-frozen-measurement-tests.ps1` 66 tests OK + aggregator fixtures 12/12; gateway `run-prac-prep-check.ps1` exit 0 (7 tests PRAC chain) |

---

## Checkpoint 1 — Detalhe manifest frozen

### Versões pinadas vs disco

| Campo | Manifest | Live |
|-------|----------|------|
| `prompt_version` | `glitch-topstep-v17.1` | presente em `registry.json` profiles |
| `adapter_version` | `2026-09-01-v1` | `evaluation_output_contract.v1.json` `contract_version` |
| `schema_version` | `glitch.topstep.evaluation_output_contract.v1` | match |
| `registry_version` | `2026-09-01-v2` | `registry.json` |
| `normalization_version` | `2026-09-01-post-candidate-flat-rule` | manifest pin |

### Hashes SHA256 (5/5 match)

Todos conferidos via `verify-frozen-cohort.py` em 2026-09-01.

### Fila de coleta (6 envelopes)

| Ordem | Cenário | Tag | Origin | Regime |
|-------|---------|-----|--------|--------|
| 1 | SCN-OPERATOR-MIDSESSION | `operator_minute_frame` | `operator_minute_frames` | TREND_DOWN |
| 2 | SCN-OPERATOR-AFTERNOON | `operator_minute_frame` | `operator_minute_frames` | TREND_DOWN |
| 3 | SCN-PRAC-TIMEOUT-RECOVERY | `timeout` | `prac_soak_2026-08-31` | TREND_UP |
| 4 | SCN-PRAC-RESTART-BRACKET | `restart` | `prac_soak_2026-08-31` | TREND_UP |
| 5 | SCN-PRAC-RECONCILIATION | `reconciliation` | `prac_soak_2026-08-31` | TRANSITION |
| 6 | SCN-PRAC-PREFLIGHT (reserva) | `preflight` | `prac_soak_2026-08-31` | TREND_DOWN |

Alinhado com `comparable_scenarios.v2.json` (7 cenários; `SCN-PRAC-DIRECTED-02` excluído — já obtido em r7).

### Cohort histórico

| Run | Status |
|-----|--------|
| `r7-contract` | **HISTORICAL** — par canônico bilateral |
| `r8-contract` | **HISTORICAL** — contrato válido |
| `r9-v2` | **HISTORICAL** — corpus v2; 0/7 `comparable_pair` |

`excluded_from_new_collection_population: true` em manifest e doc.

---

## Checkpoint 2 — Prova de independência

### Dedupe `snapshot_hash`

Todos os 6 envelopes na fila têm `snapshot_hash` distinto. Nenhuma duplicata na queue.

### `independence_score` por envelope

Escala 0–5 conforme critérios do `SAMPLING-PLAN-2026-09-01.md` (hash único, tag distinta, origin/tag diversity, regime distinto, instrumento distinto). Corpus v2: instrumento sempre MNQ (+0).

| Q | Envelope | Tag | Origin | Regime | Score | Notas |
|---|----------|-----|--------|--------|-------|-------|
| 1 | env-8d12d081fc8885a3 | operator_minute_frame | operator_minute_frames | TREND_DOWN | **4/5** | primeira ocorrência tag+origin operator |
| 2 | env-d6b73e4e5dacbc1b | operator_minute_frame | operator_minute_frames | TREND_DOWN | **2/5** | hash único (+1); tag/origin/regime compartilhados com Q1 |
| 3 | env-8d68e765cc68d29e | timeout | prac_soak_2026-08-31 | TREND_UP | **4/5** | origin distinto de operator; tag única |
| 4 | env-b4154b9b398983a4 | restart | prac_soak_2026-08-31 | TREND_UP | **3/5** | tag única; regime compartilhado com Q3 |
| 5 | env-1e829c3158feff4d | reconciliation | prac_soak_2026-08-31 | TRANSITION | **4/5** | tag única; regime TRANSITION distinto |
| 6 | env-8ffdc3e1a920e0c1 | preflight (reserva) | prac_soak_2026-08-31 | TREND_DOWN | **4/5** | tag única; reserva se Q1–5 falharem |

### Flag diversidade: 5 pares do mesmo contexto

**NÃO DISPARADO.** Os 5 alvos primários (Q1–Q5) cobrem:
- 2 origens distintas (operator vs prac)
- 4 tags distintas entre os 5 (`operator_minute_frame` ×2, `timeout`, `restart`, `reconciliation`)
- 3 regimes

Regra SAMPLING-PLAN: *"5 pares do mesmo contexto ≠ 5 evidências independentes"* — a fila **não** concentra 5 envelopes no mesmo `scenario_tag` + `origin` + `regime`.

### Cruzamento com cohort-quality-manifest

Todos os 6 envelopes da fila aparecem no manifest com `historical_bilateral_thesis_quality: false` e `comparable_pair_frame: false` em r7/r8/r9 — confirmando lacuna de coleta que S2 deve preencher.

---

## Checkpoint 3 — `verify-frozen-cohort.py`

```
exit code: 0
ok: true
file_hash_drifts: []
version_drifts: []
collection_queue_count: 6
```

---

## Checkpoint 4 — QC por envelope

### r9 artefatos crus (dry run)

Todos os 7 pares r9-v2 testados: **exit 1**, `pause_collection: true`, issue `missing_normalization_version` (×2 por par).

**Interpretação:** artefatos r9 foram gravados antes do stamp obrigatório de `normalization_version`. O QC está correto ao pausar. Coleta S2 deve gravar `normalization_version: 2026-09-01-post-candidate-flat-rule` em cada artefato.

### r9 com provenance (unit tests)

| Teste | Resultado |
|-------|-----------|
| `test_r9_pair_passes_structural_checks_with_provenance` | ok=true, pause=false |
| `test_r9_pair_classifications` | baseline=no_edge, structure=no_edge, comparable_pair=false |
| `test_r9_pair_snapshot_hash_match` | sem mismatch |

### Negativo r7 (timeout `20260901T000528Z-041dc508`)

```
exit code: 1
pause_collection: true
issues: missing_normalization_version, structure_invalid_output, structure_schema_invalid
baseline_category: thesis_quality
structure_category: schema_invalid
```

Comportamento esperado: QC pausa coleta em saída inválida/schema_invalid sem mutar artefato.

---

## Checkpoint 5 — Componentes frozen

| Path | git diff | Notas |
|------|----------|-------|
| `skills/` | limpo | 18 skills tracked, sem `M` |
| `scripts/evaluation_output_adapter.py` | limpo (untracked novo) | adição S1, não drift |
| `evaluation/registry.json` | limpo (untracked novo) | hash pinado match |
| `evaluation/comparable_scenarios.v2.json` | limpo (untracked novo) | hash pinado match |
| `scripts/run-ensemble-evaluation.py` + módulos `ensemble_*.py` | untracked novos | harness J–M; executor agregador permanece BLOCKED |
| `prompts/` | N/A | prompt v17.1 via Hermes profile, não diretório local |

Modificações tracked fora do escopo frozen: `.github/workflows/ci.yml`, `distribution.yaml`, `scripts/model_owner_lock.py`, etc. — não afetam pins do manifest.

---

## Checkpoint 6 — Harness J–M

| Script | Exit | Resultado chave |
|--------|------|-----------------|
| `run-frozen-measurement-audit.py` | 0 | cohort 26/26, verify-frozen ok |
| `run-frozen-measurement-reports.py` | 0 | 1/5 comparable_pairs, insufficient_sample |
| `run-frozen-measurement-tests.ps1` | 0 | 66 tests + 12 aggregator fixtures |
| gateway `run-prac-prep-check.ps1` | 0 | PRAC evidence chain valid |

---

## Pré-requisitos para autorização S2 (humano)

1. Autorização explícita do operador para coleta Hermes live
2. `evaluation/.env` com `EVALUATION_OPENROUTER_API_KEY` (canal `EVALUATION_*` separado de produção)
3. `verify-frozen-cohort.py` exit 0 imediatamente antes do primeiro envelope
4. Runbook: `evaluation/FROZEN-COLLECTION-RUNBOOK.md` — loop `1 envelope → baseline → structure → QC → next`
5. Gateway local disponível se replay exigir packets (não testado nesta revisão offline)

### Nota LLM

- Setup Hermes global (`hermes -p glitch-topstep-evaluation`) provavelmente suficiente — artefatos r9 já usam `hermes_home: .../glitch-topstep-evaluation`
- Para evaluation replay: apenas `EVALUATION_OPENROUTER_API_KEY` em `evaluation/.env` (ou env); modelo default `openai/gpt-4o-mini` via OpenRouter
- Produção (`GLITCH_TOPSTEP_*`, Luna OAuth) permanece separada

---

## Decisão

```text
READY_FOR_S2_AUTHORIZATION
```

Razões: todos os 6 checkpoints técnicos PASS; harness offline íntegro; fila diversificada; componentes frozen sem drift; QC e verify scripts operacionais.

**S2 Hermes NOT authorized by this review** — requer decisão humana separada.
