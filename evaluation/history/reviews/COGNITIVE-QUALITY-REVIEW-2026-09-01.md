# Revisão cognitiva — qualidade de decisão (2026-09-01)

**Status:** `offline_human_review`  
**Runs revisados:** r7-contract, r8-contract, r9-v2 (separados — sem blend de versões)  
**Gate aplicado:** `evaluation/sample_quality_gate.v1.json` (frozen)  
**Resultado gate:** `evaluation/runs/sample-quality-gate-result-2026-09-01.json`  
**Auditoria proveniência:** `evaluation/runs/provenance-decision-audit-2026-09-01.json`

## Metodologia

Cada invocação classificada em **exatamente uma** categoria:

| Categoria | Uso |
|-----------|-----|
| `evidência de contrato` | Saída adapter válida (incl. `no_edge`, `held`); ou falha de contrato observável (`invalid`/`schema_invalid`) |
| `evidência de capacidade` | Perfil produz tese direcional sem par comparável bilateral |
| `evidência de diversidade` | Divergência cognitiva observável (`thesis_delta`, divergência categórica `no_edge`↔`thesis_quality`) |
| `evidência de qualidade de tese` | Membro de `comparable_pair: true` com ambos `thesis_quality` |
| `evidência inconclusiva` | Drift histórico de normalização ou interpretação bloqueada pelo gate |

Todas as citações incluem path do artefato + `normalization_version` do sidecar `*-provenance.json`.

---

## Run r7 — `scenario-live-2026-09-01-r7-contract`

**Role:** diversidade canônica + primeiro par comparável (SCN-PRAC-DIRECTED-02 `thesis_delta`); corpus v1 (3 cenários).  
**Sidecar:** `evaluation/runs/scenario-live-2026-09-01-r7-contract-provenance.json`  
**Resumo:** 6 invocações, 1/3 `comparable_pair`, 1 `invalid`, 3 artefatos `historical_normalization_version`.

| Invocação | Cenário | Perfil | Classificação | Citação |
|-----------|---------|--------|---------------|---------|
| `20260831T173427Z-4ac91997` | SCN-PRAC-DIRECTED-02 | baseline-current | evidência de qualidade de tese | `evaluation/runs/scenario-live-2026-09-01-r7-contract-baseline-current-20260831T173427Z-4ac91997.json` — `normalization_version`: `2026-09-01-post-candidate-flat-rule` (`scenario-live-2026-09-01-r7-contract-provenance.json`) |
| `20260831T173427Z-4ac91997` | SCN-PRAC-DIRECTED-02 | structure | evidência de diversidade | `evaluation/runs/scenario-live-2026-09-01-r7-contract-structure-20260831T173427Z-4ac91997.json` — `thesis_delta: true` no bundle; `normalization_version`: `2026-09-01-post-candidate-flat-rule` |
| `20260901T134026Z-bb50bbe9` | SCN-OPERATOR-MIDSESSION | baseline-current | evidência inconclusiva | `evaluation/runs/scenario-live-2026-09-01-r7-contract-baseline-current-20260901T134026Z-bb50bbe9.json` — `historical_normalization_version` (`drift_reason`: `candidate_flat_pre_guard_stored_as_candidate`) |
| `20260901T134026Z-bb50bbe9` | SCN-OPERATOR-MIDSESSION | structure | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r7-contract-structure-20260901T134026Z-bb50bbe9.json` — `no_edge` válido; `normalization_version`: `2026-09-01-post-candidate-flat-rule` |
| `20260901T000528Z-041dc508` | SCN-PRAC-TIMEOUT-RECOVERY | baseline-current | evidência inconclusiva | `evaluation/runs/scenario-live-2026-09-01-r7-contract-baseline-current-20260901T000528Z-041dc508.json` — `historical_normalization_version` |
| `20260901T000528Z-041dc508` | SCN-PRAC-TIMEOUT-RECOVERY | structure | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r7-contract-structure-20260901T000528Z-041dc508.json` — `invalid` / `schema_invalid` (1 invocação inválida do run); `historical_normalization_version` |

**Frame SCN-PRAC-DIRECTED-02:** único `comparable_pair` (1/3); `thesis_delta: true` — evidência de diversidade canônica preservada.

---

## Run r8 — `scenario-live-2026-09-01-r8-contract`

**Role:** correção de contrato de saída (adapter v1); corpus v1 (3 cenários).  
**Sidecar:** `evaluation/runs/scenario-live-2026-09-01-r8-contract-provenance.json`  
**Resumo:** 6/6 válidos, 0 `comparable_pair`, 0 drift histórico.

