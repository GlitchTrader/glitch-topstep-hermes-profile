# Análise pós-r14 — `no_edge` bilateral e caso `e8df6b82`

**Data:** 2026-09-02  
**Run:** `scenario-live-2026-09-02-r14-v5.1`  
**Escopo:** diagnóstico offline — **não** implica vitória/derrota de perfil

---

## 1. `no_edge` bilateral — prudência ou evidência parcial?

### Observação r14

| Métrica | Valor |
|---------|-------|
| Cenários com bilateral `no_edge` | **8/9** |
| `no_edge_rate` (invocações) | **94.4%** (17/18) |
| `missing_required_evidence` | **0** em todas as invocações |
| `completeness` dominante | `indicators:partial`, `ohlc:partial`, `structure:partial` |
| `invalid_count` | **0** |

### Diagnóstico

| Fator | Peso | Evidência |
|-------|------|-----------|
| **Prudência cognitiva** | Alto | Frames espontâneos NOTHING no live; teses baseline citam conflito de delta, falta de assimetria risco/retorno |
| **Evidência parcial (corpus)** | Alto | Barra 1m parcial em todos os envelopes; `partial_evidence` congelado como limitação de captura |
| **Política de entrada divergente** | Médio | 1/9 frames (`e8df6b82`): structure `candidate`, baseline `no_edge` no **mesmo** snapshot |

**Conclusão:** o padrão dominante é **abstinência alinhada** sob evidência parcial + contexto NOTHING — não falha de contrato nem invalidação. Não é possível separar totalmente prudência de teto de evidência sem captura com barras completas e mais regimes.

**Não é leitura correta:** “baseline venceu” ou “structure falhou”. Ambos abstiveram na maioria; amostra bilateral `thesis_quality` insuficiente.

---

## 2. Caso `e8df6b82` (`20260902T020023Z-e8df6b82`)

| Campo | baseline-current | structure |
|-------|------------------|-----------|
| `normalized.state` | `no_edge` | `candidate` |
| `direction` | flat | short |
| `action` | NOTHING | ENTER_SHORT |
| `missing_required` | [] | [] |
| `comparable` (gate) | true | true |
| `completeness` | partial ohlc/structure | idem |
| Latência | 11.0s | 16.4s |
| Custo | $0.0113 | $0.0115 |

### Tese baseline (resumo)

Bearish macro, mas preço no limite inferior do range; delta 15s vendedor conflita com delta 60s/300s neutro/positivo; continuação sem assimetria; reversão sem reclaim confirmado → **abstém**.

### Tese structure (resumo)

Continuação bearish alinhada em 5m/15m/60m abaixo de EMAs/VWAP; pressão vendedora 15s; favorece short em direção ao low 5m anterior.

### Interpretação

- **Mesmo envelope**, mesma classificação de capacidade — divergência é de **política de entrada**, não de `missing_required` nem `not_comparable`.
- Baseline aplicou critério mais conservador (conflito de fluxo + proximidade de range).
- Structure emitiu candidato direcional com entry/stop/target — conta como `thesis_quality` **unilateral**, **não** par bilateral.
- Padrão histórico similar: r12-v2 operator `a49c317a` (baseline `no_edge`, structure `thesis_quality`).

**Uso permitido:** evidência de divergência de política para futura análise qualitativa — **não** infla gate 2/5.

---

## 3. Implicação para próxima PRAC

| Objetivo captura | Motivo |
|------------------|--------|
| Barras 1m completas | Reduzir teto `partial` |
| Ciclos espontâneos contínuos | Mais frames com decisão real, não só NOTHING |
| reconciliation / preflight | Buckets com histórico de par bilateral |
| Horários diversos | Reduzir viés overnight NOTHING |
| Outros instrumentos | Quando política permitir |

Até obter **≥3 novos pares** `thesis_quality` bilaterais, agregador offline permanece prematuro.
