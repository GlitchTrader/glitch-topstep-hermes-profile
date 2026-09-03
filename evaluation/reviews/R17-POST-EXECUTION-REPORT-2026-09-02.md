# Relatório pós-execução — replay coorte v9 (r17)

**Data:** 2026-09-02  
**Run:** `scenario-live-2026-09-02-r17-v9`  
**Autorização:** Ari · `executed_2026-09-02_Ari`  
**Coorte:** v9 · `READY_WITH_LIMITATIONS` · digest `59093a3a770107f0abe0173cfcd98d4746fd908ff3429b55a15ade0e56d56674`  
**Fechamento pós-replay:** 2026-09-02T18:51:03Z (sem nova invocação Hermes)

---

## Resultado executivo

| Métrica | Valor |
|---------|-------|
| Status | **COMPLETE** |
| Invocações | **8/8** (`invalid: 0`) |
| Envelopes | **4/4** |
| `comparable_pair` (r17) | **0/4** |
| Gate agregado | **2/5** · `insufficient_sample` **mantido** |
| Novos pares bilaterais | **0** |
| Custo sessão | **$0.08949** |
| Latência p50 / p95 | **11 507.5 ms** / **14 781 ms** |
| Produção intocada | **sim** (`production_paths_untouched: true`) |
| Agregador | **não executado** |

**Conclusão:** replay v9 concluído com integridade operacional; **não** fechou gap cognitivo bilateral. **STOP_RERUNS v9** fechado. Próximo passo: **PRAC v10** com maior diversidade — **não** repetir v9.

---

## Sequência de gate (pós-replay)

| Etapa | Resultado | Artefato |
|-------|-----------|----------|
| QC técnico | **PASS** | `evaluation/reviews/V9-REPLAY-QC-CHECKLIST-2026-09-02.md` |
| Proveniência | **PASS** | `evaluation/reviews/R17-PROVENANCE-REVIEW-2026-09-02.md` |
| Custo/latência | **PASS** | `evaluation/reviews/R17-COST-LATENCY-REPORT-2026-09-02.md` |
| `apply-sample-quality-gate` | **2/5** · `insufficient_sample: true` | `evaluation/runs/sample-quality-gate-result-2026-09-02-r17-v9.json` |
| `report-evaluation-quality` | agregado via gate r17 | `evaluation/runs/evaluation-quality-report-2026-09-02-r17-v9.json` |
| Análise abstinência | revisão curta (gate inalterado) | `evaluation/reviews/R17-ABSTENTION-ANALYSIS-2026-09-02.md` |

```text
next_authorized_run_id = null
STOP_RERUNS v9 = true
```

---

## Cognição (r17)

| Perfil | `no_edge` | Divergência vs par |
|--------|-----------|-------------------|
| `baseline-current` | 4/4 | 0 |
| `structure` | 4/4 | 0 |

Todos os frames: `no_edge` bilateral · `direction_delta: 0` · `thesis_delta: 0`.

---

## Artefatos canônicos

| Artefato | Path |
|----------|------|
| Índice canônico | `evaluation/runs/r17-canonical-artifacts-2026-09-02.json` |
| Bundle | `evaluation/runs/scenario-live-2026-09-02-r17-v9.json` |
| Corpus validation | `evaluation/runs/scenario-live-2026-09-02-r17-v9-corpus-validation.json` |
| Quality / checklist | `*-quality-report.json`, `*-checklist.json` |
| Cost audit | `evaluation/runs/scenario-live-2026-09-02-r17-v9-cost-audit.json` |
| Provenance audit | `evaluation/runs/r17-provenance-audit-2026-09-02.json` |
| Autorização | `evaluation/reviews/V9-TECHNICAL-REVIEW-AUTHORIZATION-CHECKLIST-2026-09-02.md` |
| QC checklist | `evaluation/reviews/V9-REPLAY-QC-CHECKLIST-2026-09-02.md` |

---

## Política pós-r17

```text
STOP_RERUNS v9
next_authorized_run_id: null
next_collection_priority: new_prac_session_v10_diversity
replay_blocked_until: nova PRAC + coorte + autorização humana
```

Próximo replay cognitivo **somente** após nova evidência PRAC ou decisão técnica formal sobre trilha diagnóstica de abstinência.
