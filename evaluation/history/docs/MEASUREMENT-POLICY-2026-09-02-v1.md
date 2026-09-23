# Política de medição — versão 2026-09-02-v1

**Status:** `PENDING_HUMAN_SIGNATURE`  
**Substitui:** gate único implícito (direcional apenas)  
**Gate direcional histórico:** **preservado** (`2/5` · `directional_gate_v1`)

```text
measurement_policy_approval = pending_human
next_authorized_run_id      = null
STOP_RERUNS                 = ativo (v2–v9)
```

---

## Trilhas adotadas

| Trilha | ID | Promoção |
|--------|-----|----------|
| Direcional | `quality_gate_directional` | bloqueada até critério v1 satisfeito |
| Abstinência | `abstention_diagnostic` | **nunca** (`promotion_use_allowed=false`) |

---

## Gate direcional — duas visões

### `directional_gate_v1` (imutável)

- Fonte: `evaluation/runs/directional-gate-report-2026-09-02-v1.json`
- Numerador histórico: **2** pares bilaterais `thesis_quality`
- **Não recalcular** sem nova versão de relatório

### `directional_gate_v2` (estratificado)

- Fonte: `evaluation/runs/directional-gate-report-2026-09-02-v2.json`
- Estratos por frame:

| Estrato | Frames |
|---------|--------|
| `spontaneous` | 40 |
| `directed` | 7 |
| `insufficient_capacity` | 6 |
| `no_edge_bilateral` | 31 |
| `unilateral_candidate` | 6 |
| `comparable_pairs` (total) | **2** (1 dirigido · 1 espontâneo) |

**Regra:** não misturar pares dirigidos e espontâneos em uma única conclusão de qualidade.

---

## Abstinência

- Spec: `evaluation/ABSTENTION-DIAGNOSTIC-SPEC.md` (`FROZEN`)
- Relatório: `evaluation/runs/abstention-diagnostic-report-2026-09-02-v1.json`

---

## Oportunidade

- Relatório: `evaluation/reviews/OPPORTUNITY-FUNNEL-REPORT-2026-09-02.md`
- JSON: `evaluation/runs/opportunity-funnel-report-2026-09-02-v1.json`

---

## Coleta adicional (máximo uma)

**Pré-condição:** assinatura humana desta política.

**Permitido após aprovação:**

```text
1 PRAC diversificada
→ export chain_complete
→ ingest
→ coorte pré-registrada (não v10 automático — nova versão se aprovada)
→ revisão técnica
→ autorização humana
→ replay sequencial
→ directional_gate_v* + abstention_diagnostic
```

**Critério de parada:**

```text
novos pares bilaterais suficientes para fechar gate direcional
OU
zero novos pares após coleta limitada
→ PARAR e revisar desenho (sem cadeia indefinida de PRACs)
```

**Proibido:** forçar entradas · v10 antes da assinatura · replay exploratório.

---

## Bloqueios mantidos

```text
agregador executável
paralelismo Hermes
shadow / paper / canary
promoção
```

---

## Plano global (~52%)

| Área | Estado |
|------|--------|
| Avaliação / coordenação | madura |
| Fase 5 → política mensurável | **esta versão** |
| Agregador executável | não iniciado |
| Shadow / paper / canary / roteamento | não iniciado |

---

## Assinatura humana (bloqueio)

| Campo | Valor |
|-------|-------|
| Aprovado por | **Ari** |
| Data UTC | **2026-09-02T19:30:00Z** |

`measurement_policy_approval` → **approved** (registry atualizado pós-assinatura).

---

## Sequência única pós-assinatura

Ver `evaluation/COLLECTION-CLOSURE-PLAN.md`.

1. `measurement_policy_approval=approved` (registry)
2. **Uma** PRAC limitada · objetivo: novos pares direcionais + diagnóstico abstinência
3. Critério de parada: novos pares **ou** zero → encerrar coleta atual
4. Pipeline: export → ingest → auditoria → coorte → verify → revisão → autorização → replay → gates

**Não** iniciar coleta sem assinatura.

---

## Ferramentas offline (implementadas)

| Ferramenta | Path |
|------------|------|
| Gate estratificado (visão única) | `scripts/report-directional-gate-stratified.py` |
| Outcome abstinência (diagnóstico) | `scripts/build-abstention-outcome-associations.py` |
| Plano encerramento | `evaluation/COLLECTION-CLOSURE-PLAN.md` |

```text
preparatory_artifacts: CLOSED — não criar novos checklists/relatórios preparatórios
```
