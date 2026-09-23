# Pré-registro coorte v9 — PRAC diversa

**Data:** 2026-09-02  
**Status:** `PRE_REGISTERED_OFFLINE` · aguarda nova PRAC  
**Substitui:** tentativas de reruns v7/v8 (ambos `STOP_RERUNS`)

---

## Objetivo

Coletar **≥3 frames espontâneos elegíveis** com **diversidade real** — não inflar coorte a partir de janelas curtas MNQ/NOTHING. Instrumentos: observar naturalmente; excluir frames sem capacidade comparável.

---

## Critérios de captura PRAC (obrigatórios)

| Critério | Meta |
|----------|------|
| Janela temporal | **>30 min** preferencial; múltiplas faixas horárias |
| Instrumentos | **≥2 instrumentos disponíveis** na evidência ou **observados naturalmente** (packet/universe) — **não forçar decisões**; registrar `instrument_decided` efetivo por ciclo |
| Cenários | **≥2** `scenario_tag` ou buckets de sessão distintos |
| Barras | 1m **completas** · `state_complete: true` |
| Ciclos | espontâneos apenas · **sem** forçar entradas |
| Capacidade | `capacity_gate_pass` em todos os candidatos |
| Mínimo ingest | `frames_added ≥ 3` · `novo_elegivel ≥ 3` |

---

## Política de exclusão v9

- Excluir coortes **v2–v8** (manifests estratificados anteriores).
- Excluir frames em bundles `scenario-live-*`.
- Excluir testes dirigidos (`prac_directed_execution`).
- Não reutilizar frames v6/v7/v8.

**Implementação:** `build-stratified-cohort.py --cohort-version v9` · `inventory-unused-cohort-frames.py --cohort-version v9`

---

## Sequência pós-PRAC

```text
export (chain_complete)
→ ingest
→ auditoria consumo
→ inventário v9
→ build v9 --latest-origin prac_soak_<tag>
→ digest → verify (sem skip)
→ revisão técnica
→ autorização humana
→ replay sequencial (r17 proposto)
```

---

## Bloqueios mantidos

- Agregador executável · paralelismo · shadow · paper · canary · promoção
- Repetir v8 ou v7
- `next_authorized_run_id` até assinatura humana

---

## Referências

- `evaluation/reviews/V9-PRAC-SESSION-OPERATOR-CHECKLIST-2026-09-02.md`
- `evaluation/reviews/V9-PRAC-SESSION-REPORT-2026-09-02.md`
- `evaluation/PHASE-PRAC-COLLECTION-2026-09-02.md`
- `docs/evidence/PRAC-PROGRAMMER-RUNBOOK-2026-09-02.md`
- `R15-R16-ABSTENTION-CONSOLIDATION-2026-09-02.md`
