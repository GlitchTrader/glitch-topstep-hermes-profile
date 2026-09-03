# Auditoria — frames PRAC-SOAK-2026-09-02-diversity

**Data:** 2026-09-02  
**Sessão:** `PRAC-SOAK-2026-09-02-diversity` · `chain_complete: true`  
**Artefato JSON:** `evaluation/runs/prac-frame-consumption-audit-2026-09-02-diversity.json`

---

## Interpretação de `frames_added: 0` (primeiro ingest)

**Não** significava “já no corpus consumido”. Significava **falha de ingest**:

| Causa | Detalhe |
|-------|---------|
| Path errado | `run-prac-corpus-ingest.ps1` apontava para `...\minute-frames` em vez de `...\state\minute-frames` |
| Efeito | `exclusion_reason: minute_frame_not_found_for_chain` nos 3 packets |
| Evidência PRAC | Archive preservado (`PRAC-proven`) independentemente do corpus enriched |

**Correção:** path do PS1 alinhado ao default de `build-enriched-corpus.py`.  
**Re-ingest:** `frames_added: 3` · `exclusion_breakdown: { directed_test_missing: 3 }` (testes 6–8 ausentes na sessão — esperado).

---

## Classificação por frame (pós re-ingest, pré-coorte v6)

| packet_id (8) | frame_id | Classificação | Cohort/replay prévio | capacity_gate | Coorte v6 |
|---------------|----------|---------------|----------------------|---------------|-----------|
| `fedf09de` | `20260902T151525Z-fedf09de` | **novo_elegivel** | nenhum | PASS | incluído |
| `8ff26413` | `20260902T152026Z-8ff26413` | **insufficient_capacity** | nenhum | FAIL | excluído |
| `56090490` | `20260902T152528Z-56090490` | **novo_elegivel** | nenhum | PASS | incluído |

Todos: `spontaneous_cognitive` · origem `prac_soak_2026_09_02_diversity` · archive PRAC íntegro.

**Nota hashes:** `market_snapshot_hash` no evidence-chain é o hash do **intent**; o corpus enriched usa hash de **envelope** computado — verify v6 **2/2 PASS** com `manifest_trust: ok`.

---

## Coorte v6 (offline)

| Item | Valor |
|------|-------|
| Envelopes | **2** (afternoon · diversity origin) |
| Digest | `evaluation/runs/stratified-cohort-digest-v6-2026-09-02.json` |
| Verify | **2/2** sem `--skip-validation` |
| Seleção | `STRATIFIED-COHORT-V6-SELECTION-2026-09-02.md` |

**Não autoriza replay** — revisão técnica + autorização humana obrigatórias.

---

## Gate cognitivo (expectativa)

3 frames NOTHING com comparação multi-instrumento = **cobertura comportamental útil**; projeção conservadora: maioria `no_edge` bilateral → **improvável** fechar gap 2/5→5/5 só com 2 envelopes novos.

**Segunda sessão PRAC longa:** somente se revisão confirmar que v6 não justifica replay (amostra < mínimo independente).

---

## Bloqueios inalterados

Agregador executável · paralelismo · shadow · promoção · `next_authorized_run_id: null`
