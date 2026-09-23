# Revisão técnica e checklist de autorização — replay coorte v9

**Gerado:** 2026-09-02  
**Classificação:** **`READY_WITH_LIMITATIONS`**  
**Run alvo (proposto):** `scenario-live-2026-09-02-r17-v9`  
**Coorte:** v9-pre-registered · digest `59093a3a770107f0abe0173cfcd98d4746fd908ff3429b55a15ade0e56d56674`  
**Sessão PRAC:** `PRAC-SOAK-2026-09-02-v9` · origin `prac_soak_2026_09_02_v9`  
**Gate atual:** **2/5** (`insufficient_sample`)  
**Potencial pós-v9 (teto agregado):** **6/5** — 2 pares históricos + até 4 novos envelopes (não garante pares bilaterais)  
**Status:** **AUTHORIZED** — Ari 2026-09-02 · replay `scenario-live-2026-09-02-r17-v9` autorizado

---

## Veredito

A coorte v9 **atende ao mínimo técnico** para um replay de medição sequencial: 4 envelopes `novo_elegivel`, capacidade completa nos selecionados, cadeia PRAC íntegra, verify **4/4** sem skip, sem duplicatas nem consumo prévio.

**Limitação principal:** diversidade **limitada** — janela ~22 min, tag/origem únicas, `instrument_decided=MNQ` em 6/6 ciclos (`NOTHING`), observação multi-instrumento (MNQ/MES/MCL) sem decisão fora de MNQ. A coorte **justifica medição**, mas **não** alega diversidade forte nem novos pares bilaterais.

---

## Confirmação humana (preencher antes do replay)

| Campo | Valor |
|-------|-------|
| Revisor | Ari |
| Data UTC | 2026-09-02 |
| Decisão | [x] APROVADO replay v9  [ ] REJEITADO  [ ] ADIADO |
| Classificação aceita | [x] `READY_WITH_LIMITATIONS` |
| Assinatura / referência | autorizado Ari 2026-09-02 |

**Autorizado:** replay v9 sequencial no escopo §6. Agregador, paralelismo, shadow e promoção permanecem **BLOCKED**.

---

## 1. Integridade coorte v9

| # | Item | Status | Evidência |
|---|------|--------|-----------|
| 1.1 | Manifest v9 | **PASS** | `evaluation/runs/stratified-cohort-manifest-v9-2026-09-02.json` |
| 1.2 | Digest SHA256 `59093a3a…` | **PASS** | `evaluation/runs/stratified-cohort-digest-v9-2026-09-02.json` |
| 1.3 | `verify-stratified-cohort.py` sem skip | **PASS 4/4** | `all_valid: true` |
| 1.4 | Política v9 (exclui v2–v8 + scenario-live) | **PASS** | `STRATIFIED-COHORT-V9-PREREGISTRATION-2026-09-02.md` |
| 1.5 | Classificação | **`READY_WITH_LIMITATIONS`** | §5 |

---

## 2. Frames novos (4/4 selecionados; 2 excluídos por capacidade)

| # | frame_id | Classificação | capacity | Na coorte |
|---|----------|---------------|----------|-----------|
| 2.1 | `20260902T180851Z-c5f24442` | novo_elegivel | PASS | **sim** |
| 2.2 | `20260902T181051Z-ab6e5383` | novo_elegivel | PASS | **sim** |
| 2.3 | `20260902T181554Z-79fa9dae` | insufficient_capacity | FAIL | **não** |
| 2.4 | `20260902T182055Z-08066af5` | novo_elegivel | PASS | **sim** |
| 2.5 | `20260902T182551Z-54dde640` | insufficient_capacity | FAIL | **não** |
| 2.6 | `20260902T183055Z-92f0a8a8` | novo_elegivel | PASS | **sim** |

**Evidência:** `evaluation/runs/prac-frame-consumption-audit-PRAC-SOAK-2026-09-02-v9.json`

| Critério agregado | Resultado |
|------------------|-----------|
| `novo_elegivel` | **4** |
| `insufficient_capacity` | **2** |
| `already_consumed` | **0** |
| Ingest `frames_added` | **6** |

---

## 3. Cadeia PRAC

| # | Item | Status |
|---|------|--------|
| 3.1 | `chain_complete: true` | **PASS** |
| 3.2 | Archive preservado | **PASS** |
| 3.3 | Production paths unchanged | **PASS** (offline only) |

Relatório: `evaluation/reviews/V9-PRAC-SESSION-REPORT-2026-09-02.md`

---

## 4. Duplicatas e proveniência

| Revisão | Veredito |
|---------|----------|
| Duplicatas | **PASS** — `V9-COHORT-DUPLICATE-REVIEW-2026-09-02.md` |
| Proveniência | **PASS** — `V9-COHORT-PROVENANCE-REVIEW-2026-09-02.md` |

---

## 5. Limitações obrigatórias (`READY_WITH_LIMITATIONS`)

| Dimensão | Observação |
|----------|------------|
| Janela temporal | ~**22 min** (`18:10:06` → `18:32:29` UTC) |
| `scenario_tag` | única: `operator_minute_frame` |
| `origin` | única: `prac_soak_2026_09_02_v9` |
| Instrumentos observados | MNQ, MES, MCL (evidence) |
| `instrument_decided` | **MNQ only** (6/6 · NOTHING) |
| Ciclos exportados | 6 espontâneos · todos NOTHING |
| Capacidade na coorte | **4/4** envelopes `capacity_gate_validated` |
| Gate agregado (teto) | 2/5 → no máximo **6/5** se todos bilaterais — **não garantido** |

---

## 6. Escopo replay proposto (não autorizado)

```text
4 envelopes × 2 perfis = 8 invocações sequenciais
run_id proposto: scenario-live-2026-09-02-r17-v9
```

## 7. Bloqueios mantidos

```text
agregador executável · paralelismo Hermes · shadow · paper · canary · promoção
alteração prompt/adapter/registry semântico
```

---

## Referências

- Seleção: `evaluation/reviews/STRATIFIED-COHORT-V9-SELECTION-2026-09-02.md`
- Inventário: `evaluation/runs/unused-cohort-frame-inventory-v9-2026-09-02.json`
- Registry: `evaluation/runs/stratified-cohort-execution-registry.json` · bloco `v9_pre_registered`
