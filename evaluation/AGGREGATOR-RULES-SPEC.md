# Especificação do agregador ensemble (spec-only)

**Status:** `approved_for_technical_review` (spec-only; executor bloqueado)  
**Rules version:** `2026-09-01-v2`  
**Revisão compatibilidade:** `2026-09-01-r7` (Trilha 4 — sem alterar status do JSON normativo)  
**Artefato normativo:** `evaluation/aggregator_rules.v1.json`  
**Saída:** `evaluation/schemas/ensemble_selection.v1.json`  
**Evidência:** `evaluation/runs/scenario-live-2026-09-01-r7-contract.json`

## Escopo

Esta especificação fecha regras de equivalência, severidade, desempate e outputs para revisão técnica. **Não autoriza** implementação executável, seleção operacional, shadow ao vivo, gateway ou promoção.

## Outputs permitidos

| Output | Quando emitir | Não confundir com |
|--------|---------------|-------------------|
| `selected` | Exatamente um candidato passou gates, expiry, eliminações objetivas e desempate | decisão operacional do gateway |
| `no_selection` | Nenhum candidato elegível após filtros; auditoria preservada | `NOTHING` analítico do perfil |
| `classified_failure` | Falha de envelope, versão, snapshot ou processo impediu comparação | `missing_required_evidence` de um perfil |

### Mapeamento `failure_class` → `classified_failure`

| `failure_class` | Condição de entrada | `decision_code` sugerido |
|-----------------|---------------------|--------------------------|
| `ensemble_timeout` | Budget global ou per-profile timeout antes de candidatos finais | `ENSEMBLE_TIMEOUT` |
| `decision_expired` | `expires_utc` do envelope ultrapassado na avaliação | `ENVELOPE_EXPIRED` |
| `schema_invalid` | Candidato normalizado inválido após normalização | `SCHEMA_INVALID` |
| `version_incompatible` | `profile_version` / `prompt_version` fora do registry aceito | `VERSION_INCOMPATIBLE` |
| `snapshot_divergence` | `snapshot_hash` do candidato ≠ envelope | `SNAPSHOT_DIVERGENCE` |

## Equivalência de candidatos

### Agrupamento

Candidatos agrupam quando **todos** os campos em `group_by` coincidem:

- `instrument`, `contract_id`, `contract_generation`, `direction`, `horizon_bars`

### Regras adicionais (fechamento v2)

1. **Mesmo instrumento e contrato** — obrigatório (`same_instrument_required`).
2. **Mesma direção** — obrigatório para grupo direcional (`same_direction_required`).
3. **Stop obrigatório** — candidatos direcionais sem `stop` nunca entram no mesmo grupo (`require_stop_for_directional`).
4. **Candidatos opostos** — direções `LONG` vs `SHORT` (ou equivalentes normalizados) **nunca** agrupam; competem em desempate, não em equivalência.
5. **Distâncias** — tolerâncias em ticks nativos (`entry_ticks`, `stop_ticks`, `target_ticks`); `entry_range` usa midpoint (`use_range_midpoint_for_distance`).
6. **Contrato diferente** — `contract_id` ou `contract_generation` distintos → grupos distintos, sem merge.

### Algoritmo (spec)

```text
1. Normalizar direction para {LONG, SHORT, FLAT, HOLD}
2. Filtrar estados não comparáveis (missing_required_evidence, timeout, invalid)
3. Para cada candidato direcional: exigir stop
4. Bucket por group_by key
5. Dentro do bucket: pairwise tick distance <= tolerância → subgrupo equivalente
6. Candidatos opostos permanecem em buckets separados por direction
```

## Severidade adversarial

| Nível | Elimina? | Penalidade | Normalização |
|-------|----------|------------|--------------|
| `info` | não | 0 | — |
| `warning` | não | 1 | — |
| `critical` | só com regra objetiva | 3 | sem regra → `normalize_to_warning` (`ADVERSARIAL_CRITICAL_DOWNGRADED`) |

Regras objetivas (`objective_elimination_rules`): geometria, identidade, consistência de evidência.

**Validators referenciados mas não implementados** (`validate_candidate_identity`, `validate_candidate_evidence_consistency`) permanecem spec-only até aprovação do executor.

