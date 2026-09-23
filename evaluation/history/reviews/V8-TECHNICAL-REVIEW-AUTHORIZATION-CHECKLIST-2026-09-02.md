# Revisão técnica e checklist de autorização — replay coorte v8

**Gerado:** 2026-09-02  
**Classificação:** **`READY_WITH_LIMITATIONS`**  
**Run alvo (proposto):** `scenario-live-2026-09-02-r16-v8`  
**Coorte:** v8-pre-registered · digest `b4e9289b3a0a57b3a158f8de21fc11cadb1993e1d1d6c678faaade340e043cba`  
**Sessão PRAC:** `PRAC-SOAK-2026-09-02-v8` · origin `prac_soak_2026_09_02_v8`  
**Gate atual:** **2/5** (`insufficient_sample`)  
**Potencial pós-v8 (teto):** **5/5** — 2 pares históricos + até 3 novos envelopes bilaterais  
**Status:** **AUTHORIZED & EXECUTED** — Ari 2026-09-02 · `scenario-live-2026-09-02-r16-v8` COMPLETE

---

## Veredito

A coorte v8 **atende ao mínimo técnico** para um replay de medição sequencial: 3 envelopes novos, capacidade completa, cadeia PRAC íntegra, verify 3/3 sem skip, sem duplicatas nem consumo prévio.

**Limitação principal:** diversidade fraca — janela curta (~12 min), tag/origem únicas, decisões concentradas em MNQ/`NOTHING`. A coorte **justifica medição**, mas **não** alega diversidade forte nem superioridade de perfil.

---

## Confirmação humana (preencher)

| Campo | Valor |
|-------|-------|
| Revisor | Ari |
| Data UTC | 2026-09-02 |
| Decisão | [x] APROVADO replay v8  [ ] REJEITADO  [ ] ADIADO |
| Classificação aceita | [x] `READY_WITH_LIMITATIONS` |
| Assinatura / referência | autorizado Ari 2026-09-02 |

**Autorizado:** replay v8 sequencial no escopo §9. Agregador, paralelismo, shadow e promoção permanecem **BLOCKED**.

---

## 1. Integridade coorte v8 (pré-assinatura)

| # | Item | Status | Evidência |
|---|------|--------|-----------|
| 1.1 | Manifest v8 canônico | **PASS** | `evaluation/runs/stratified-cohort-manifest-v8-2026-09-02.json` |
| 1.2 | Digest SHA256 `b4e9289b…` | **PASS** | `evaluation/runs/stratified-cohort-digest-v8-2026-09-02.json` |
| 1.3 | `verify-stratified-cohort.py` sem `--skip-validation` | **PASS 3/3** | `all_valid: true` · `envelope_count: 3` |
| 1.4 | Política v8 (exclui v2–v7 + scenario-live) | **PASS** | `STRATIFIED-COHORT-V8-PREREGISTRATION-2026-09-02.md` |
| 1.5 | Classificação | **`READY_WITH_LIMITATIONS`** | diversidade fraca documentada §4 |

### Re-verificação offline (recomendada antes de assinar)

```powershell
cd glitch-topstep-hermes-profile
python scripts\verify-stratified-cohort.py `
  --manifest evaluation\runs\stratified-cohort-manifest-v8-2026-09-02.json `
  --scenarios evaluation\stratified_scenarios.v8.json
python scripts\digest-stratified-cohort.py `
  --manifest evaluation\runs\stratified-cohort-manifest-v8-2026-09-02.json `
  --output evaluation\runs\stratified-cohort-digest-v8-2026-09-02.json
```

Digest re-run deve permanecer: `b4e9289b3a0a57b3a158f8de21fc11cadb1993e1d1d6c678faaade340e043cba`

---

## 2. Frames novos e não consumidos (3/3)

| # | frame_id | packet_id (8) | Classificação | Consumido prévio | capacity_gate |
|---|----------|---------------|---------------|------------------|---------------|
| 2.1 | `20260902T171541Z-4fdd308c` | `4fdd308c` | novo_elegivel | nenhum | **PASS** |
| 2.2 | `20260902T172046Z-86a52bbc` | `86a52bbc` | novo_elegivel | nenhum | **PASS** |
| 2.3 | `20260902T172547Z-c62a7390` | `c62a7390` | novo_elegivel | nenhum | **PASS** |

**Evidência:** `evaluation/runs/prac-frame-consumption-audit-PRAC-SOAK-2026-09-02-v8.json`

