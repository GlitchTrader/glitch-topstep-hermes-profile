# Revisão estática do agregador — artefatos reais r7/r9 (2026-09-01)

**Escopo:** spec-only + estados normalizados de runs reais; **executor BLOCKED**  
**Complementa:** `evaluation/reviews/AGGREGATOR-CONFORMITY-REVIEW-2026-09-01.md`  
**Fixtures:** `evaluation/fixtures/aggregator_decision_cases.v1.json` (12/12 PASS)  
**Rules:** `evaluation/aggregator_rules.v1.json` (`2026-09-01-v2`)

## Veredito

| Gate | Status |
|------|--------|
| Executor ensemble | **BLOCKED** |
| Fixtures artificiais 12/12 | **PASS** |
| Mapeamento r7 par canônico | **PASS** |
| Mapeamento r9 divergências | **PASS** |
| `no_selection` ≠ `NOTHING` | **PASS** |

---

## 1. Par comparável único — r7 `SCN-PRAC-DIRECTED-02`

Único `comparable_pair` bilateral em todo o cohort (r7+r8+r9).

| Perfil | Estado normalizado | Categoria |
|--------|-------------------|-----------|
| baseline-current | `candidate` | thesis_quality |
| structure | `candidate` | thesis_quality |

- `thesis_delta`: **true** (diversidade cognitiva observável)
- Resultado agregador esperado (spec): **`selected`** ou desempate por `evidence_score` / `PREFER_BASELINE_ON_TIE` se geometria equivalente
- Fixture análogo: `AGG-THESIS-QUAL-01`, `AGG-EQUIV-01`
- **Nota:** executor não executado; mapeamento derivado de `scenario-live-2026-09-01-r7-contract-diversity-metrics.json`

---

## 2. Candidatos opostos

**Nenhum** cenário nos artefatos r7/r8/r9 apresenta direções opostas elegíveis (LONG vs SHORT ambos `thesis_quality`).

- r7 `SCN-OPERATOR-MIDSESSION`: baseline `candidate` vs structure `no_edge` → não é conflito direcional
- Fixture de referência: `AGG-DIR-OPP-01` → `no_selection` / `DIRECTION_CONFLICT` (não exercitado em runs reais)

---

## 3. Candidate vs no_edge — divergências r9

Dois cenários r9 com divergência categórica (baseline abstém, challenger não):

| scenario_id | baseline | structure | spec result | decision_code |
|-------------|----------|-----------|-------------|---------------|
| SCN-PRAC-DIRECTED-02 | no_edge | held | no_selection | ENSEMBLE_CATEGORY_DIVERGENCE |
| SCN-PRAC-RECONCILIATION | no_edge | held | no_selection | ENSEMBLE_CATEGORY_DIVERGENCE |

Demais 5 cenários r9: abstinência unânime (`no_edge`/`no_edge`) → `ENSEMBLE_UNANIMOUS_ABSTENTION`.

Fixture análogo: `AGG-CAT-DIV-01`.

---

## 4. missing_required_evidence

Nenhum artefato r7/r9 reporta `classification.missing_required_evidence: true` nos estados normalizados auditados.

- Política spec: `missing_required_evidence` **não** conta como `no_edge`
- Fixture: `AGG-MISS-EVID-01` → `INSUFFICIENT_ENSEMBLE_AGREEMENT`
- Runs reais: categoria não exercitada no cohort atual

---

## 5. Objeção adversarial

Perfil `adversarial-risk` **não** participou dos runs r7/r8/r9 (apenas `baseline-current` + `structure`).

- Fixtures críticos: `AGG-ADV-CRIT-OBJ-01`, `AGG-ADV-CRIT-NORULE-01`
- Runs reais: **sem evidência adversarial** neste cohort

---

## 6. `no_selection` vs `NOTHING`

| Conceito | Escopo nos runs | Exemplo r9 |
|----------|-----------------|------------|
| `no_selection` | saída agregador — nenhum perfil promovido | 7/7 cenários → abstinência ou divergência |
| `NOTHING` | ação de perfil individual | estados `no_edge`, `held`, `candidate` — **nunca** output agregador |

Nenhum estado normalizado nos artefatos mapeia para `NOTHING` como decisão de ensemble. Abstinência unânime r9 usa `ENSEMBLE_UNANIMOUS_ABSTENTION`, não ação operacional `NOTHING`.

---

## Executor

```text
████████████████████████████████████████
█  EXECUTOR STILL BLOCKED            █
█  Static review from run artifacts. █
████████████████████████████████████████
```

## Referências

- `evaluation/runs/scenario-live-2026-09-01-r7-contract.json`
- `evaluation/runs/scenario-live-2026-09-01-r9-v2.json`
- `evaluation/runs/cohort-provenance-audit-2026-09-01.json`
