# Revisão de conformidade do agregador — 2026-09-01

**Escopo:** spec-only; **executor BLOCKED**  
**Script:** `scripts/review-aggregator-spec-fixtures.py`  
**Fixtures:** `evaluation/fixtures/aggregator_decision_cases.v1.json` (12 casos)  
**Rules:** `evaluation/aggregator_rules.v1.json` (`2026-09-01-v2`)  
**Spec:** `evaluation/AGGREGATOR-RULES-SPEC.md`  
**Evidência r9:** `evaluation/runs/scenario-live-2026-09-01-r9-v2.json`

## Veredito executivo

| Gate | Status |
|------|--------|
| Executor ensemble | **BLOCKED** |
| Fixtures 12/12 vs spec | **PASS** |
| Rules JSON ↔ fixtures `rules_version` | **PASS** (`2026-09-01-v2`) |
| r9 normalized state cross-check | **PASS** (7 cenários mapeados) |
| `no_selection` ≠ `NOTHING` | **PASS** (documentado + fixtures) |
| Política adversarial | **PASS** (tabela fechada + fixtures críticos) |

Relatório machine-readable: `evaluation/aggregator_fixture_review_2026-09-01.json`

---

## 1. Alinhamento `aggregator_rules.v1.json` ↔ schemas

| Check | Resultado |
|-------|-----------|
| Três outputs (`selected`, `no_selection`, `classified_failure`) | **PASS** |
| `failure_class_to_output` cobre timeout/schema/version | **PASS** |
| `adversarial_severity` + `critical_normalization` | **PASS** |
| `group_by` inclui `horizon_bars` e identidade de contrato | **PASS** |
| `tiebreak_order` termina em `prefer_baseline_on_tie` → `no_selection` | **PASS** |

---

## 2. Fixtures artificiais (12 casos)

Revisão automatizada em **2026-09-01T20:31:28Z** — **12/12 PASS**.

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
| AGG-UNANIMOUS-ABSTAIN-01 | no_selection | ENSEMBLE_UNANIMOUS_ABSTENTION | ✓ |
| AGG-INSUFFICIENT-01 | no_selection | INSUFFICIENT_ENSEMBLE_AGREEMENT | ✓ |
| AGG-TIMEOUT-01 | classified_failure | ENSEMBLE_TIMEOUT | ✓ |
| AGG-PROFILE-MISSING-01 | classified_failure | PROFILE_MISSING | ✓ |

---

## 3. Cross-check r9 — estados normalizados (sem executor)

Bundle `scenario-live-2026-09-01-r9-v2`: **7 cenários**, **0** `comparable_pair`, **5** abstinência unânime, **2** divergência categórica.

| scenario_id | baseline | challenger | spec result | decision_code |
|-------------|----------|------------|-------------|---------------|
| SCN-PRAC-DIRECTED-02 | no_edge | thesis_quality | no_selection | ENSEMBLE_CATEGORY_DIVERGENCE |
| SCN-OPERATOR-MIDSESSION | no_edge | no_edge | no_selection | ENSEMBLE_UNANIMOUS_ABSTENTION |
| SCN-PRAC-TIMEOUT-RECOVERY | no_edge | no_edge | no_selection | ENSEMBLE_UNANIMOUS_ABSTENTION |
| SCN-PRAC-RESTART-BRACKET | no_edge | no_edge | no_selection | ENSEMBLE_UNANIMOUS_ABSTENTION |
| SCN-PRAC-RECONCILIATION | no_edge | thesis_quality | no_selection | ENSEMBLE_CATEGORY_DIVERGENCE |
| SCN-PRAC-PREFLIGHT | no_edge | no_edge | no_selection | ENSEMBLE_UNANIMOUS_ABSTENTION |
| SCN-OPERATOR-AFTERNOON | no_edge | no_edge | no_selection | ENSEMBLE_UNANIMOUS_ABSTENTION |

**Leitura:** r9 não exercita desempate `EVIDENCE_SCORE_WIN` nem equivalência bilateral — limitação de corpus, não falha de spec. Divergências `no_edge` vs `held`/`candidate` mapeiam corretamente para `ENSEMBLE_CATEGORY_DIVERGENCE`.

---

## 4. `no_selection` vs `NOTHING`

| Conceito | Escopo | Confundir? |
|----------|--------|------------|
| `no_selection` | saída agregador — nenhum perfil promovido | — |
| `NOTHING` | ação de perfil individual no intent | **Proibido** |

- Abstinência unânime r9 → `ENSEMBLE_UNANIMOUS_ABSTENTION`, **não** `NOTHING` operacional.
- Fixture `AGG-UNANIMOUS-ABSTAIN-01` cobre o caso artificial.
- Nenhum fixture espera `NOTHING` como output agregador.

---

## 5. Política adversarial

| Severidade | Regra objetiva? | Efeito | Fixture |
|------------|-----------------|--------|---------|
| `critical` | sim | eliminação | AGG-ADV-CRIT-OBJ-01 |
| `critical` | não | normaliza → warning | AGG-ADV-CRIT-NORULE-01 |
| `warning` | — | penalidade | tabela JSON normativa |

Validators (`validate_candidate_identity`, etc.) permanecem **spec-only** — sem executor.

---

## Executor

```text
████████████████████████████████████████
█  EXECUTOR STILL BLOCKED            █
█  Spec-review + r9 cross-check only.█
████████████████████████████████████████
```

## Referências

- `evaluation/AGGREGATOR-SPEC-CHECKLIST-2026-09-01.md`
- `evaluation/aggregator_review_2026-09-01.md` (r7 histórico)
- `evaluation/reviews/CORPUS-COVERAGE-GAPS-2026-09-01.md`
