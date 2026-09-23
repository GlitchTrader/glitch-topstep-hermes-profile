# Revisão estática da spec do agregador

**Data:** 2026-09-02 (offline, spec-only)  
**Rules version:** `2026-09-01-v2`  
**Executor:** **BLOCKED** — nenhum executor criado nesta rodada  
**Regra explícita:** nenhuma alteração de regras por causa de n=2 pares comparáveis

---

## Resultado

| Verificação | Status |
|-------------|--------|
| `review-aggregator-spec-consistency.py` | **PASS** (`consistency_ok: true`) |
| Fixtures com expected | **12/12** |
| Estados r13 observados mapeáveis | **PASS** (0 unknown) |
| Regras adversarial presentes | **PASS** |
| Issues | **0** |

---

## Schemas validados

| Schema | Path | Status |
|--------|------|--------|
| aggregator_rules | `evaluation/aggregator_rules.v1.json` | alinhado à spec MD |
| ensemble_selection | `evaluation/schemas/ensemble_selection.v1.json` | referenciado |
| normalized_candidate | `evaluation/schemas/normalized_candidate.v1.json` | referenciado |
| evaluation_envelope | `evaluation/schemas/evaluation_envelope.v1.json` | referenciado |

---

## Taxonomia de inputs (r13 + spec)

| Estado normalizado | Papel no agregador | Fixture? |
|--------------------|-------------------|----------|
| `candidate` | Entrada comparável direcional | Sim |
| `no_edge` | Abstinência — não agrupa com oposto | Sim |
| `missing_required_evidence` | Filtrado antes de equivalência | Sim |
| `not_comparable` | Excluído de agrupamento | Sim |
| `data_quality_insufficient` | → `not_comparable` na prática | Observado r13 |
| `held` | Comparável em `thesis_quality` | Sim |
| `thesis_quality` | **Categoria de comparação**, não `normalized.state` | Documentado |

---

## Cenários spec cobertos

| Cenário | Cobertura fixture/spec |
|---------|------------------------|
| Equivalência `candidate` | `group_by` + tick tolerances |
| `no_edge` bilateral | Sem par `thesis_quality` |
| `missing_required_evidence` | Eliminação pré-grupo |
| `not_comparable` | Preservação auditoria |
| `ensemble_timeout` | `failure_class` → `classified_failure` |
| Adversarial `critical` | Downgrade sem regra objetiva |
| Candidatos opostos LONG/SHORT | Buckets separados |
| `snapshot_divergence` | `VERSION_INCOMPATIBLE` / divergência hash |

---

## Outputs permitidos (sem executor)

| Output | Spec | Implementado? |
|--------|------|---------------|
| `selected` | Sim | **Não** (executor blocked) |
| `no_selection` | Sim | **Não** |
| `classified_failure` | Sim | **Não** |

Validators referenciados (`validate_candidate_identity`, `validate_candidate_evidence_consistency`) permanecem **spec-only**.

---

## Decisão

- Spec **consistente** com artefatos r7–r13 e fixtures 12/12.
- **Não** criar executor.
- **Não** alterar `aggregator_rules.v1.json` por n=2.
- Próximo passo (pós-autorização humana): replay r14 produz candidatos; agregador continua blocked para seleção operacional.

**Artefato JSON:** `evaluation/runs/aggregator-spec-consistency-review-2026-09-01.json`
