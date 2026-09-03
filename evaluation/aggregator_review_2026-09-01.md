# Revisão estática do agregador — Trilha 4

**Data:** 2026-09-01  
**Escopo:** spec-only; **sem executor**  
**Run de evidência:** `scenario-live-2026-09-01-r7-contract`  
**Spec revisada:** `evaluation/AGGREGATOR-RULES-SPEC.md`  
**Rules JSON:** `evaluation/aggregator_rules.v1.json` — status **inalterado** (`approved_for_technical_review`)

## Veredito

A spec foi estendida com tabelas de decisão fechadas para os cenários observáveis no r7.  
**Executor ainda BLOCKED** — nenhum código de seleção ensemble foi implementado ou habilitado.

```text
agregador spec            FROZEN (compatibilidade r7 aplicada)
agregador executável      BLOCKED
paralelismo               BLOCKED
shadow / promoção         BLOCKED
```

## Corpus r7 exercitado

| Métrica | Valor |
|---------|-------|
| Cenários | 3 |
| Invocações | 6 (baseline-current + structure, sequencial) |
| `comparable_pair` | 1 / 3 (33,3%) |
| `aggregator_used` | `false` |
| Custo sessão | $0.007681 |

Fontes: `evaluation/runs/scenario-live-2026-09-01-r7-contract.json`, `-quality-report.json`, `-divergence-notes.json`.

## Cenários vs spec (frame comparisons)

### SCN-PRAC-DIRECTED-02 — `20260831T173427Z-4ac91997`

| Campo | baseline-current | structure |
|-------|------------------|-----------|
| `normalized.state` | `candidate` | `candidate` |
| `direction` | `long` | `long` |
| entry / stop / target | 29394.625 / 29186.5 / 29413.75 | idênticos |
| `baseline_category` / `challenger_category` | `thesis_quality` / `thesis_quality` |
| `comparable_pair` | **true** |
| `thesis_delta` | **true** |
| `direction_delta` | `null` |

**Exercício spec:** tabela “equivalência com ambos `thesis_quality`” + desempate com `thesis_delta` true.

**Resultado esperado (spec):** subgrupo equivalente único (0 ticks de distância); desempate por `evidence_score`; texto da thesis ignorado. Se scores empatarem → `prefer_baseline_on_tie` → `selected` baseline.

**Gap observado:** `completeness_used` de structure omite `orderflow` presente no baseline — impacto em `evidence_score` não exercitado com fixture fino (`thesis_quality: not_evaluated_on_thin_fixture`).

---

### SCN-OPERATOR-MIDSESSION — `20260901T134026Z-bb50bbe9`

| Campo | baseline-current | structure |
|-------|------------------|-----------|
| `normalized.state` | `candidate` | `no_edge` |
| `direction` | `flat` | `flat` |
| geometria | entry/stop/target presentes | `null` (abstinência válida) |
| `baseline_category` / `challenger_category` | `thesis_quality` / `no_edge` |
| `comparable_pair` | **false** |
| `thesis_delta` | `null` |

**Exercício spec:** tabela `no_edge` vs `candidate`.

**Resultado esperado (spec):** `no_selection` com `decision_code: ENSEMBLE_CATEGORY_DIVERGENCE` — diagnóstico em `decision_trace`, **não** `classified_failure`.

**Nota de divergência:** baseline declarou `candidate` com `direction: flat` e geometria (possível violação de contrato de prompt — `flat` deveria usar `no_edge`). Isso é problema de output contract / prompt (r8), não do agregador; spec trata o estado normalizado como dado.

---

### SCN-PRAC-TIMEOUT-RECOVERY — `20260901T000528Z-041dc508`

| Campo | baseline-current | structure |
|-------|------------------|-----------|
| `normalized.state` | `candidate` | `invalid` |
| `error_code` (structure) | — | `directional_without_geometry` |
| `baseline_category` / `challenger_category` | `thesis_quality` / `schema_invalid` |
| `comparable_pair` | **false** |
| `thesis_delta` | `null` |

**Exercício spec:** tabela timeout / `schema_invalid` / pool insuficiente.

**Resultado esperado (spec):** structure excluído do pool (`SCHEMA_INVALID` em trace); baseline sozinho no pool → `no_selection` / `INSUFFICIENT_ENSEMBLE_AGREEMENT` (consenso ensemble exige >1 perfil elegível na mesma categoria).

**Ação fora do agregador:** `prompt_contract_clarification_r8` (ver `-divergence-notes.json`).

## Cenários não exercitados no r7 (spec fechada, sem evidência)

