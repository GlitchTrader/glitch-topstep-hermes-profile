# Revisão técnica e checklist de autorização — replay coorte v7

**Gerado:** 2026-09-02  
**Run alvo (proposto):** `scenario-live-2026-09-02-r15-v7`  
**Coorte:** v7-pre-registered · digest `1020808345f1c2c7087cfe5eeedc1b6c33e1d8d1d2cd5d8adaa94d546205778f`  
**Gate atual:** **2/5** (`insufficient_sample`)  
**Potencial pós-v7:** até **6/5** pares agregados teóricos (2 históricos + 4 novos envelopes) — **não garantido**; depende de `thesis_quality` bilateral por frame  
**Status:** **AUTHORIZED** — assinatura Ari 2026-09-02 · `next_authorized_run_id: scenario-live-2026-09-02-r15-v7`

---

## Confirmação humana (preencher)

| Campo | Valor |
|-------|-------|
| Revisor | Ari |
| Data UTC | 2026-09-02 |
| Decisão | [x] APROVADO replay v7  [ ] REJEITADO  [ ] ADIADO |
| Assinatura / referência | aprovado Ari 2026-09-02 |

**Autorizado:** replay v7 sequencial no escopo §7. Agregador, shadow e promoção permanecem **BLOCKED**.

---

## 1. Integridade coorte v7 (pré-assinatura)

| # | Item | Status | Evidência |
|---|------|--------|-----------|
| 1.1 | Manifest v7 canônico | **PASS** | `evaluation/runs/stratified-cohort-manifest-v7-2026-09-02.json` |
| 1.2 | Digest SHA256 `10208083…` | **PASS** | `evaluation/runs/stratified-cohort-digest-v7-2026-09-02.json` |
| 1.3 | `verify-stratified-cohort.py` sem `--skip-validation` | **PASS 4/4** | corpus validation `all_valid: true` |
| 1.4 | Política `recency_first_spontaneous` | **PASS** | origem `prac_soak_2026_09_02_long` |
| 1.5 | v6 preservada, adiada para gate | **PASS** | `V6-GATE-DECISION-2026-09-02.md` · replay v6 **não** autorizado |

### Re-verificação offline (opcional, recomendada antes de assinar)

```powershell
cd glitch-topstep-hermes-profile
python scripts\verify-stratified-cohort.py `
  --manifest evaluation\runs\stratified-cohort-manifest-v7-2026-09-02.json `
  --scenarios evaluation\stratified_scenarios.v7.json
python scripts\digest-stratified-cohort.py `
  --manifest evaluation\runs\stratified-cohort-manifest-v7-2026-09-02.json `
  --output evaluation\runs\stratified-cohort-digest-v7-2026-09-02.json
```

Digest re-run deve permanecer: `1020808345f1c2c7087cfe5eeedc1b6c33e1d8d1d2cd5d8adaa94d546205778f`

---

## 2. Frames novos e não consumidos (4/4)

| # | frame_id | packet_id (8) | Classificação | Consumido prévio | capacity_gate |
|---|----------|---------------|---------------|------------------|---------------|
| 2.1 | `20260902T154027Z-358cec55` | `358cec55` | novo_elegivel | nenhum | **PASS** |
| 2.2 | `20260902T154529Z-db31fa40` | `db31fa40` | novo_elegivel | nenhum | **PASS** |
| 2.3 | `20260902T155028Z-8c4e5912` | `8c4e5912` | novo_elegivel | nenhum | **PASS** |
| 2.4 | `20260902T155530Z-4d39411f` | `4d39411f` | novo_elegivel | nenhum | **PASS** |

**Evidência:** `evaluation/runs/prac-frame-consumption-audit-2026-09-02-long.json`  
**Relatório:** `evaluation/reviews/PRAC-LONG-FRAME-CONSUMPTION-AUDIT-2026-09-02.md`

| Critério agregado | Resultado |
|------------------|-----------|
| Frames novos | **4/4** |
| Não consumidos por coortes v2–v6 ou replays | **4/4** (`consumed_by_cohorts: []`, `consumed_by_replays: []`) |
| `capacity_gate_pass` | **4/4** |

---

## 3. Cadeia PRAC íntegra

