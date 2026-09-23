# Revisão técnica formal — pacote de coordenação evaluation×cron

**Gerado:** 2026-09-02  
**Escopo:** runtime lease/defer/preflight/smoke/fault (pós-incidente r15)  
**Status:** **APPROVED** (coordenação) · **NÃO** autoriza replay cognitivo nem paralelismo  
**Revisor:** agente técnico + confirmação operacional Ari (plano 2026-09-02)

---

## Escopo e limites

| Incluído | Excluído |
|----------|----------|
| `evaluation_lease.py` + integração cron | Replay cognitivo Hermes |
| Preflight + sync manifest | Agregador executável |
| Smoke live (cron ativo) | Paralelismo Hermes |
| Fault injection (abort/timeout/crash/recovery) | Shadow / paper / canary |
| Registro `LIVE_VALIDATED` | Autorização de `next_authorized_run_id` |

**Leitura correta:** removeu bloqueador de runtime descoberto no r15. **Não** substitui coorte nova nem gate `2/5`.

---

## Confirmação humana (coordenação apenas)

| Campo | Valor |
|-------|-------|
| Pacote | evaluation×cron v1 |
| Decisão | [x] APROVADO coordenação  [ ] REJEITADO  [ ] ADIADO |
| Replay autorizado | **NÃO** — aguarda coorte v8 + autorização explícita |
| Paralelismo | **BLOCKED** (inalterado) |
| Referência plano | Ari 2026-09-02 — sequência pós-lease |

---

## 1. Contrato e artefatos

| # | Item | Status | Evidência |
|---|------|--------|-----------|
| 1.1 | Contrato exclusão v1 | **PASS** | `evaluation/EVALUATION-PRODUCTION-EXCLUSION-CONTRACT.md` |
| 1.2 | Lease path produção | **PASS** | `state/evaluation-lease.json` |
| 1.3 | Schema lease | **PASS** | `glitch.topstep.evaluation_lease.v1` |
| 1.4 | Incidente r15 documentado | **PASS** | `R15-EVALUATION-CRON-COORDINATION-INCIDENT-2026-09-02.md` |
| 1.5 | Pausa manual cron | **DOC ONLY** | workaround r15 — não procedimento permanente |

---

## 2. Implementação runtime

| # | Item | Status | Evidência |
|---|------|--------|-----------|
| 2.1 | `scripts/evaluation_lease.py` | **PASS** | acquire/renew/release/TTL |
| 2.2 | Defer `run-topstep-cycle.py` | **PASS** | antes de `acquire_model_owner` |
| 2.3 | Defer `run-topstep-learning.py` | **PASS** | idem |
| 2.4 | Defer `run-wake-trigger-monitor.py` | **PASS** | `poll_once` |
| 2.5 | Replay integrado | **PASS** | `run-scenario-live-replay.py` + `ProductionEvaluationLease` |
| 2.6 | Testes unitários | **PASS 8/8** | `tests/test_evaluation_lease.py` |

---

## 3. Deploy e integridade (2026-09-02T16:50:30Z)

| Script | SHA256 (repo = instalado) |
|--------|---------------------------|
| `evaluation_lease.py` | `dd30b35e…a7a660` |
| `preflight-evaluation-replay.py` | `8a6d0144…d74a01` |
| `run-topstep-cycle.py` | `e56b26e5…531d120` |
| `run-topstep-learning.py` | `d40ee064…4fc434a` |
| `run-wake-trigger-monitor.py` | `c0abbd94…91790c1` |
| `run-evaluation-lease-smoke-test.py` | `257edfb2…a35bc2` |

**Manifest:** `%LOCALAPPDATA%/hermes/profiles/glitch-topstep/state/lease-coordination-sync.json` · `all_matched: true`

**Sync:** `scripts/sync-evaluation-lease-scripts.ps1` · verify: `-VerifyOnly`

---

## 4. Validação live (cron ativo, sem pausa manual)

| # | Item | Status | Evidência |
|---|------|--------|-----------|
| 4.1 | Smoke lease→defer→release→resume | **PASS** | `evaluation/runs/lease-smoke-2026-09-02.json` |
| 4.2 | Defer dos 3 workers | **PASS** | direct_cycle · learning · wake_monitor |
| 4.3 | Tick cron natural durante hold | **PASS** | `cron_defer_observed_during_window: true` |
| 4.4 | Artefatos operacionais inalterados | **PASS** | snapshot pré/pós smoke |
| 4.5 | Fault: abort | **PASS** | `lease-smoke-2026-09-02-fault.json` |
| 4.6 | Fault: timeout | **PASS** | idem |
| 4.7 | Fault: crash + orphan cleanup | **PASS** | idem |
| 4.8 | Fault: recovery | **PASS** | idem |

Relatório operacional: `LEASE-COORDINATION-LIVE-VALIDATION-2026-09-02.md`

---

## 5. Preflight (coordenação)

| Check | Status | Evidência |
|-------|--------|-----------|
| `production_lane_inactive` | **PASS** | `preflight-coordination-review-2026-09-02.json` |
| `evaluation_lease_available` | **PASS** | idem |
| `lease_scripts_synced` | **PASS** | synced_utc `2026-09-02T16:50:30Z` |
| `lease_smoke_passed` | **PASS** | `lease-smoke-2026-09-02.json` |
| `coordination_contract` | **PASS** | idem |

```powershell
python scripts/preflight-evaluation-replay.py --run-id coordination-review-2026-09-02
# ok: true (2026-09-02)
```

**Nota:** preflight verde de coordenação **não** valida cenários de replay nem coorte v8.

---

## 6. Riscos residuais aceitos

| Risco | Mitigação | Severidade |
|-------|-----------|------------|
| `launch-topstep-cycle.py` não checa lease antes de spawn | filho `run-topstep-cycle` adia imediatamente | baixa (custo CPU) |
| Sync manual pós-mudança no repo | manifest + preflight `lease_scripts_synced` | operacional |
| Status supervisor stale pós-defer | smoke usa probe ativo, não JSON histórico | baixa |
| Replay cognitivo ainda não exercido com lease | exige coorte v8 + autorização separada | **gate** |

---

## 7. Registro e próxima sequência

```text
evaluation×cron: LIVE_VALIDATED          ✓ (2026-09-02)
→ nova PRAC diversa                      pendente
→ ingest + inventário + coorte v8        pendente
→ revisão técnica coorte v8              pendente
→ autorização humana replay              pendente
→ replay sequencial + QC + novo gate     pendente
```

**Proibido:** repetir v6/v7 para testar infraestrutura — smoke live já cumpriu esse objetivo.

---

## 8. Decisão

| Decisão | Valor |
|---------|-------|
| Coordenação evaluation×cron | **APPROVED** · `LIVE_VALIDATED` |
| `blocks_next_cognitive_replay` (runtime) | **removido** |
| `blocks_next_cognitive_replay` (amostra) | **mantido** — gate `2/5` |
| `next_authorized_run_id` | `null` |
| Agregador / paralelismo / shadow | **BLOCKED** |
