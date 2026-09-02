# Diagnóstico `no_edge` e `partial_evidence` — contexto v5.1

**Data:** 2026-09-02  
**Gate:** 2/5 · `no_edge_rate` agregado ~70% (r7–r13)  
**Relacionado:** `PARTIAL-EVIDENCE-DIAGNOSIS-2026-09-01.md`

---

## 1. `no_edge` — padrão dominante

| Causa | Frequência | Ação |
|-------|------------|------|
| Baseline abstém (NOTHING live → `no_edge` normalizado) | Alta | **Esperado** em frames espontâneos NOTHING; não é falha de schema |
| Structure abstém enquanto baseline em `candidate` | Média | Divergência de **política de entrada**, não `missing_required` |
| Bilateral `no_edge` | Alta | **Não conta** para gate 5 pares |
| `prac_directed` / restart / timeout | Contextual | Prova operacional; fora do gate espontâneo |

### Implicação v5.1

8 envelopes `spontaneous_cognitive` com join NOTHING na sessão 09-02 → **projeção conservadora:** maioria permanece `no_edge` bilateral pós-replay. Isso **não invalida** o replay; confirma ou refuta a projeção com evidência.

---

## 2. `partial_evidence` — corpus

| Sinal | Origem | Quem afeta |
|-------|--------|------------|
| `indicators` / `ohlc` / `structure` = `partial` | Barra 1m incompleta no packet | Ambos perfis (capacity gate) |
| `manifest_trust: degraded_metadata` | Hash stale no enriched legado | Verify OK se hash computado coincide |
| `capacity_gate_pass: false` | Ex.: `1a8dbc33` (3ª linha manifest) | Frame **excluído** da coorte |

**Causa raiz (frozen):** captura em barra parcial — ver recomendação em `PARTIAL-EVIDENCE-DIAGNOSIS-2026-09-01.md`.

**Próxima PRAC:** priorizar fechamento de barra 1m ou `data_quality.state_complete=true` quando aplicável.

---

## 3. Categorias que não contam como par

| Padrão | Exemplo | Conta gate? |
|--------|---------|-------------|
| baseline `thesis_quality` + structure `no_edge` | r7 operator `bb50bbe9` | **Não** |
| bilateral `no_edge` | r10 preflight | **Não** |
| `data_quality_insufficient` | r13 operator frames | **Não** |
| `schema_invalid` | r7 timeout structure | **Não** |
| bilateral `thesis_quality` + `thesis_delta` | r7 directed-02, r10 reconciliation | **Sim** |

---

## 4. Decisão operacional

| Se pós-r14… | Então |
|-------------|-------|
| `no_edge` bilateral nos 8 espontâneos | Gate inalterado — **nova PRAC**, não novo greedy |
| ≥3 novos pares `thesis_quality` | Reavaliar `insufficient_sample` (promoção ainda bloqueada) |
| `partial_evidence` ↑ | Ajustar captura (barras completas), não prompt |