| # | Item | Status | Evidência |
|---|------|--------|-----------|
| 3.1 | Sessão `PRAC-SOAK-2026-09-02-long` | **PASS** | gateway `docs/evidence/PRAC-SOAK-2026-09-02-long/` |
| 3.2 | Export `chain_complete: true` | **PASS** | 4 linhas espontâneas NOTHING |
| 3.3 | Ingest `frames_added: 4` | **PASS** | `prac-corpus-ingest-PRAC-SOAK-2026-09-02-long.json` |
| 3.4 | Archive PRAC preservado | **PASS** | `evaluation/runs/prac-evidence-archive/PRAC-SOAK-2026-09-02-long/` |
| 3.5 | `packet → snapshot → intent → decisão → receipt` | **PASS** | manifest + decisions/receipts no archive |
| 3.6 | Captura sem forçar entradas | **PASS** | 4 ciclos espontâneos; prompt/adapter/registry inalterados |

---

## 4. Ausência de duplicatas

| # | Item | Status | Detalhe |
|---|------|--------|---------|
| 4.1 | `packet_id` únicos na fila v7 | **PASS** | 4 IDs distintos |
| 4.2 | `snapshot_hash` (envelope) únicos | **PASS** | 4 hashes distintos no digest |
| 4.3 | Sem overlap com coortes v2–v6 | **PASS** | 44 IDs em `excluded_frame_ids` |
| 4.4 | Inventário unused pós-seleção | **PASS** | `eligible_unused_count: 0` em `unused-cohort-frame-inventory-v7-2026-09-02.json` |

---

## 5. Componentes congelados

| Item | Valor / status |
|------|----------------|
| Prompt | `glitch-topstep-v17.1` |
| Registry / adapter | `2026-09-01-v1` |
| Modelo | `gpt-5.6-luna` |
| Regras agregador (spec) | **FROZEN** · fixtures 12/12 |
| Paralelismo Hermes | **BLOCKED** |
| Agregador executável | **BLOCKED** |
| Shadow / promoção | **BLOCKED** |

**Acknowledgement revisor:** [x] Confirmo que nenhum componente congelado foi alterado desde a PRAC long.

---

## 6. Custo e latência estimados

| Item | Valor |
|------|-------|
| Escopo | **4 envelopes × 2 perfis = 8 invocações** |
| Modo | replay **sequencial** (1 envelope → baseline → structure → QC → next) |
| Referência r14 v5.1 | 18 inv · $0.203 · p50 **11 679 ms** / inv |
| Estimativa linear v7 | **~$0.09–0.11 USD** |
| Latência soma (p50) | **~93 s** (8 × 11.7 s) |
| Latência soma (p95 ref.) | **~131 s** (8 × 16.4 s) |
| Agregador na sessão | **não** — somente replay + QC |

| Limiar operacional | Reconhecido? |
|--------------------|--------------|
| Custo dentro do orçamento de avaliação offline | [ ] |
| Latência sequencial aceitável (~2 min) | [ ] |

---

## 7. Escopo de execução (pós-assinatura)

| # | Item | Valor |
|---|------|-------|
| 7.1 | Run ID proposto | `scenario-live-2026-09-02-r15-v7` |
| 7.2 | Manifest pinado | `stratified-cohort-manifest-v7-2026-09-02.json` |
| 7.3 | Scenarios pinados | `evaluation/stratified_scenarios.v7.json` |
| 7.4 | Perfis | `baseline-current`, `structure` |
| 7.5 | Invocações totais | **8** |
| 7.6 | Agregador | **não executar** nesta fase |
| 7.7 | `next_authorized_run_id` | **`scenario-live-2026-09-02-r15-v7`** (registrado 2026-09-02) |

### Fila de envelopes (ordem sequencial)

| ordem | scenario_id | frame_id | envelope_id |
|-------|-------------|----------|-------------|
| 1 | `SCN-STRAT-OPERATOR-MINUTE-FRAME-4d39411f` | `20260902T155530Z-4d39411f` | `env-04f49708157926e4` |
| 2 | `SCN-STRAT-OPERATOR-MINUTE-FRAME-8c4e5912` | `20260902T155028Z-8c4e5912` | `env-642ad737ef8a4420` |
| 3 | `SCN-STRAT-OPERATOR-MINUTE-FRAME-db31fa40` | `20260902T154529Z-db31fa40` | `env-cdacdb4c49dffbb8` |
| 4 | `SCN-STRAT-OPERATOR-MINUTE-FRAME-358cec55` | `20260902T154027Z-358cec55` | `env-cd054bdd570306e1` |

