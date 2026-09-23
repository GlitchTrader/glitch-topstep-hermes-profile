# Relatório pós-execução — replay coorte v7 (r15)

**Data:** 2026-09-02  
**Run:** `scenario-live-2026-09-02-r15-v7`  
**Autorização:** Ari · `approved_2026-09-02T16:18:00Z_Ari`  
**Coorte:** v7 · digest `1020808345f1c2c7087cfe5eeedc1b6c33e1d8d1d2cd5d8adaa94d546205778f`

---

## Resultado executivo

| Métrica | Valor |
|---------|-------|
| Status | **COMPLETE** |
| Invocações | **8/8** (`invalid: 0`) |
| Envelopes | **4/4** |
| `comparable_pair` (r15) | **0/4** |
| Gate agregado (r7→r15) | **2/5** · `insufficient_sample` **mantido** |
| Custo sessão | **$0.090658** |
| Latência p50 / p95 | **12 523 ms** / **15 594 ms** |
| Produção intocada | **sim** |
| Agregador | **não executado** |

**Conclusão:** replay v7 concluído com integridade operacional; **não** fechou gap cognitivo. Próximo passo: **nova coleta PRAC** com diversidade adicional — **não** repetir v7.

---

## Tentativas de execução (preservadas)

| # | Resultado | Causa |
|---|-----------|-------|
| 1 | `deferred` | `production_lane_active` (`direct_cycle` em lock) |
| 2 | `PermissionError` após 1ª invocação | `production_operational_artifacts_mutated` (cron ativo durante Hermes) |
| 3 | **COMPLETE 8/8** | Cron jobs pausados (`direct-operator`, `learning`, `wake-monitor`) |

Artefatos das tentativas: `scenario-live-2026-09-02-r15-v7-collect-stdout.log`, `…-retry2.log`

---

## QC (4/4 envelopes)

Todos `qc-envelope-collection.py` exit **0**:

- `r15-v7-qc-20260902T155530Z-4d39411f.json`
- `r15-v7-qc-20260902T155028Z-8c4e5912.json`
- `r15-v7-qc-20260902T154529Z-db31fa40.json`
- `r15-v7-qc-20260902T154027Z-358cec55.json`

Categorias: **no_edge** bilateral em todos os frames.

---

## Custo e latência

| Artefato | Caminho |
|----------|---------|
| Quality report | `evaluation/runs/scenario-live-2026-09-02-r15-v7-quality-report.json` |
| Cost audit | `evaluation/runs/evaluation-cost-audit-r15-v7-2026-09-02.json` |
| Diversity | `evaluation/runs/scenario-live-2026-09-02-r15-v7-diversity-metrics.json` |

`audit_gate_passed: true` · dentro do orçamento.

---

## Proveniência

| Artefato | Caminho |
|----------|---------|
| Artifact audit | `evaluation/runs/artifact-provenance-audit-r15-v7-2026-09-02.json` |
| Cohort provenance | `evaluation/runs/cohort-provenance-audit-r15-v7-2026-09-02.json` |

`historical_drift_total: 3` (r7 preservados) · sem drift novo.

---

## Gate

| Artefato | Caminho |
|----------|---------|
| Gate agregado | `evaluation/runs/sample-quality-gate-result-2026-09-02-r15-v7.json` |

```text
comparable_pairs: 2/5
insufficient_sample: true
```

**≥5/5 não atingido** — agregador offline permanece **BLOCKED**. Revisão qualitativa formal **não** iniciada (pré-condição gate não satisfeita).

---

## Artefatos canônicos r15

| Item | Caminho |
|------|---------|
| Bundle | `evaluation/runs/scenario-live-2026-09-02-r15-v7.json` |
| Checklist | `evaluation/runs/scenario-live-2026-09-02-r15-v7-checklist.json` |
| Corpus validation | `evaluation/runs/scenario-live-2026-09-02-r15-v7-corpus-validation.json` |
| Stdout | `evaluation/runs/scenario-live-2026-09-02-r15-v7-collect-stdout-retry2.log` |

---

## Ação operacional — cron jobs

**Retomados** `2026-09-02T16:28:32Z` · registro `CRON-RESUME-RECORD-2026-09-02.md`

---

## Incidente isolamento evaluation × cron

Ver `R15-EVALUATION-CRON-COORDINATION-INCIDENT-2026-09-02.md` e pendência `EVALUATION-CRON-COORDINATION-PENDING.md`. Próximo replay bloqueado até correção estrutural.

---

## Próximo passo autorizado

```text
STOP reruns v7
→ nova coleta PRAC (diversidade adicional)
→ export → ingest → auditoria → nova coorte (se ≥3 elegíveis)
```
