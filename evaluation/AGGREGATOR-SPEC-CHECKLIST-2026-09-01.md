# Checklist — agregador spec-only (Trilha C)

**Data:** 2026-09-01  
**Escopo:** revisão estática; **sem executor**  
**Fixtures:** `evaluation/fixtures/aggregator_decision_cases.v1.json` (12 casos)  
**Spec:** `evaluation/AGGREGATOR-RULES-SPEC.md`  
**Rules JSON:** `evaluation/aggregator_rules.v1.json` (`2026-09-01-v2`)  
**Script:** `scripts/review-aggregator-spec-fixtures.py`

## Veredito executivo

| Gate | Status |
|------|--------|
| Executor ensemble | **BLOCKED** |
| Fixtures vs spec | ver tabela automatizada abaixo |
| Outputs vs estados normalizados | **PASS** (mapeamento fechado) |

---

## 1. Outputs spec ↔ estados normalizados

Os três outputs do agregador (`selected`, `no_selection`, `classified_failure`) mapeiam para categorias de candidato **após** normalização (`evaluation_output_contract.v1.json` + adapter):

| Output agregador | Estados normalizados típicos no pool | `decision_code` exemplos |
|------------------|--------------------------------------|--------------------------|
| `selected` | `candidate` (e eventualmente `held`) após gates | `EVIDENCE_SCORE_WIN`, `PREFER_BASELINE_ON_TIE`, `ADVERSARIAL_CRITICAL_DOWNGRADED` |
| `no_selection` | pool vazio, divergência de categoria, consenso insuficiente | `DIRECTION_CONFLICT`, `ENSEMBLE_CATEGORY_DIVERGENCE`, `INSUFFICIENT_ENSEMBLE_AGREEMENT`, `ENSEMBLE_UNANIMOUS_ABSTENTION` |
| `classified_failure` | processo/envelope impediu comparação | `ENSEMBLE_TIMEOUT`, `PROFILE_MISSING` |

**Verificação:** cada fixture `expected.result` ∈ `{selected, no_selection, classified_failure}` e alinha com `scenario_tags` via mapeamento normativo do script de review. Estados de entrada usam `normalized_state` do contrato (`candidate`, `no_edge`, `missing_required_evidence`, `invalid`, `timeout`).

| Check | Resultado |
|-------|-----------|
| Três outputs únicos na spec | **PASS** |
| Fixtures usam apenas outputs permitidos | **PASS** (12/12) |
| `classified_failure` exige `failure_class` quando timeout global | **PASS** (`AGG-TIMEOUT-01`) |

---

## 2. `no_selection` ≠ `NOTHING` (documentação explícita)

| Conceito | Escopo | Confundir? |
|----------|--------|------------|
| `no_selection` | saída do **agregador ensemble** — nenhum perfil promovido após filtros | — |
| `NOTHING` | ação analítica/operacional de um **perfil individual** (`action` no intent) | **Proibido** |

**Regras fechadas (spec):**

- Abstinência unânime (`no_edge` em todos) → `no_selection` + `ENSEMBLE_UNANIMOUS_ABSTENTION`, **não** inferência de `NOTHING` operacional.
- `no_edge` vs `candidate` → `no_selection` diagnóstico (`ENSEMBLE_CATEGORY_DIVERGENCE`), não promove baseline isolado.
- Proibido inferir `no_edge` a partir de `action: NOTHING` no adapter (`OUTPUT-CONTRACT-SPEC.md`).

| Check | Resultado |
|-------|-----------|
| Spec distingue outputs agregador vs ação perfil | **PASS** |
| Fixture `AGG-UNANIMOUS-ABSTAIN-01` usa `no_selection` | **PASS** |
| Nenhum fixture espera `NOTHING` como output agregador | **PASS** |

---

## 3. `not_comparable` excluído do pool

Pré-filtro (spec algoritmo passo 2): estados `missing_required_evidence`, `timeout`, `invalid` e `comparability: not_comparable` **não entram** no pool de seleção.

| Fixture | Perfil excluído | Pool residual | Resultado |
|---------|-----------------|---------------|-----------|
| `AGG-MISS-EVID-01` | structure (`not_comparable` + `missing_required_evidence`) | baseline sozinho | `no_selection` / `INSUFFICIENT_ENSEMBLE_AGREEMENT` |
| `AGG-INSUFFICIENT-01` | structure (`invalid` / `schema_invalid`) | baseline sozinho | `no_selection` / `INSUFFICIENT_ENSEMBLE_AGREEMENT` |

| Check | Resultado |
|-------|-----------|
| `not_comparable` não concorre ao desempate | **PASS** |
| Trace esperado `MISSING_REQUIRED_EVIDENCE` em `AGG-MISS-EVID-01` | **PASS** |
| Perfil único elegível ≠ auto-seleção | **PASS** |

---

## 4. Desempate baseline explícito (`prefer_baseline_on_tie`)

Ordem normativa (passos 5–7): `evidence_score` → `warning_priority_penalty` → **`prefer_baseline_on_tie`** → `no_selection`.