| Critério agregado | Resultado |
|------------------|-----------|
| Frames novos | **3/3** |
| Não consumidos por coortes ou replays | **3/3** (`consumed_by_cohorts: []`, `consumed_by_replays: []`) |
| `capacity_gate_pass` | **3/3** |
| Ingest `frames_added` | **3** (`ingest_outcome_class: frames_added`) |

---

## 3. Cadeia PRAC íntegra (3/3)

| # | Item | Status | Evidência |
|---|------|--------|-----------|
| 3.1 | Sessão `PRAC-SOAK-2026-09-02-v8` | **PASS** | `glitch-topstep/docs/evidence/PRAC-SOAK-2026-09-02-v8/` |
| 3.2 | Export `chain_complete: true` | **PASS** | 3 linhas espontâneas NOTHING |
| 3.3 | Ingest `frames_added: 3` | **PASS** | `prac-corpus-ingest-PRAC-SOAK-2026-09-02-v8.json` |
| 3.4 | Archive PRAC preservado | **PASS** | `evaluation/runs/prac-evidence-archive/PRAC-SOAK-2026-09-02-v8/` |
| 3.5 | `packet → snapshot → intent → decisão → receipt` | **PASS** | manifest + decisions/receipts no archive |
| 3.6 | Primeiro ciclo espontâneo | **PASS** | `2026-09-02T17:17:04.457734Z` |

---

## 4. Ausência de duplicatas

| # | Item | Status | Detalhe |
|---|------|--------|---------|
| 4.1 | `packet_id` únicos na fila v8 | **PASS** | 3 IDs distintos |
| 4.2 | `snapshot_hash` (envelope) únicos | **PASS** | 3 hashes distintos no digest |
| 4.3 | Sem overlap com coortes v2–v7 | **PASS** | 48 IDs em `excluded_frame_ids` |
| 4.4 | Inventário unused pós-seleção | **PASS** | `eligible_unused_count: 3` antes da seleção; 0 após pin da fila v8 |

---

## 5. Limitação de diversidade (acknowledgement obrigatório)

| Dimensão | Observação | Impacto |
|----------|------------|---------|
| Janela temporal | ~12 min (`17:14:30` → `17:27:17` UTC) | **fraca** |
| `scenario_tag` | única: `operator_minute_frame` | **fraca** |
| `origin` | única: `prac_soak_2026_09_02_v8` | **fraca** |
| Sessão PRAC | `late_session` (3/3) | **fraca** |
| Decisões live | MNQ · `NOTHING` (3/3) | **fraca** |
| Observação multi-instrumento | MNQ/MES/MCL no packet · decisão single-scope MNQ | ver `V8-MULTI-INSTRUMENT-OBSERVATION-REVIEW-2026-09-02.md` |

**Não inflar a coorte** além dos 3 envelopes elegíveis. Nova PRAC permanece preparada se v8 não produzir pares bilaterais (`evaluation/PHASE-PRAC-COLLECTION-2026-09-02.md`).

| # | Item | Reconhecido? |
|---|------|--------------|
| 5.1 | Diversidade **fraca** — aceita apenas para medição mínima | [x] |
| 5.2 | Coorte **não** suporta alegação de diversidade forte | [x] |
| 5.3 | Se `<5/5` pós-replay: **STOP_RERUNS** v8 → nova PRAC | [x] |

---

## 6. Gate cognitivo e expectativa pós-replay

| # | Item | Valor |
|---|------|-------|
| 6.1 | Gate atual | **2/5** |
| 6.2 | Pares históricos preservados | r7 `SCN-PRAC-DIRECTED-02`, r10 `SCN-PRAC-RECONCILIATION` |
| 6.3 | Teto teórico pós-v8 | **5/5** (2 + 3 novos envelopes **se** todos gerarem `comparable_pair`) |
| 6.4 | Garantia de 5/5 | **nenhuma** — NOTHING live → provável `no_edge` bilateral |
| 6.5 | `≥5/5` após replay | **gate mínimo apenas** — não prova superioridade de perfil |

| # | Item | Reconhecido? |
|---|------|--------------|
| 6.6 | `≥5/5` exige revisão qualitativa antes de agregador offline | [x] |
| 6.7 | Replay útil para evidência; não garante fechamento do gate | [x] |

---

## 7. Componentes congelados

