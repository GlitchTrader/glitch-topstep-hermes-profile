# Auditoria de elegibilidade de qualidade — amostra efetiva

**Data:** 2026-09-02 (offline)  
**Escopo:** v4 vs r7–r13 · separação contrato / proveniência / dirigido / tese  
**Gate congelado:** `sample_quality_gate.v1.json` · mínimo **5** pares comparáveis independentes

---

## Resumo da amostra efetiva

| Camada | Contagem | Conta para gate? |
|--------|----------|------------------|
| Pares bilaterais `thesis_quality` (r7+r10 canônicos) | **2** | **Sim** |
| Novos pares r11–r13 | **0** | Não |
| Envelopes v4 espontâneos (pré-replay) | **2** potenciais | Só após replay autorizado |
| Envelopes v4 dirigidos | **3** | **Não** |
| Drift r7 (3 artefatos) | preservados | **Não** — evidência histórica audit-only |
| r12-v1 (`skip_validation`) | 36 artefatos | **Não** — não canônico |

**Veredito amostra:** `insufficient_sample` — **2/5** mantido.

---

## Comparação por run (adapter `2026-09-01-v1` homogêneo r8–r13)

| Run | Invocações | Válidos | Pares novos | Adapter misturado? | Notas |
|-----|------------|---------|-------------|-------------------|-------|
| r7-contract | 6 | 6 | 1 | r7: 3 drift histórico | **Não** recontar drift como nova evidência |
| r8-contract | 6 | 6 | 0 | Não | Contrato only |
| r9-v2 | 14 | 14 | 0 | Não | Corpus v2 |
| r10-v2 | 14 | 14 | 1 | Não | SCN-PRAC-RECONCILIATION bilateral histórico |
| r11-v2 | 12 | 12 | 0 | Não | Fila frozen |
| r12-stratified (v1) | 18 | 18 | 0 | Não | **skip_validation** — audit-only |
| r12-stratified-v2 | 18 | 18 | 0 | Não | Canônico 9/9 corpus |
| r13-stratified-v3 | 16 | 16 | 0 | Não | Último MNQ esgotado |
| v4 (pré-registro) | 0 replay | — | 0 | Não | 2 espontâneos + 3 dirigidos na fila |

---

## Separação de evidência

### Contrato de saída
- r8: 100% válidos — prova schema/normalização
- r9–r13: 100% válidos pós-adapter v1
- **Não** infla pares comparáveis

### Proveniência / normalização
- 104 artefatos escaneados; 3 drift r7 conhecidos (`historical_normalization_version`)
- r12-v1 alinhado ao adapter atual mas **protocol_conformance: CONDITIONAL** por skip
- v4 ingest: `chain_complete` prova cadeia operacional PRAC

### Execução dirigida
- Testes 6–8: `prac_directed_execution` no ingest
- Fila v4: restart + timeout + prac_directed_test legado
- **Excluídos** do numerador de tese espontânea

### Qualidade de tese (espontânea)
- Únicos pares canônicos: r7 `SCN-PRAC-DIRECTED-02`, r10 `SCN-PRAC-RECONCILIATION`
- r13 divergências unilaterais (`candidate` vs `no_edge`) — diagnóstico em `DIVERGENCE-QUALITATIVE-R7-R13-2026-09-01.md`
- v4: 2 frames `operator_minute_frame` com `spontaneous_cognitive` — **única** extensão potencial pós-r14

---

## Regras de exclusão aplicadas

| Exclusão | Motivo |
|----------|--------|
| Drift r7 re-normalizado | Contagem histórica preservada; não duplicar |
| r12-v1 | skip-validation; não canônico |
| `no_edge` ↔ `no_edge` | Abstinência alinhada — sem par |
| `not_comparable` | Categoria incompatível |
| Directed tests | Proveniência execução, não espontânea |
| Intra-profile instability | Repetibilidade, não par independente |

---

## Projeção pós-r14 (não autorizado)

| Cenário | Pares máximos adicionais |
|---------|--------------------------|
| Ambos operator espontâneos → bilateral `thesis_quality` | +2 (total 4/5) |
| Um bilateral + três dirigidos só `no_edge` | +0 a +1 |
| Ainda abaixo de 5 | **more_collection** PRAC necessária |

---

## Artefatos

| Arquivo | Uso |
|---------|-----|
| `evaluation/runs/sample-quality-gate-result-2026-09-01.json` | Gate agregado |
| `evaluation/runs/evaluation-quality-report-2026-09-01.json` | Métricas 2/5 |
| `evaluation/runs/corpus-join-report-v4-prep-2026-09-02.json` | Join cognitivo limitado |
| `evaluation/reviews/DIVERGENCE-QUALITATIVE-R7-R13-2026-09-01.md` | Diagnóstico qualitativo |
