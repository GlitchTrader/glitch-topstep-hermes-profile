# Checklist de autorização r14 (offline — pendente confirmação humana)

**Gerado:** 2026-09-02  
**Run alvo:** `scenario-live-2026-09-01-r14` (ou sucessor datado)  
**Coorte:** v4-pre-registered · digest `7b858bd3482eb15fd42982fb4a0e585b4501a928736fb9365eea88a692dfc209`  
**Status global:** **BLOCKED** até confirmação humana explícita

---

## 1. Pré-voo

| Item | Status | Evidência |
|------|--------|-----------|
| Scripts gateway (`finalize`, `validate`, `export`) presentes | PASS | `run-r14-preflight.py` 2026-09-02 |
| `SAMPLING-PLAN-R14-2026-09-01.md` presente | PASS | profile |
| `reruns_blocked: true` no registry | PASS | `stratified-cohort-execution-registry.json` |
| Par contrato gateway/profile | PASS | gateway `0.2.5` / profile `0.2.8` |
| Disco livre ≥ 1 GB | PASS | ~1200 GB |
| `validate-prac-capture-chain.py --example` | **PASS** (2026-09-02) |
| Gateway health (opcional offline) | N/A | não consultado nesta rodada |

---

## 2. Manifest / digest

| Item | Status |
|------|--------|
| Manifest v4 registrado | PASS |
| Digest SHA256 estável (re-run) | PASS `7b858bd3…` |
| `verify-stratified-cohort.py` sem skip | PASS 5/5 |
| `chain_complete` no ingest PRAC 2026-09-01 | PASS |
| Inventário v4 arquivado | PASS `unused-cohort-frame-inventory-v4-2026-09-01.json` |

---

## 3. Verify sem skip

| Item | Status |
|------|--------|
| Corpus validation 5/5 | PASS |
| `capacity_gate_validated: true` em todos os envelopes v4 | PASS |
| r12-v1 (`skip_validation: true`) | **audit-only** — não reutilizar |
| `EVALUATION_ALLOW_SKIP_VALIDATION` | **não** definido (correto para produção) |

---

## 4. Custo / token budget

| Item | Valor / limite |
|------|----------------|
| Perfis na coorte | baseline-current, structure (2×5 = 10 invocações mín.) |
| Referência r13 | $0.18065 / 16 invocações |
| Estimativa r14 (linear) | ~$0.11–0.20 USD (tokens `gpt-5.6-luna`) |
| Budget operacional | Ver `OPERATIONS-BUDGET-SPEC.md` — sessão única OK; latência agregada r7–r9 informativa |
| Paralelismo | **BLOCKED** |

---

## 5. OAuth evaluation

| Item | Status |
|------|--------|
| Modelo congelado | `gpt-5.6-luna` / `openai-codex` (runs r10–r13) |
| Credenciais nesta rodada | **não usadas** |
| Troca de modelo/prompt | **PROIBIDA** durante medição |

---

## 6. Isolamento

| Item | Status |
|------|--------|
| Produção intocada | Requerido |
| Shadow | **BLOCKED** |
| Agregador executável | **BLOCKED** |
| Hermes live nesta revisão | **não iniciado** |
| Adapter/registry/prompt | **congelados** (`2026-09-01-v1` / `glitch-topstep-v17.1`) |

---

## 7. Estado operacional

| Item | Status |
|------|--------|
| `next_authorized_run_id` | `null` (correto) |
| `r14_authorization` | `pending_explicit_human_approval` |
| Gate cognitivo | **2/5** `insufficient_sample` |
| v4 status | `pre_registered_offline` |
| r12-v1 | histórico / não canônico |
| r12-v2 / r13-v3 | canônicos executados; `promotion_eligible: false` |

---

## 8. Critérios de parada

| Condição | Ação |
|----------|------|
| QC pós-envelope exit ≠ 0 | **PAUSE** coleta (`qc-envelope-collection.py`) |
| Output `invalid` normalizado | Parar se `--stop-on-invalid` (default) |
| Budget de sessão excedido | Parar e registrar |
| Drift de digest mid-run | **ABORT** |
| Novo drift de proveniência | **ABORT** + auditoria |

---

## 9. QC pós-envelope

| Item | Status |
|------|--------|
| Script `qc-envelope-collection.py` disponível | PASS |
| Procedimento FROZEN-COLLECTION-RUNBOOK | 1 envelope → baseline → structure → QC → next |
| Classificação protocolo pós-run | Gerar `r14-protocol-classification-*.json` |

---

## 10. Rollback

| Item | Procedimento |
|------|--------------|
| Registry | Manter `next_authorized_run_id: null`; marcar run como `non_canonical` se abortado |
| Artefatos | Não promover bundles parciais |
| Digest v4 | Imutável — novo run exige novo manifest/digest |
| Gateway/profile | Reverter apenas via paired release — **não** alterar nesta autorização |

---

## 11. Confirmação humana explícita

| Campo | Valor atual |
|-------|-------------|
| Operador autorizou r14? | **NÃO** |
| Data/hora autorização | — |
| Assinatura / ticket | — |
| `next_authorized_run_id` após aprovação | Deve ser definido **manualmente** pelo operador |

---

## Resumo executivo

| Pronto | Bloqueado | Depende de humano |
|--------|-----------|-------------------|
| Coorte v4 verify 5/5 | Execução r14 | Confirmação explícita |
| Digest estável | Gate 2/5 | Aprovação operador |
| Ingest PRAC chain_complete | Paralelismo, shadow, agregador |
| `validate-prac-capture-chain --example` **PASS** | Autorização humana r14 |
| Checklist documentado | Gate 2/5 (captura espontânea) |

**Não autorizar r14** até: (1) confirmação humana registrada; (2) gate cognitivo revisado (ainda insuficiente para promoção).