| Item | Valor / status |
|------|----------------|
| Prompt | `glitch-topstep-v17.1` |
| Registry / adapter | `2026-09-01-v1` |
| Modelo | `gpt-5.6-luna` |
| Regras agregador (spec) | **FROZEN** |
| Paralelismo Hermes | **BLOCKED** |
| Agregador executável | **BLOCKED** |
| Shadow / promoção | **BLOCKED** |

**Acknowledgement revisor:** [x] Confirmo que nenhum componente congelado foi alterado desde a PRAC v8.

---

## 8. Custo e latência estimados

| Item | Valor |
|------|-------|
| Escopo | **3 envelopes × 2 perfis = 6 invocações** |
| Modo | replay **sequencial** (1 envelope → baseline → structure → QC → next) |
| Referência r15 v7 | 8 inv · custo proporcional |
| Estimativa linear v8 | **~$0.07–0.09 USD** |
| Latência soma (p50 ref. r14) | **~70 s** (6 × ~11.7 s) |
| Agregador na sessão | **não** |

---

## 9. Escopo de execução (somente pós-assinatura)

| # | Item | Valor |
|---|------|-------|
| 9.1 | Run ID proposto | `scenario-live-2026-09-02-r16-v8` |
| 9.2 | Manifest pinado | `stratified-cohort-manifest-v8-2026-09-02.json` |
| 9.3 | Scenarios pinados | `evaluation/stratified_scenarios.v8.json` |
| 9.4 | Perfis | `baseline-current`, `structure` |
| 9.5 | Invocações totais | **6** |
| 9.6 | Agregador / paralelismo / shadow / promoção | **não executar** |
| 9.7 | `next_authorized_run_id` | **`scenario-live-2026-09-02-r16-v8`** (registrado 2026-09-02) |

### Fila de envelopes (ordem sequencial)

| ordem | scenario_id | frame_id | envelope_id |
|-------|-------------|----------|-------------|
| 1 | `SCN-STRAT-OPERATOR-MINUTE-FRAME-c62a7390` | `20260902T172547Z-c62a7390` | `env-2d581eea30511bd9` |
| 2 | `SCN-STRAT-OPERATOR-MINUTE-FRAME-86a52bbc` | `20260902T172046Z-86a52bbc` | `env-7218421555d4daf9` |
| 3 | `SCN-STRAT-OPERATOR-MINUTE-FRAME-4fdd308c` | `20260902T171541Z-4fdd308c` | `env-5329e8096338d3cf` |

---

## 10. Sequência pós-assinatura

```text
revisão técnica v8 (este documento)
  → assinatura humana
  → registry com run_id scenario-live-2026-09-02-r16-v8
  → replay sequencial (6 invocações)
  → QC / proveniência (V8-REPLAY-QC-CHECKLIST)
  → relatório pós-replay (V8-POST-REPLAY-REPORT-TEMPLATE)
  → novo gate
```

**Proibido:** executar replay antes da assinatura.

### Registry (preencher após assinatura)

```json
"next_authorized_run_id": "scenario-live-2026-09-02-r16-v8",
"v8_pre_registered": {
  "manifest": "evaluation/runs/stratified-cohort-manifest-v8-2026-09-02.json",
  "digest_sha256": "b4e9289b3a0a57b3a158f8de21fc11cadb1993e1d1d6c678faaade340e043cba",
  "classification": "READY_WITH_LIMITATIONS",
  "authorized_by": "<assinatura>",
  "authorized_utc": "<UTC>"
}
```

---

## 11. Artefatos de suporte

| Documento | Path |
|-----------|------|
| Pré-registro v8 | `evaluation/reviews/STRATIFIED-COHORT-V8-PREREGISTRATION-2026-09-02.md` |
| Seleção v8 | `evaluation/reviews/STRATIFIED-COHORT-V8-SELECTION-2026-09-02.md` |
| Sessão PRAC v8 | `evaluation/reviews/V8-PRAC-SESSION-REPORT-2026-09-02.md` |
| Multi-instrumento vs decisão | `evaluation/reviews/V8-MULTI-INSTRUMENT-OBSERVATION-REVIEW-2026-09-02.md` |
| QC pós-replay (template) | `evaluation/reviews/V8-REPLAY-QC-CHECKLIST-2026-09-02.md` |
| Relatório pós-replay (template) | `evaluation/reviews/V8-POST-REPLAY-REPORT-TEMPLATE-2026-09-02.md` |
| Próxima PRAC (fallback) | `evaluation/PHASE-PRAC-COLLECTION-2026-09-02.md` |