| Invocação | Cenário | Perfil | Classificação | Citação |
|-----------|---------|--------|---------------|---------|
| `20260831T173427Z-4ac91997` | SCN-PRAC-DIRECTED-02 | baseline-current | evidência de capacidade | `evaluation/runs/scenario-live-2026-09-01-r8-contract-baseline-current-20260831T173427Z-4ac91997.json` — `thesis_quality` sem par bilateral; `normalization_version`: `2026-09-01-post-candidate-flat-rule` |
| `20260831T173427Z-4ac91997` | SCN-PRAC-DIRECTED-02 | structure | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r8-contract-structure-20260831T173427Z-4ac91997.json` — `no_edge` válido |
| `20260901T134026Z-bb50bbe9` | SCN-OPERATOR-MIDSESSION | baseline-current | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r8-contract-baseline-current-20260901T134026Z-bb50bbe9.json` — `no_edge` |
| `20260901T134026Z-bb50bbe9` | SCN-OPERATOR-MIDSESSION | structure | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r8-contract-structure-20260901T134026Z-bb50bbe9.json` — `no_edge` |
| `20260901T000528Z-041dc508` | SCN-PRAC-TIMEOUT-RECOVERY | baseline-current | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r8-contract-baseline-current-20260901T000528Z-041dc508.json` — `no_edge` |
| `20260901T000528Z-041dc508` | SCN-PRAC-TIMEOUT-RECOVERY | structure | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r8-contract-structure-20260901T000528Z-041dc508.json` — `no_edge` |

**Leitura:** run confirma contrato de saída estável (100% válidos); sem par comparável — não produz evidência de superioridade cognitiva.

---

## Run r9 — `scenario-live-2026-09-01-r9-v2`

**Role:** adapter atual + corpus v2 (7 cenários); 14/14 válidos, 0 `comparable_pair`, divergências categóricas.  
**Sidecar:** `evaluation/runs/scenario-live-2026-09-01-r9-v2-provenance.json`  
**Resumo:** cobertura v2 completa por tag; baseline 7× `no_edge`; structure 2× `thesis_quality` + 5× `no_edge`.

| Invocação | Cenário | Perfil | Classificação | Citação |
|-----------|---------|--------|---------------|---------|
| `20260831T173427Z-4ac91997` | SCN-PRAC-DIRECTED-02 | baseline-current | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r9-v2-baseline-current-20260831T173427Z-4ac91997.json` — `no_edge`; `normalization_version`: `2026-09-01-post-candidate-flat-rule` |
| `20260831T173427Z-4ac91997` | SCN-PRAC-DIRECTED-02 | structure | evidência de diversidade | `evaluation/runs/scenario-live-2026-09-01-r9-v2-structure-20260831T173427Z-4ac91997.json` — `held`/`thesis_quality` vs baseline `no_edge` |
| `20260901T134026Z-bb50bbe9` | SCN-OPERATOR-MIDSESSION | baseline-current | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r9-v2-baseline-current-20260901T134026Z-bb50bbe9.json` — `no_edge` |
| `20260901T134026Z-bb50bbe9` | SCN-OPERATOR-MIDSESSION | structure | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r9-v2-structure-20260901T134026Z-bb50bbe9.json` — `no_edge` |
| `20260901T000528Z-041dc508` | SCN-PRAC-TIMEOUT-RECOVERY | baseline-current | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r9-v2-baseline-current-20260901T000528Z-041dc508.json` — `no_edge` |
| `20260901T000528Z-041dc508` | SCN-PRAC-TIMEOUT-RECOVERY | structure | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r9-v2-structure-20260901T000528Z-041dc508.json` — `no_edge` |
| `20260831T235211Z-cdbf204f` | SCN-PRAC-RESTART-BRACKET | baseline-current | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r9-v2-baseline-current-20260831T235211Z-cdbf204f.json` — `no_edge` |
| `20260831T235211Z-cdbf204f` | SCN-PRAC-RESTART-BRACKET | structure | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r9-v2-structure-20260831T235211Z-cdbf204f.json` — `no_edge` |
| `20260901T143431Z-534fefd5` | SCN-PRAC-RECONCILIATION | baseline-current | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r9-v2-baseline-current-20260901T143431Z-534fefd5.json` — `no_edge` |
| `20260901T143431Z-534fefd5` | SCN-PRAC-RECONCILIATION | structure | evidência de diversidade | `evaluation/runs/scenario-live-2026-09-01-r9-v2-structure-20260901T143431Z-534fefd5.json` — `held`/`thesis_quality` vs baseline `no_edge` |
| `20260901T182843Z-b06d9a93` | SCN-PRAC-PREFLIGHT | baseline-current | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r9-v2-baseline-current-20260901T182843Z-b06d9a93.json` — `no_edge` |
| `20260901T182843Z-b06d9a93` | SCN-PRAC-PREFLIGHT | structure | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r9-v2-structure-20260901T182843Z-b06d9a93.json` — `no_edge` |
| `20260901T150823Z-d7908a55` | SCN-OPERATOR-AFTERNOON | baseline-current | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r9-v2-baseline-current-20260901T150823Z-d7908a55.json` — `no_edge` |
| `20260901T150823Z-d7908a55` | SCN-OPERATOR-AFTERNOON | structure | evidência de contrato | `evaluation/runs/scenario-live-2026-09-01-r9-v2-structure-20260901T150823Z-d7908a55.json` — `no_edge` |

