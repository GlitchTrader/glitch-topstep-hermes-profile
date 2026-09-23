# Plano de promoção — RASCUNHO (inativo)

**Status:** `DRAFT` · **NÃO ATIVAR** · `promotion_use_allowed: false`  
**Pré-requisitos não atendidos:** gate 5/5 · agregador não executado · shadow blocked

---

## Fases (somente após gate e QC)

| Fase | Critério entrada | Ação | Saída |
|------|------------------|------|-------|
| P0 | Gate `insufficient_sample: false` | Revisão humana amostra | Go/no-go documentado |
| P1 | r14+ QC PASS · proveniência 0 drift novo | Shadow **read-only** (se política permitir) | Relatório shadow |
| P2 | Agregador spec + fixtures 12/12 · executor implementado | Executor em sandbox | `ensemble_selection` auditável |
| P3 | N runs estáveis · custo dentro budget | Promoção armed (gateway) | Rollback runbook |

---

## Stop lines (frozen)

- Não promover com gate <5 pares bilaterais `thesis_quality`.
- Não promover com `promotion_eligible: false` nos runs canônicos.
- Não alterar prompt/adapter entre P1 medição e P3.
- TS-AUTH-02 / TS-DATA-01 / TS-MULTI-04 inalterados.

---

## Rollback

| Gatilho | Ação |
|---------|------|
| Drift proveniência pós-promoção | Reverter paired contract + registry snapshot |
| QC falha em produção | `armed` → `observe` via gateway |
| Custo > 2× baseline r13 | Pausar e revisar budget |

---

## Estado atual

```text
Fase ativa:     nenhuma
Promoção:       BLOCKED
Próximo gate:   replay v5.1 → recalcular 2/5
```