## `evidence_score` (definição fechada para desempate)

Campo derivado **somente** do candidato normalizado + envelope; não usa confiança LLM bruta.

```text
evidence_score =
  +10 por required source em completeness_used == "available"
  +5  por optional source == "available"
  -20 por missing_required em completeness_used
  -10 por stale ou inconsistent
  +len(evidence_refs) capped at 5
```

Empate em `evidence_score` e `warning_priority_penalty` → passo 7 `prefer_baseline_on_tie` → `selected` com `baseline-current` (ou perfil baseline do registry).  
Empate perfeito **após** `prefer_baseline_on_tie` (ex.: baseline ausente do pool) → passo 8 `no_selection`.

### `thesis_delta` (métrica Track D) vs agregador

| Campo | Escopo | Usado no agregador? |
|-------|--------|---------------------|
| `thesis_delta` | `ensemble_compare.compare_frame_profiles` | **Não** — texto da thesis nunca entra em equivalência nem desempate |
| `comparable_pair` | métricas offline | **Diagnóstico** — informa `decision_trace`, não substitui gates do agregador |
| `direction_delta` | métricas offline | **Diagnóstico** — conflito direcional dispara regras de agrupamento/desempate abaixo |

Quando `comparable_pair: true` e `thesis_delta: true` (r7 `SCN-PRAC-DIRECTED-02`): candidatos podem ser geometricamente equivalentes com narrativas distintas; desempate segue `evidence_score`, não similaridade textual.

## Tabela — equivalência com ambos `thesis_quality`

Pré-condição: `classify_candidate` → `thesis_quality` para cada perfil; `comparability: comparable`.

| Condição geométrica / identidade | Agrupa? | Próximo passo agregador |
|----------------------------------|---------|-------------------------|
| Mesmo `group_by` + distâncias ≤ tolerância em ticks | sim | Um representante por subgrupo; desempate entre representantes |
| Mesma direção, geometria fora da tolerância | não | Buckets direcionais separados; desempate entre vencedores de cada bucket |
| `thesis_delta: true`, geometria dentro da tolerância | sim | Ignorar texto; `evidence_score` decide |
| `thesis_delta: false`, `evidence_score` empate | sim (se geometria ok) | `prefer_baseline_on_tie` → `selected` baseline |
| Um perfil `held`, outro `candidate`, mesma geometria | sim* | *Se ambos `thesis_quality`; `held` não isenta de equivalência geométrica |
| `horizon_bars` distinto | não | `group_by` separa — sem merge |

**Observação r7 (`4ac91997`):** baseline + structure, `LONG`, entry/stop/target idênticos → subgrupo único; `thesis_delta: true` não impede agrupamento.

## Tabela — direções opostas (nunca agrupar)

| baseline | challenger | Agrupa? | `direction_delta` (métrica) | Resultado agregador |
|----------|------------|---------|----------------------------|---------------------|
| `long` | `short` | **nunca** | `{baseline, challenger}` | `no_selection` — `DIRECTION_CONFLICT` |
| `long` | `long` (geom. distinta) | não (distância) | `null` se ambos `thesis_quality` | desempate por `evidence_score` entre buckets |
| `flat` | `long` | **nunca** | ver nota | `no_selection` — `DIRECTION_CONFLICT` |
| `flat` + geometria | `no_edge` | n/a | n/a | ver tabela `no_edge` abaixo |

Regra fechada: `opposite_direction_never_groups` — `LONG`/`SHORT` (e pares `long`/`short` normalizados) permanecem em buckets distintos; conflito direcional entre buckets elegíveis → `no_selection`, nunca `selected` por “maior score isolado”.

## Tabela — `no_edge` vs `candidate` no mesmo envelope

Pré-condição: mesmo `envelope_id` / `snapshot_hash`; perfis retornaram com sucesso (não timeout).