---

## 8. Expectativa cognitiva e gate (acknowledgement obrigatório)

| # | Item | Reconhecido? |
|---|------|--------------|
| 8.1 | Gate atual permanece **2/5** até novo cálculo pós-replay | [x] |
| 8.2 | v7 **pode** fechar gap para **≥5/5** — diferente de v6 (cap 4/5) | [x] |
| 8.3 | **`≥5/5` é gate mínimo**, não prova de superioridade de perfil | [x] |
| 8.4 | NOTHING live → provável `no_edge` bilateral em parte dos frames | [x] |
| 8.5 | Replay útil para evidência; **não** garante 5/5 | [x] |
| 8.6 | Se gate **<5/5** após r15: **não** repetir v7 → nova coleta PRAC com diversidade adicional | [x] |
| 8.7 | Se gate **≥5/5**: revisão qualitativa formal **antes** de agregador offline | [x] |

### Ressalva pós-gate (se ≥5/5)

Antes do agregador determinístico offline, confirmar:

- independência dos pares;
- estabilidade intra-perfil;
- ausência de viés de seleção;
- cobertura de instrumentos e regimes;
- correlação/diversidade entre perfis;
- custo e latência aceitáveis;
- revisão qualitativa das teses.

---

## 9. Sequência pós-assinatura (obrigatória)

```text
autorização humana (este checklist assinado)
  → replay v7 sequencial (r15)
  → QC de 8 invocações
  → auditoria de proveniência
  → cálculo do gate (apply-sample-quality-gate.py)
```

### 9.1 Replay sequencial

- [ ] `verify-stratified-cohort.py` exit 0 imediatamente antes do replay
- [ ] `run-scenario-live-replay.py` com manifest v7 pinado — **sem** paralelismo
- [ ] 8/8 invocações `completed` · `invalid: 0`

### 9.2 QC (8 invocações)

- [ ] `qc-envelope-collection.py` por envelope (ou batch equivalente)
- [ ] Contrato de saída válido em todas
- [ ] Hash snapshot/envelope estável pré/pós
- [ ] `evaluation_only: true` · produção intocada

### 9.3 Auditoria de proveniência

- [ ] `audit-artifact-provenance.py` no bundle r15
- [ ] Cohort provenance audit atualizado
- [ ] Sem drift em componentes congelados

### 9.4 Cálculo do gate

- [ ] `apply-sample-quality-gate.py` (agregado histórico + r15)
- [ ] `report-evaluation-quality.py` / `report-insufficient-sample.py` se aplicável
- [ ] Atualizar `GATE_STATUS.md` e registry — **sem** `promotion_eligible: true` automático

---

## 10. Ramificações pós-gate

| Resultado | Ação |
|-----------|------|
| **≥5/5** | Revisão qualitativa formal → simulação offline agregador determinístico → auditoria → shadow controlado |
| **<5/5** | **STOP** reruns v7 · registrar STOP · abrir nova coleta PRAC (diversidade adicional) |

---

## 11. Autorização registry — **REGISTRADO** 2026-09-02

```json
"next_authorized_run_id": "scenario-live-2026-09-02-r15-v7",
"v7_pre_registered": {
  "replay_authorization": "approved_2026-09-02T16:18:00Z_Ari",
  "authorization_checklist": "evaluation/reviews/V7-TECHNICAL-REVIEW-AUTHORIZATION-CHECKLIST-2026-09-02.md"
}
```

Replay v7 **desbloqueado** no escopo aprovado (§7). Agregador, shadow e promoção permanecem bloqueados.

---

## Referências

| Artefato | Caminho |
|----------|---------|
| Seleção v7 | `evaluation/reviews/STRATIFIED-COHORT-V7-SELECTION-2026-09-02.md` |
| Auditoria consumo | `evaluation/reviews/PRAC-LONG-FRAME-CONSUMPTION-AUDIT-2026-09-02.md` |
| Decisão v6 | `evaluation/reviews/V6-GATE-DECISION-2026-09-02.md` |
| Runbook sequencial | `evaluation/FROZEN-COLLECTION-RUNBOOK.md` |
| Gate status | `evaluation/GATE_STATUS.md` |
| Registry | `evaluation/runs/stratified-cohort-execution-registry.json` |
