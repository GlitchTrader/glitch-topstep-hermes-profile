# Relatório de sessão PRAC — coorte v9 (preenchido)

**Sessão:** `PRAC-SOAK-2026-09-02-v9`  
**Classificação coorte (provisória):** elegível para montagem offline · diversidade **limitada**  
**Não autoriza replay** — ingest + auditoria apenas

---

## Identificação e janela UTC

| Campo | Valor |
|-------|-------|
| `session_id` | `PRAC-SOAK-2026-09-02-v9` |
| `origin` | `prac_soak_2026_09_02_v9` |
| `session_pin_utc` | `2026-09-02T18:03:13.130Z` |
| `first_spontaneous_cycle_utc` | `2026-09-02T18:10:06.807382Z` |
| `export_finalized_utc` | `2026-09-02T18:33:56.555384Z` |
| `capture_window_utc` | `18:10:06` → `18:32:29` UTC (~**22 min** de ciclos; ~**30 min** pin→export) |
| `evidence_dir` | `glitch-topstep/docs/evidence/PRAC-SOAK-2026-09-02-v9` |
| `operator_frames_dir` | `%LOCALAPPDATA%\hermes\profiles\glitch-topstep\state\minute-frames` |
| `prac_evidence_archive` | `evaluation/runs/prac-evidence-archive/PRAC-SOAK-2026-09-02-v9` |

### Diversidade temporal

| Campo | Valor |
|-------|-------|
| Duração contínua (pin→export) | ~30 min |
| Faixa de ciclos espontâneos | ~22 min (6 ciclos) |
| Ciclos espontâneos totais | **6** |
| Ciclos dirigidos na janela | **0** (testes 6–8 no ingest são artefatos de sessão, não na janela exportada) |
| `scenario_tag` exportado | `prac_session` (todos) |

---

## Health antes / depois

### Antes (`gateway-health-preflight.json`)

| Campo | Valor |
|-------|-------|
| `recorded_utc` | `2026-09-02T18:05:57Z` |
| `status` | **ok** |
| `state_complete` | **true** |
| flat | **sim** |
| `unprotected_open_quantity` | **0** |
| `recovery_blocking` | **false** |
| cron | **ativo** (não pausado) |

### Depois (`gateway-health-postcapture.json`)

| Campo | Valor |
|-------|-------|
| `recorded_utc` | `2026-09-02T18:33:56Z` |
| `status` | **ok** |
| `state_complete` | **true** |
| flat | **sim** |
| `unprotected_open_quantity` | **0** |
| `recovery_blocking` | **false** |
| Incidentes | nenhum — captura sem parada forçada |

---

## Export e cadeia

| Campo | Valor |
|-------|-------|
| `chain_complete` | **true** |
| `validation.valid` | **true** |
| Exit code export | **0** |
| `manifest_row_count` | **6** |
| `spontaneous_chain_rows` | **6** |
| `SinceUtc` | `2026-09-02T18:10:06.807382Z` |
| `session-finalize.json` | `docs/evidence/PRAC-SOAK-2026-09-02-v9/session-finalize.json` |

---

## Instrumentos — observado vs decidido

| Campo | Valor |
|-------|-------|
| `instruments_observed` (evidence / universe) | **MNQ, MES, MCL** (6/6 ciclos) |
| `instrument_decided` (efetivo) | **MNQ** (6/6 · `NOTHING`) |
| ≥2 instrumentos observados naturalmente | **sim** |
| Decisões forçadas | **nenhuma** |

### Por frame

| `frame_id` | observados | decidido | ação | `capacity_gate_pass` | classificação |
|------------|------------|----------|------|----------------------|---------------|
| `20260902T180851Z-c5f24442` | MNQ,MES,MCL | MNQ | NOTHING | **true** | `novo_elegivel` |
| `20260902T181051Z-ab6e5383` | MNQ,MES,MCL | MNQ | NOTHING | **true** | `novo_elegivel` |
| `20260902T181554Z-79fa9dae` | MNQ,MES,MCL | MNQ | NOTHING | **false** | `insufficient_capacity` |
| `20260902T182055Z-08066af5` | MNQ,MES,MCL | MNQ | NOTHING | **true** | `novo_elegivel` |
| `20260902T182551Z-54dde640` | MNQ,MES,MCL | MNQ | NOTHING | **false** | `insufficient_capacity` |
| `20260902T183055Z-92f0a8a8` | MNQ,MES,MCL | MNQ | NOTHING | **true** | `novo_elegivel` |

