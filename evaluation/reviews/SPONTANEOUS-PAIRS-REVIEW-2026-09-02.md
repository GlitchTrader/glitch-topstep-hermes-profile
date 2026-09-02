# Revisão dos dois pares espontâneos canônicos (sem promoção)

**Data:** 2026-09-02  
**Gate:** 2/5 — `insufficient_sample` mantido  
**Escopo:** diagnóstico offline; **não** autoriza promoção, agregador ou r14

## Pares

| # | Run | Cenário | Frame | Baseline | Structure | Bilateral `thesis_quality` | Nota |
|---|-----|---------|-------|----------|-----------|----------------------------|------|
| 1 | r7 | SCN-PRAC-DIRECTED-02 | `20260831T173427Z-4ac91997` | candidate | candidate | **Sim** · `thesis_delta: true` | Frame **dirigido** — conta no gate histórico 2/5, não é espontâneo |
| 2 | r10-v2 | SCN-PRAC-RECONCILIATION | `20260901T143431Z-534fefd5` | thesis_quality | thesis_quality | **Sim** · `thesis_delta: true` | Par espontâneo/reconciliation canônico |

## Leitura (sem promoção)

- Ambos provam **divergência mensurável** entre perfis, não superioridade operacional.
- r7 inclui 3 artefatos com drift de normalização — **audit-only**; não recontar como nova evidência.
- r10/r11 no mesmo snapshot de reconciliation: r11 `no_edge`↔`held` — **não** par; r10 permanece o par canônico desse frame.
- Baseline ocasionalmente em `candidate` onde structure abstém (`no_edge`) — política de entrada, não gap de `missing_required`.

## Uso permitido na sequência v5

- Referência de formato bilateral para comparar novos frames espontâneos.
- Critério: novo par só conta se **ambos** perfis em `thesis_quality` comparável e snapshot independente.

## Uso proibido

- Promoção de perfil ou alteração de prompt/adapter mid-stream.
- Inflar gate com divergências unilaterais ou testes dirigidos.
