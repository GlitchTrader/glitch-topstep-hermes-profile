# Relatório de cobertura — coorte v4 e corpus enriched

**Data:** 2026-09-02 (offline)  
**Corpus:** `tests/fixtures/frozen_corpus/enriched` · 45 entries pós-ingest  
**Coorte v4:** 5 envelopes pré-registrados

---

## Cenários (scenario_tag)

| Tag | No corpus (elegível v4) | Na fila v4 | Lacuna |
|-----|-------------------------|------------|--------|
| operator_minute_frame | 8 | **2** | 6 não selecionados (greedy) |
| prac_directed_test | 3 | **1** | 2 usados em runs anteriores |
| restart | 1 | **1** | — |
| timeout | 1 | **1** | — |
| reconciliation | 1+ | **0** | **LACUNA** — não na fila v4 |
| preflight | 1+ | **0** | **LACUNA** — não na fila v4 |

---

## Sessões / origem

| Origin | Frames elegíveis v4 | Na fila v4 |
|--------|---------------------|------------|
| prac_soak_2026_09_01 | 10 | **4** |
| prac_soak_2026-08-31 | 3 | **1** (legado prac_directed) |

**Sessão PRAC 2026-09-01:** janela `since_utc: 2026-09-02T01:25:00Z` · 9 cadeias espontâneas ingeridas · 11 frames adicionados · 1 duplicata excluída.

---

## Instrumentos

| Instrumento | Corpus | v4 fila |
|-------------|--------|---------|
| MNQ | 45/45 | 5/5 |

**Lacuna:** sem diversidade multi-instrumento no corpus atual.

---

## Regimes

| Regime | Observação |
|--------|------------|
| overnight | 5/5 envelopes v4 (`session_bucket`) |
| afternoon / midsession | Parcial no corpus; sub-representados na fila |

---

## Qualidade das barras

| Aspecto | Status |
|---------|--------|
| `capacity_gate_validated` v4 | **5/5 true** |
| `manifest_trust: degraded_metadata` | 3/5 (hash stale metadata; packet OK) |
| Barra 1m parcial (estrutura) | Documentado em `PARTIAL-EVIDENCE-DIAGNOSIS` |
| Capture bar audit anterior | `CAPTURE-BAR-QUALITY-AUDIT-2026-09-01.md` |

Profile gates offline: `comparable: true`, `allows_directional_evaluation: true` em todos os 5 cenários v4.

---

## Candidatos bilaterais

| Fonte | Pares `thesis_quality` bilateral |
|-------|----------------------------------|
| Histórico r7+r10 | **2** |
| r11–r13 | **0** |
| v4 (potencial pós-replay) | **0–2** (2 frames espontâneos) |
| **Total atual** | **2/5** |

---

## Motivos de exclusão (seleção v4)

| Motivo | Contagem |
|--------|----------|
| Usado em v2/v3 ou runs r7–r13 | 26 frame_ids |
| Snapshot duplicado (teste 07 vs 06) | 1 |
| Greedy não atingiu meta 8–10 | — (5 selecionados) |
| capacity_gate_pass false | frames legados ago/31 |

---

## Lacunas para próximo PRAC

1. **reconciliation** — cenário sem envelope v4
2. **preflight** — cenário sem envelope v4
3. Mais **operator_minute_frame** espontâneos com barra completa e potencial bilateral
4. Pares adicionais para fechar **5/5** gate (faltam ≥3 independentes)
5. Evitar overlap de `snapshot_hash` entre testes dirigidos e espontâneos na mesma sessão

---

## Artefatos

- `evaluation/runs/unused-cohort-frame-inventory-v4-2026-09-01.json`
- `evaluation/reviews/STRATIFIED-COHORT-V4-SELECTION-2026-09-01.md`
- `evaluation/runs/capture-bar-quality-audit-2026-09-01.json`