| Fixture | Condição | Resultado esperado |
|---------|----------|-------------------|
| `AGG-TIE-BASELINE-01` | scores e penalties iguais | `selected` baseline / `PREFER_BASELINE_ON_TIE` |
| `AGG-THESIS-QUAL-01` | geometria equivalente, `thesis_delta` distinto, scores iguais | `selected` baseline / `PREFER_BASELINE_ON_TIE` |
| `AGG-EQUIV-01` | geometria equivalente, scores distintos | `selected` / `EVIDENCE_SCORE_WIN` (baseline maior score) |

**Nota:** `thesis_delta` é métrica offline (Track D); **não** inverte `prefer_baseline_on_tie`.

| Check | Resultado |
|-------|-----------|
| Empate perfeito resolve para baseline | **PASS** |
| `thesis_delta` não é gate de desempate | **PASS** (documentado na spec) |
| Passo 8 `no_selection` só após baseline preference esgotada | **PASS** |

---

## 5. Severidade adversarial determinística

Tabela fechada em `aggregator_rules.v1.json` → `adversarial_severity` + `critical_normalization`:

| Severidade | Regra objetiva? | Efeito | Fixture |
|------------|-----------------|--------|---------|
| `critical` | sim (`objective_rule_match: true`) | eliminação | `AGG-ADV-CRIT-OBJ-01` → `no_selection` |
| `critical` | não | normaliza para `warning` | `AGG-ADV-CRIT-NORULE-01` → `selected` baseline |
| `warning` | — | penalidade, não elimina | (tabela JSON normativa) |

| Check | Resultado |
|-------|-----------|
| Critical + regra objetiva → eliminação determinística | **PASS** |
| Critical sem regra → `ADVERSARIAL_CRITICAL_DOWNGRADED` | **PASS** |
| Validators (`validate_candidate_identity`, etc.) permanecem spec-only | **PASS** (sem executor) |

---

## 6. Tolerâncias em ticks por contrato e `horizon_bars`

**Agrupamento (`group_by`):** `instrument`, `contract_id`, `contract_generation`, `direction`, **`horizon_bars`**.

- `horizon_bars` distinto → buckets separados, **sem merge** (spec tabela equivalência).
- Tolerâncias em ticks nativos por instrumento (`tick_tolerance_by_instrument`):

| Instrumento | entry_ticks | stop_ticks | target_ticks |
|-------------|-------------|------------|--------------|
| DEFAULT / MNQ / MES | 4 | 6 | 8 |

Distâncias calculadas a partir de `envelope.contract.tick_size`; `entry_range` usa midpoint (`use_range_midpoint_for_distance`).

| Check | Resultado |
|-------|-----------|
| `horizon_bars` em `group_by` | **PASS** (JSON normativo) |
| Tolerâncias por contrato/instrumento documentadas | **PASS** |
| Fixture `AGG-EQUIV-01` usa mesmo `horizon_bars` (12) para equivalência | **PASS** |
| Candidatos opostos nunca agrupam | **PASS** (`AGG-DIR-OPP-01`) |

---

## Executor

```text
████████████████████████████████████████
█  EXECUTOR STILL BLOCKED            █
█  Spec-review only (Trilha C).      █
████████████████████████████████████████
```

## Fixture review (automated)

**Revisado em:** 2026-09-01T20:21:40.519415Z  
**Casos:** 12  
**Passou:** sim  

| case_id | result | decision_code | spec_ok |
|---------|--------|---------------|---------|
| AGG-EQUIV-01 | selected | EVIDENCE_SCORE_WIN | ✓ |
| AGG-DIR-OPP-01 | no_selection | DIRECTION_CONFLICT | ✓ |
| AGG-THESIS-QUAL-01 | selected | PREFER_BASELINE_ON_TIE | ✓ |
| AGG-CAT-DIV-01 | no_selection | ENSEMBLE_CATEGORY_DIVERGENCE | ✓ |
| AGG-MISS-EVID-01 | no_selection | INSUFFICIENT_ENSEMBLE_AGREEMENT | ✓ |
| AGG-ADV-CRIT-OBJ-01 | no_selection | ADVERSARIAL_CRITICAL_OBJECTIVE_ELIMINATION | ✓ |
| AGG-ADV-CRIT-NORULE-01 | selected | ADVERSARIAL_CRITICAL_DOWNGRADED | ✓ |
| AGG-TIE-BASELINE-01 | selected | PREFER_BASELINE_ON_TIE | ✓ |
| AGG-TIMEOUT-01 | classified_failure | ENSEMBLE_TIMEOUT | ✓ |
| AGG-PROFILE-MISSING-01 | classified_failure | PROFILE_MISSING | ✓ |
| AGG-INSUFFICIENT-01 | no_selection | INSUFFICIENT_ENSEMBLE_AGREEMENT | ✓ |
| AGG-UNANIMOUS-ABSTAIN-01 | no_selection | ENSEMBLE_UNANIMOUS_ABSTENTION | ✓ |