| baseline | challenger | `comparable_pair` (métrica) | Resultado agregador | `decision_code` | Diagnóstico |
|----------|------------|----------------------------|---------------------|-----------------|-------------|
| `thesis_quality` | `no_edge` | `false` | **`no_selection`** | `ENSEMBLE_CATEGORY_DIVERGENCE` | Sim — registrar categorias em `decision_trace`; **não** `classified_failure` |
| `no_edge` | `thesis_quality` | `false` | **`no_selection`** | `ENSEMBLE_CATEGORY_DIVERGENCE` | idem |
| `no_edge` | `no_edge` | `false` | **`no_selection`** | `ENSEMBLE_UNANIMOUS_ABSTENTION` | Consenso de abstinência; distinto de `NOTHING` operacional |
| `thesis_quality` | `thesis_quality` | `true` | fluxo normal | — | Equivalência + desempate |

**Fechamento r7 (`bb50bbe9`):** baseline emitiu `candidate` com `direction: flat` e geometria; structure emitiu `no_edge` válido. Agregador **não** promove baseline sozinho — abstinência explícita do challenger bloqueia `selected`. Métricas Track D permanecem diagnósticas (`comparable_pair: false`).

**Proibido:** inferir `no_edge` a partir de `action: NOTHING` ou `direction: flat` no adapter (ver `OUTPUT-CONTRACT-SPEC.md`).

## Tabela — objeções adversarial (spec-only)

Validators referenciados permanecem spec-only até aprovação do executor.

| Cenário | Severidade | Regra objetiva? | Elimina? | Resultado |
|---------|------------|-----------------|----------|-----------|
| 4 perfis concordam + critical + regra objetiva | `critical` | sim | sim (todos afetados) | `no_selection` — `ADVERSARIAL_CRITICAL_OBJECTIVE_ELIMINATION` |
| 4 perfis concordam + critical sem regra | `critical` | não | não (normaliza) | `selected` baseline — `ADVERSARIAL_CRITICAL_DOWNGRADED` |
| 4 perfis concordam + warning | `warning` | — | não | `selected` baseline — `ADVERSARIAL_WARNING_PENALTY` |
| 2 perfis, um com critical objetivo no único candidato restante | `critical` | sim | sim | `no_selection` |
| Objeção `info` | `info` | — | não | sem efeito no desempate |

Objeções são anexadas a `ensemble_selection.objections[]`; `eliminates_candidate` segue `adversarial_severity` no JSON normativo.

## Tabela — timeout, `not_comparable`, perfil ausente

| Condição | Perfil afetado | Pool de seleção | Resultado | `failure_class` / `decision_code` |
|----------|----------------|-----------------|-----------|-----------------------------------|
| `normalized.state == timeout` | um perfil | excluído | continua com restantes | — / `PROFILE_TIMEOUT` em `decision_trace` |
| Budget global esgotado antes de candidatos finais | todos | vazio | `classified_failure` | `ensemble_timeout` / `ENSEMBLE_TIMEOUT` |
| Todos os perfis `timeout` | todos | vazio | `classified_failure` | `ensemble_timeout` |
| `comparability: not_comparable` | um perfil | excluído | continua | — / `PROFILE_NOT_COMPARABLE` |
| Todos `not_comparable` ou `missing_required_evidence` | todos | vazio | `no_selection` | `NO_ELIGIBLE_CANDIDATES` |
| `missing_required_evidence` | um perfil | excluído | continua | — / `MISSING_REQUIRED_EVIDENCE` |
| Invocação ausente no bundle (registry exige perfil) | perfil esperado | — | `classified_failure` | — / `PROFILE_MISSING` |
| `schema_invalid` / `error` | um perfil | excluído | continua se outro elegível | — / `SCHEMA_INVALID` |
| baseline `thesis_quality`, único challenger `schema_invalid` | challenger | baseline sozinho no pool | ver nota r7 | **`no_selection`** — `INSUFFICIENT_ENSEMBLE_AGREEMENT` (um perfil elegível ≠ consenso) |

**Nota r7 (`041dc508`):** baseline `candidate` válido; structure `invalid` (`directional_without_geometry`). Métrica: `comparable_pair: false`. Agregador spec: seleção exige mais de um perfil concordante na mesma categoria elegível; perfil único no pool → `no_selection`, não `selected` automático do baseline.

## Tabela — desempate com baseline em empate (`thesis_delta` / score)

Ordem após eliminações (passos 1–4 da ordem de desempate):

