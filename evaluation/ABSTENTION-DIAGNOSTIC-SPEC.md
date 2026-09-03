# Especificação diagnóstica — abstinência (`abstention_diagnostic`)

**Status:** `FROZEN` · trilha `abstention_diagnostic` · **não** substitui `sample_quality_gate.v1.json`  
**Versão:** `2026-09-02-v1`  
**Relatório canônico:** `evaluation/runs/abstention-diagnostic-report-2026-09-02-v1.json`

```text
diagnostic_only           = true
promotion_use_allowed     = false
```

**Proibido:** converter `no_edge` → `thesis_quality` · inflar `comparable_pair` · usar abstinência para promoção.

---

## Objetivo

Medir **comportamento de abstinência** sem alegar superioridade direcional, distinguindo:

- perfil conservador com evidência suficiente;
- ausência de oportunidade observável;
- abstinência forçada por capacidade ou evidência parcial.

Outcomes futuros serão necessários para avaliar se a abstinência foi **correta** — esta trilha não conclui correção, apenas observabilidade e consistência.

---

## Unidade de análise

| Nível | Uso |
|-------|-----|
| **Invocação** | taxas, custo, latência |
| **Frame (envelope)** | alinhamento bilateral baseline/structure |
| **Sessão PRAC** | cobertura temporal e diversidade |
| **Run replay** | agregação operacional |

---

## Métricas obrigatórias

Todas classificadas:

```text
classification: diagnostic_only
promotion_use_allowed: false
```

### 1. `no_edge_rate`

```text
no_edge_rate(profile) = count(state=no_edge) / count(valid_invocations)
```

Reportar `numerator` / `denominator` por perfil e agregado.

### 2. `no_edge_with_complete_evidence`

Invocações com `state=no_edge` e `completeness_tier=complete` (sem dimensão `partial`/`missing`).

```text
no_edge_with_complete_evidence = count(no_edge AND tier=complete) / count(tier=complete)
```

### 3. Consistência intra-perfil

Quando o mesmo `frame_id`+`profile_id` tiver múltiplas invocações (reruns):

- `intra_profile_state_agreement_rate`
- divergências `no_edge` ↔ `candidate` | `thesis_quality`

### 4. Divergência baseline / structure

Por frame:

| Classe | Definição |
|--------|-----------|
| `aligned_abstention` | ambos `no_edge` |
| `category_divergence` | categorias distintas, `comparable_pair=false` |
| `bilateral_thesis` | `comparable_pair=true` |

### 5. Cobertura de oportunidades

```text
opportunity_coverage = frames_with_directional_signal / frames_with_capacity_and_evidence
```

`directional_signal` = ≥1 perfil em `candidate` | `thesis_quality` | `held`.

### 6. Taxa de candidato

```text
candidate_rate(profile) = count(state IN candidate,thesis_quality,held) / valid_invocations(profile)
```

Separado de `no_edge_rate` — nunca somar para inflar qualidade.

### 7. Taxa de abstinência por instrumento

```text
no_edge_rate_by_instrument[instrument]
```

### 8. Taxa de abstinência por completude

| Tier | Critério |
|------|----------|
| `complete` | sem `partial`/`missing` |
| `partial` | ≥1 `partial`, `capacity_gate_comparable=true` |
| `insufficient` | `capacity_gate_comparable=false` ou `missing_required_evidence` |

Métrica: `no_edge_rate_by_completeness[tier]`.

### 9. Custo / latência por decisão

```text
cost_per_decision_usd  = session_cost_usd / valid_invocation_count
cost_per_no_edge_usd   = session_cost_usd / no_edge_count
latency_p50_ms / p95_ms por run e agregado
```

---

## Elegibilidade para leitura de abstinência (filtro offline)

Incluir no relatório diagnóstico apenas quando **todos** forem verdadeiros:

1. `capacity_gate_comparable: true`
2. `completeness_tier` ∈ {`complete`, `partial`} — reportar separado
3. `scenario_tag != prac_directed_test`
4. origem espontânea quando o relatório for “abstinência espontânea”

Frames dirigidos e com capacidade insuficiente permanecem no relatório global com estrato explícito.

---

## Relação com `quality_gate_directional`

| Trilha | ID | Promoção |
|--------|-----|----------|
| Direcional | `quality_gate_directional` | bloqueada até ≥5 pares bilaterais `thesis_quality` |
| Abstinência | `abstention_diagnostic` | **nunca** autoriza promoção |

Gates **independentes**. Replay futuro deve emitir **ambos** os relatórios.

---

## Artefatos

| Artefato | Path |
|----------|------|
| Spec (este arquivo) | `evaluation/ABSTENTION-DIAGNOSTIC-SPEC.md` |
| Relatório v1 | `evaluation/runs/abstention-diagnostic-report-2026-09-02-v1.json` |
| Consolidação runs | `evaluation/runs/phase-5-run-consolidation-audit-2026-09-02.json` |

Nova versão de relatório (`-v2`) obrigatória se métricas ou runs incluídos mudarem — **não** alterar v1 retroativamente.
