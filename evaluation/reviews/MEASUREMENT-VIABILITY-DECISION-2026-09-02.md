# Decisão de viabilidade de medição — 2026-09-02

**Status:** `FINAL`  
**Sequência:** gate de prontidão implementado → fonte histórica auditada → decisão de viabilidade  
**Bloqueios mantidos:** `next_authorized_run_id=null` · sem v10 · sem r18 · sem nova PRAC · sem agregador

---

## Matriz consolidada

| Dimensão | Resultado |
|----------|-----------|
| Medição direcional | **2/5** pares v1 · **0** espontâneos recentes |
| Medição abstinência | **0** abstinências válidas (PRAC-LIMITED) |
| Qualidade captura | **8/8** degradados ou bloqueados |
| Isolamento | **validado** |
| Custo/latência | **validado** |
| Fonte histórica | **`historical_opportunity_source_unavailable`** |

Fonte machine-readable: `evaluation/runs/viability-decision-matrix-2026-09-02.json`

---

## Paralelo A — gate `evaluation_measurement_ready`

**Implementado** (evaluation lane only — não altera gateway nem trading):

| Componente | Caminho |
|------------|---------|
| Script | `scripts/evaluation-measurement-ready.py` |
| Schema | `evaluation/schemas/evaluation_measurement_ready.v1.json` |
| Testes | `tests/test_evaluation_measurement_ready.py` (11 checks) |
| Runbook | `evaluation/FROZEN-COLLECTION-RUNBOOK.md` |
| Exemplo preflight | `evaluation/runs/measurement-ready-preflight-PRAC-LIMITED-2026-09-02.json` (`ready=true` no instante pré-captura) |
| Exemplo capture | `evaluation/runs/measurement-ready-capture-PRAC-LIMITED-example.json` (`daily_capture_locked` → reprovado) |

Condições de reprovação: `daily_capture_locked` · `gateway_state_incomplete` · `bar_1m_partial` · `bar_1m_lag` · `snapshot_expired` · `insufficient_instrument_capacity` · `evidence_chain_incomplete` · `maintenance_window` · `market_not_valid`.

**Nova PRAC só após** `evaluation_measurement_ready` com `ready=true` em preflight **e** capture por frame.

---

## Paralelo B — auditoria histórica

**Artefato:** `evaluation/runs/historical-opportunity-audit-2026-09-02.json`

| Métrica | Valor |
|---------|-------|
| Sessões PRAC auditadas | múltiplas em `docs/evidence/PRAC-*` |
| Joins exatos (packet_id + intent_id + receipt) | **48** |
| Espontâneos | **49** |
| Dirigidos | **0** |
| `candidato_real` (ENTER_*) | **0** |
| `NOTHING` | **49** |
| `daily_capture_locked` (heurística decisão) | **25** |
| Outcome posterior no corpus | **44** (proxy disponível) |
| **Espontâneo real utilizável com outcome** | **0** |

**Veredito:** `historical_opportunity_source_unavailable` — não fabricar dados; não usar testes dirigidos como superioridade.

---

## Paralelo C — decisão quantitativa

### Investimento recomendado: **opção 3**

```text
encerrar ensemble direcional como não mensurável
→ manter artefatos e contratos
→ não implementar agregador
```

### Sub-decisão produto (opção 4 parcial)

A trilha **diagnóstica** de risco/abstinência (`diagnostic_only`, `promotion_use_allowed=false`) pode continuar offline sobre corpus histórico replay — **sem** reabrir coleta direcional até mudança de medição aprovada.

### Respostas objetivas

| Pergunta | Resposta |
|----------|----------|
| Evidência para escolher perfil? | **Não** |
| Ensemble direcional mensurável no fluxo atual? | **Não** |
| Abstinência sem viés operacional? | **Não** (lock domina PRACs) |
| Conclusão produto | **Ensemble direcional encerrado por falta de evidência** |

---

## Conclusão formal (uma de três)

```text
☐ ensemble mensurável e justificável
☐ ensemble limitado a diagnóstico          ← camada offline permitida
☑ ensemble direcional encerrado por falta de evidência
```

---

## Próximo passo (único, não repetir ciclo preparar→coletar→nada)

1. **Aprovar mudança de medição** (design) — ex.: captura só fora de lock + gate PASS + coorte histórica externa **ou**
2. **Aceitar produto diagnóstico** sem seleção de perfil direcional **ou**
3. **Arquivar** hipótese de ensemble direcional.

**Não executar:** v10 · r18 · nova PRAC · agregador · paralelismo · shadow · paper · canary · promoção.

---

## Artefatos

| Trilha | Arquivo |
|--------|---------|
| Gate | `scripts/evaluation-measurement-ready.py` |
| Auditoria histórica | `evaluation/runs/historical-opportunity-audit-2026-09-02.json` |
| Matriz decisão | `evaluation/runs/viability-decision-matrix-2026-09-02.json` |
| Runner | `scripts/run-measurement-viability-decision.py` |