---

## Ingest e elegibilidade

| Campo | Valor |
|-------|-------|
| `ingest_report` | `evaluation/runs/prac-corpus-ingest-PRAC-SOAK-2026-09-02-v9.json` |
| `ingest_outcome_class` | `frames_added` |
| `operator_frames_dir_status` | `found` |
| `frames_added` | **6** |
| `new_eligible` (`novo_elegivel`) | **4** |
| `insufficient_capacity` | **2** |
| `already_consumed` | **0** |
| `capacity_gate_pass` (espontâneos) | **4/6** |
| Consumption audit | `evaluation/runs/prac-frame-consumption-audit-PRAC-SOAK-2026-09-02-v9.json` |

---

## Hashes, archive e proveniência

| Artefato | SHA256 |
|----------|--------|
| `evidence-chain-manifest.json` | `89755d30cf23a7c6cf89b000654ed15f690aa70b046b0d9f72232a99ea98141f` |
| `session-finalize.json` | `5d7758ade5326a0a3a60c498e763fdfb428da9c618f6a11f84379ee0d8df86cc` |
| `decisions.jsonl` | `8a81c7b496b1f531416e952942abe356d770d4f9dd3554a0bb51b84934ab73ed` |
| `receipts.jsonl` | `82dedcd220e789ca22c9ec0d4141b6733db4a7344fd3e07956e7824435f6df5c` |
| Archive | `evaluation/runs/prac-evidence-archive/PRAC-SOAK-2026-09-02-v9` |
| Proveniência cadeia | **PASS** (`validation.valid: true`) |

---

## Exclusões

| Motivo | Contagem |
|--------|----------|
| `insufficient_capacity` | **2** (excluir da coorte) |
| `already_consumed` | **0** |
| `prac_directed_execution` (ingest sidecar) | 3 testes arquivados — fora da janela exportada |
| `novo_elegivel` | **4** |

---

## Decisão pós-sessão

| Critério | Resultado |
|----------|-----------|
| `chain_complete` | **PASS** |
| Espontâneos novos elegíveis | **4 ≥ 3** |
| `capacity_gate_pass` | **4/6** |
| Diversidade instrumento (observado) | **PASS** (MNQ,MES,MCL) |
| Diversidade instrumento (decidido) | **limitada** (MNQ only · abstinência) |
| Diversidade temporal | **moderada** (~22 min · 6 ciclos) |
| Novos pares bilaterais | **desconhecido** — só após replay autorizado |

**Decisão:** **Opção A — coorte v9 montada offline** (2026-09-02).

| Artefato | Path |
|----------|------|
| Manifest | `evaluation/runs/stratified-cohort-manifest-v9-2026-09-02.json` |
| Digest | `evaluation/runs/stratified-cohort-digest-v9-2026-09-02.json` · `59093a3a…` |
| Verify | **4/4 PASS** sem skip |
| Revisão técnica | `evaluation/reviews/V9-TECHNICAL-REVIEW-AUTHORIZATION-CHECKLIST-2026-09-02.md` |

**Classificação:** `READY_WITH_LIMITATIONS`

**Próximo passo:** assinatura humana → `next_authorized_run_id` → replay r17 (não executado).

```text
next_authorized_run_id = null
replay = bloqueado
agregador / paralelismo / shadow / promoção = bloqueados
```

**Assinatura / `next_authorized_run_id`:** pendente.

---

## Pré-voos (profile)

| Check | Resultado |
|-------|-----------|
| `validate-prac-capture-chain.py --example` | **PASS** |
| `run-r14-preflight.py` | **preflight_pass: true** |

---

## Notas operacionais

- Gateway já ativo — segundo processo **não** iniciado.
- Cron mantido ativo durante toda a captura.
- State não limpo; nenhum teste dirigido forçado na janela.
- `≥3 novo_elegivel` permite coorte; **não garante** novos pares bilaterais pós-replay.