| Cenário spec | Status |
|--------------|--------|
| Direções opostas (`LONG` vs `SHORT`) ambas elegíveis | não observado — regra `DIRECTION_CONFLICT` fechada na spec |
| `ensemble_timeout` global | não observado (todas invocações completaram) |
| `snapshot_divergence` / `version_incompatible` | não observado |
| Perfil ausente no bundle (`PROFILE_MISSING`) | não observado |
| Quatro perfis + adversarial (tabela normativa JSON) | não observado — permanece spec-only |
| `not_comparable` universal | não observado no r7 |

## Gaps encontrados

1. **Consenso mínimo não estava explícito** — perfil único elegível após exclusões não deve auto-selecionar; fechado como `INSUFFICIENT_ENSEMBLE_AGREEMENT`.
2. **`no_edge` vs `candidate`** — spec anterior não distinguia `no_selection` diagnóstico de `classified_failure`; fechado como `ENSEMBLE_CATEGORY_DIVERGENCE`.
3. **`thesis_delta` vs desempate** — risco de interpretar texto da thesis como gate; fechado: métrica Track D apenas; `prefer_baseline_on_tie` aplica em empate de score independente de `thesis_delta`.
4. **Empate pós-score** — spec dizia `no_selection` onde a ordem normativa indica `prefer_baseline_on_tie` primeiro; corrigido na spec.
5. **`candidate` + `direction: flat`** — baseline em midsession viola orientação do output contract; agregador não corrige; rastreio em output contract / prompt r8.
6. **Validators adversarial** — `validate_candidate_identity`, `validate_candidate_evidence_consistency` ainda spec-only; sem teste de integração.
7. **Corpus fino** — 1 `comparable_pair` insuficiente para validar desempate real por `evidence_score` com scores distintos.

## Alterações nesta revisão

| Artefato | Alteração |
|----------|-----------|
| `evaluation/AGGREGATOR-RULES-SPEC.md` | +7 tabelas de decisão, notas r7, correção desempate |
| `evaluation/aggregator_rules.v1.json` | **nenhuma** (status permanece `approved_for_technical_review`) |
| `evaluation/aggregator_review_2026-09-01.md` | este documento |

## Executor still BLOCKED

```text
████████████████████████████████████████
█  EXECUTOR STILL BLOCKED            █
█  Spec frozen for implementation.   █
█  No aggregator selection code.     █
█  aggregator_used: false (r7)       █
████████████████████████████████████████
```

Condições para desbloqueio (inalteradas):

1. Aprovação técnica explícita desta spec + gaps residuais  
2. Implementação do executor em mudança separada (fora Trilha 4)  
3. Testes contra `ensemble_selection.v1.json` com fixtures derivados do r7  
4. Manter `armed_promotion_allowed: false` e `evaluation_only: true`

## Referências

- `evaluation/runs/scenario-live-2026-09-01-r7-contract.json`
- `evaluation/runs/scenario-live-2026-09-01-r7-divergence-notes.json`
- `evaluation/OUTPUT-CONTRACT-SPEC.md`
- `evaluation/GATE_STATUS.md`
- `scripts/ensemble_compare.py` (`classify_candidate`, `compare_frame_profiles`)

## Fixture review (automated)

**Revisado em:** 2026-09-01T20:13:55.525671Z  
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

## Fixture review (automated)

**Revisado em:** 2026-09-01T23:40:50.482687Z  
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

## r9 normalized state cross-check

**Bundle:** `evaluation\runs\scenario-live-2026-09-01-r9-v2.json`  
**Cenários:** 7  
**comparable_pair:** 0  
**Passou:** sim  

| scenario_id | baseline | challenger | spec result | decision_code |
|-------------|----------|------------|-------------|---------------|
| SCN-PRAC-DIRECTED-02 | no_edge | thesis_quality | no_selection | ENSEMBLE_CATEGORY_DIVERGENCE |
| SCN-OPERATOR-MIDSESSION | no_edge | no_edge | no_selection | ENSEMBLE_UNANIMOUS_ABSTENTION |
| SCN-PRAC-TIMEOUT-RECOVERY | no_edge | no_edge | no_selection | ENSEMBLE_UNANIMOUS_ABSTENTION |
| SCN-PRAC-RESTART-BRACKET | no_edge | no_edge | no_selection | ENSEMBLE_UNANIMOUS_ABSTENTION |
| SCN-PRAC-RECONCILIATION | no_edge | thesis_quality | no_selection | ENSEMBLE_CATEGORY_DIVERGENCE |
| SCN-PRAC-PREFLIGHT | no_edge | no_edge | no_selection | ENSEMBLE_UNANIMOUS_ABSTENTION |
| SCN-OPERATOR-AFTERNOON | no_edge | no_edge | no_selection | ENSEMBLE_UNANIMOUS_ABSTENTION |