**Divergências categóricas (2/7 frames):** SCN-PRAC-DIRECTED-02, SCN-PRAC-RECONCILIATION — `no_edge` (baseline) vs `thesis_quality` (structure); não defeito de contrato.

---

## Gate de amostra (pré-registrado)

Fonte: `scripts/apply-sample-quality-gate.py` → `sample-quality-gate-result-2026-09-01.json`

| Run | comparable_pairs | frames | inv/profile | insufficient_sample |
|-----|------------------|--------|-------------|-------------------|
| r7-contract | 1/5 min | 3/7 | 3/7 | sim |
| r8-contract | 0/5 | 3/7 | 3/7 | sim |
| r9-v2 | 0/5 | 7/7 | 7/7 | sim |
| **Agregado** | **1/5** | 13 frames | 13/profile | **sim** |

Razões agregadas: `comparable_pairs_count < min_comparable_pairs_count`, `scenario_tag_coverage_incomplete` (tags v2 `restart`, `reconciliation`, `preflight` só cobertos em r9 individualmente; agregado ainda incompleto para gate global v2), `filtered_invocation_count < min_invocations_per_profile × 2` (r7/r8).

Conclusões bloqueadas (gate): promoção, superioridade cognitiva, PASS qualidade cognitiva, regressão baseline como blocker, estabilidade intra-perfil, agregador executável, paralelismo, shadow armado.

---

## Auditoria de proveniência (decisão)

Fonte: `provenance-decision-audit-2026-09-01.json`

- 26/26 invocações com `raw_output_integrity.hash_present: true`
- r7: 3 artefatos com drift histórico **flagged, não reescritos** (`no_cross_run_mutation.artifact_rewritten: false`)
- r8/r9: 0 drift; `normalization_version` atual em todos os artefatos
- `prompt_version`: `glitch-topstep-v17.1`; `adapter_version`: `2026-09-01-v1`; `registry_version`: `2026-09-01-v2`

---

## Decisão

### amostra ainda insuficiente → enriquecer corpus

**Justificativa:**

1. Gate pré-registrado emite `insufficient_sample: true` em todos os runs e no agregado (`comparable_pairs` 1 < 5; cobertura de tags v2 incompleta em r7/r8; invocações abaixo do mínimo em r7/r8).
2. r9 cobre 7 cenários v2 com contrato 100% válido, mas **0 pares comparáveis** — baseline sistemático em `no_edge` impede denominador bilateral de qualidade de tese.
3. Evidência de diversidade existe (r7 `thesis_delta` canônico; r9 divergências categóricas), mas gate bloqueia conclusões de superioridade ou promoção.
4. Próximo passo offline permitido: enriquecer corpus / replays com frames onde **ambos** perfis produzem `thesis_quality` comparável, até `comparable_pairs_count ≥ 5` e cobertura v2 estável — sem alterar artefatos r7 históricos.

**Não aplicável neste momento:**

- `amostra suficiente e qualidade inconclusiva` — amostra insuficiente pelo gate.
- `amostra suficiente e evidência consistente` — amostra insuficiente pelo gate.

---

## Comandos

```powershell
python scripts/apply-sample-quality-gate.py
python scripts/audit-artifact-provenance.py --decision-output evaluation/runs/provenance-decision-audit-2026-09-01.json
python -m unittest tests.test_apply_sample_quality_gate -v
```
