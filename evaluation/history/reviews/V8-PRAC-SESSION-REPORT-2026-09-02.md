# Relatório de sessão PRAC — coorte v8 (preenchido)

**Sessão:** `PRAC-SOAK-2026-09-02-v8`  
**Classificação coorte:** `READY_WITH_LIMITATIONS`  
**Não autoriza replay** — suporte à revisão técnica apenas.

---

## Identificação

| Campo | Valor |
|-------|-------|
| `session_id` | `PRAC-SOAK-2026-09-02-v8` |
| `origin` | `prac_soak_2026_09_02_v8` |
| `first_spontaneous_cycle_utc` | `2026-09-02T17:17:04.457734Z` |
| `export_finalized_utc` | `2026-09-02T17:27:17.298915Z` |
| `evidence_dir` | `glitch-topstep/docs/evidence/PRAC-SOAK-2026-09-02-v8` |
| `operator_frames_dir` | `%LOCALAPPDATA%\hermes\profiles\glitch-topstep\state\minute-frames` |

---

## Captura

| Campo | Valor |
|-------|-------|
| `chain_complete` | **true** |
| `manifest_row_count` | **3** |
| `spontaneous_chain_rows` | **3** |
| `directed_tests_executed` | nenhum na janela v8 |
| `instruments_observed` (decisão) | MNQ (3/3) |
| `instruments_observed` (packet universe) | MNQ, MES, MCL |
| `time_windows_utc` | `17:14:30` → `17:27:17` UTC (~12 min) |
| `complete_bars_recorded` | sim · `capacity_gate_pass` 3/3 |

---

## Capacidade e elegibilidade

| Campo | Valor |
|-------|-------|
| `ingest_report` | `evaluation/runs/prac-corpus-ingest-PRAC-SOAK-2026-09-02-v8.json` |
| `ingest_outcome_class` | `frames_added` |
| `operator_frames_dir_status` | `found` |
| `frames_added` | **3** |
| `new_eligible` | **3** (`novo_elegivel`) |
| `already_consumed` | **0** |
| `spontaneous_with_full_capacity` | **3** |

---

## Decisão pré-replay

| Critério | Resultado |
|----------|-----------|
| ≥3 frames espontâneos + capacidade | **PASS** — montar coorte v8 |
| Diversidade forte | **FAIL** — `READY_WITH_LIMITATIONS` |
| Próximo passo | revisão técnica → assinatura → replay |

**Assinatura / `next_authorized_run_id`:** pendente.
