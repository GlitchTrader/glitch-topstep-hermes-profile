# Relatório de sessão PRAC — coorte v8

**Preencher somente após export com `chain_complete: true`.**  
**Não autoriza replay** — apenas documenta captura e suporta revisão técnica.

---

## Identificação

| Campo | Valor |
|-------|-------|
| `session_id` | `PRAC-SOAK-AAAA-MM-DD` |
| `origin` | `prac_soak_<tag>` |
| `first_spontaneous_cycle_utc` | _UTC real do primeiro ciclo espontâneo_ |
| `export_finalized_utc` | _de `session-finalize.json`_ |
| `evidence_dir` | _path gateway_ |
| `operator_frames_dir` | `%LOCALAPPDATA%\hermes\profiles\glitch-topstep\state\minute-frames` |

---

## Captura

| Campo | Valor |
|-------|-------|
| `chain_complete` | `true` / `false` |
| `manifest_row_count` | |
| `frames_captured` (minute-frames no operador) | |
| `spontaneous_chain_rows` | |
| `directed_tests_executed` | _lista test_id 6–11 se houver_ |
| `instruments_observed` | _ex.: MNQ, MES, …_ |
| `time_windows_utc` | _since / until + diversidade horária_ |
| `complete_bars_recorded` | _sim/não + notas_ |

---

## Capacidade e elegibilidade (pós-ingest)

| Campo | Valor |
|-------|-------|
| `ingest_report` | `evaluation/runs/prac-corpus-ingest-<session>.json` |
| `ingest_outcome_class` | _ver relatório ingest_ |
| `operator_frames_dir_status` | `missing` / `empty` / `found` |
| `frames_added` | |
| `exclusion_breakdown` | _JSON ou tabela_ |
| `new_eligible` | _auditoria consumo_ |
| `already_consumed` | _auditoria consumo_ |
| `spontaneous_with_full_capacity` | _≥3 para montar v8_ |

---

## Proveniência e exclusões

| Campo | Valor |
|-------|-------|
| `evidence_archive` | `evaluation/runs/prac-evidence-archive/<session>/` |
| `archive_sha256` | _manifest chain_ |
| `cohort_exclusions` | v2–v7 · `scenario-live-*` · directed tests |
| `v8_inventory_path` | |
| `v8_manifest_path` | |
| `digest_path` | |
| `verify_stratified_cohort` | _PASS/FAIL · sem `--skip-validation`_ |

---

## Custo e latência (se aplicável na sessão)

| Campo | Valor |
|-------|-------|
| `session_cost_usd` | _se medido_ |
| `median_cycle_latency_s` | |
| `gateway_health_notes` | |

---

## Decisão

| Critério | Resultado |
|----------|-----------|
| ≥3 frames espontâneos novos + capacidade completa | ☐ montar coorte v8 |
| <3 frames espontâneos elegíveis | ☐ **não inflar** · planejar nova PRAC |
| Pós-replay ≥5/5 | ☐ revisão qualitativa + agregador offline |
| Pós-replay <5/5 | ☐ STOP_RERUNS desta coorte · voltar à coleta |

**Decisão operador:** _continuar com v8 / repetir PRAC_

**Assinatura humana (`next_authorized_run_id`):** _pendente até checklist pós-revisão_

---

## Artefatos ligados

- `evaluation/reviews/STRATIFIED-COHORT-V8-PREREGISTRATION-2026-09-02.md`
- `evaluation/runs/v8-preflight-integrity-audit-2026-09-02.json` (pré-PRAC)
- Runbook: `glitch-topstep/docs/evidence/PRAC-PROGRAMMER-RUNBOOK-2026-09-02.md`