| Estado após filtros | `thesis_delta` (métrica) | `evidence_score` | `warning_penalty` | Resultado |
|--------------------|--------------------------|------------------|-------------------|-----------|
| 2+ candidatos no mesmo subgrupo equivalente | `true` ou `false` | distinto | qualquer | `selected` — maior `evidence_score` |
| 2+ candidatos, scores iguais | `false` (mesma thesis) | empate | empate | `selected` — `prefer_baseline_on_tie` → baseline |
| 2+ candidatos, scores iguais | `true` (thesis distinta) | empate | empate | `selected` — `prefer_baseline_on_tie` → baseline (texto **não** desempata) |
| 1 candidato no pool, outro `no_edge` | n/a | n/a | n/a | `no_selection` — `ENSEMBLE_CATEGORY_DIVERGENCE` |
| 1 candidato no pool, demais `invalid`/timeout | n/a | n/a | n/a | `no_selection` — `INSUFFICIENT_ENSEMBLE_AGREEMENT` |
| 0 candidatos | n/a | n/a | n/a | `no_selection` — `NO_ELIGIBLE_CANDIDATES` |

`thesis_delta` **nunca** inverte `prefer_baseline_on_tie`: concordância textual é métrica offline, não gate de promoção.

## Ordem de desempate

1. `drop_invalid_and_expired`
2. `drop_missing_required_evidence_for_directional_claim`
3. `apply_critical_objective_eliminations`
4. `apply_critical_normalization_without_objective_rule`
5. `prefer_higher_evidence_score`
6. `apply_warning_priority_penalty`
7. `prefer_baseline_on_tie`
8. `no_selection`

## Tabela 4 concordam + adversarial

Casos em `decision_table_four_agree_adversarial_rejects` no JSON são normativos para revisão. Casos adicionais obrigatórios antes do executor:

| Caso | Resultado esperado |
|------|-------------------|
| Empate perfeito baseline/challenger após score | `selected` baseline (`prefer_baseline_on_tie`) |
| Empate após baseline preference com baseline ausente | `no_selection` |
| Timeout de um perfil | excluir perfil; trace `PROFILE_TIMEOUT` |
| Timeout global / todos timeout | `classified_failure` / `ensemble_timeout` |
| Snapshot divergente | `classified_failure` |
| Versão de perfil incompatível | `classified_failure` |
| Quatro concordam + adversarial critical com regra objetiva | `no_selection` |
| `no_edge` vs `candidate` (r7 midsession) | `no_selection` / `ENSEMBLE_CATEGORY_DIVERGENCE` |
| Direções opostas ambas elegíveis | `no_selection` / `DIRECTION_CONFLICT` |
| Único perfil elegível, demais invalid/abstain | `no_selection` / `INSUFFICIENT_ENSEMBLE_AGREEMENT` |

## Compatibilidade r7 (notas apenas)

| Cenário r7 | Frame | Leitura spec |
|------------|-------|--------------|
| `SCN-PRAC-DIRECTED-02` | `4ac91997` | `comparable_pair: true`, `thesis_delta: true` — equivalência geométrica + desempate por score |
| `SCN-OPERATOR-MIDSESSION` | `bb50bbe9` | `no_edge` vs `candidate` → `no_selection` diagnóstico |
| `SCN-PRAC-TIMEOUT-RECOVERY` | `041dc508` | structure `schema_invalid` → pool insuficiente para consenso |

Artefato de divergência: `evaluation/runs/scenario-live-2026-09-01-r7-divergence-notes.json`  
Revisão humana: `evaluation/aggregator_review_2026-09-01.md`

## Bloqueios inalterados

- Agregador executável
- Paralelismo Hermes
- Shadow ao vivo
- Promoção automática
- Ajuste de prompt durante coleta de métricas

## Próximo gate

1. ~~Corpus comparável + replay sequencial com `comparable_pair` observável~~ — **r7:** 1/3 frames (`SCN-PRAC-DIRECTED-02`)  
2. Revisão humana desta spec + resultados r7 — `evaluation/aggregator_review_2026-09-01.md`  
3. Aprovação técnica explícita  
4. Só então: implementação do executor (fora deste documento)
