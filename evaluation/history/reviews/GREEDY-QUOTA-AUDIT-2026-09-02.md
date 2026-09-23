# Auditoria greedy/quota — seleção de coorte estratificada

**Data:** 2026-09-02  
**Gatilho:** v5 preencheu quota `operator_minute_frame` com frames overnight 09-01, excluindo espontâneos da sessão PRAC 09-02.

## Mecanismo atual (`select_cohort`)

1. Ordena por `(tag_rank, tag_counts, origin+session_counts, frame_id)`.
2. `PRIORITY_TAGS` coloca `operator_minute_frame` em primeiro lugar.
3. Quota por tag corta após N seleções — **sem** considerar `chain_classification`, recência ou `origin` da sessão ingest.

## Falha observada (v5)

```
TAG_QUOTA_V5.operator_minute_frame = 4
→ 4 frames overnight prac_soak_2026_09_01 selecionados primeiro
→ 2 espontâneos prac_soak_2026_09_02 elegíveis ficaram de fora
→ 2 prac_directed_test legados entraram (quota 2) — ruído cognitivo
```

## Correção (v5.1 — `recency_first_spontaneous`)

1. Reserva 1 slot operacional (`restart`).
2. Preenche orçamento espontâneo com `chain_classification == spontaneous_cognitive`.
3. Ordena: `origin == prac_soak_2026_09_02` primeiro, depois `timestamp` descendente.
4. `prac_directed_test` quota = 0.
5. v5 não conta como frames consumidos (`include_v5=False` em prior exclusion) — digest v5 nunca replayed.

## Recomendações futuras

| ID | Recomendação | Prioridade |
|----|--------------|------------|
| GQ-01 | Separar quota `spontaneous_cognitive` de `operator_minute_frame` por tag de proveniência | P1 |
| GQ-02 | Cap por `origin` quando ingest recente existe | P1 (implementado em v5.1) |
| GQ-03 | Nunca misturar `prac_directed_test` em coorte cognitiva | P0 (v5.1) |
| GQ-04 | Relatório de cobertura por sessão no build (ver `SESSION-COVERAGE-2026-09-02.md`) | P2 |

## ponytail

Upgrade path: scoring único com pesos configuráveis por `cohort_version` em vez de duas funções `select_cohort*` — só quando v6+ precisar de mais políticas.
