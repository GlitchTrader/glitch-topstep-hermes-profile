# Relatório pós-execução — replay coorte v8 (r16)

**Data:** 2026-09-02  
**Run:** `scenario-live-2026-09-02-r16-v8`  
**Autorização:** Ari · `executed_2026-09-02_Ari`  
**Coorte:** v8 · `READY_WITH_LIMITATIONS` · digest `b4e9289b…`

---

## Resultado executivo

| Métrica | Valor |
|---------|-------|
| Status | **COMPLETE** |
| Invocações | **6/6** (`invalid: 0`) |
| Envelopes | **3/3** |
| `comparable_pair` (r16) | **0/3** |
| Gate agregado | **2/5** · `insufficient_sample` **mantido** |
| Custo sessão | **$0.06705** |
| Produção intocada | **sim** (lease + cron defer) |
| Agregador | **não executado** |

**Conclusão:** replay v8 concluído com integridade operacional; **não** fechou gap cognitivo. Próximo passo: **nova PRAC** com diversidade adicional — **não** repetir v8.

---

## Artefatos canônicos

| Artefato | Path |
|----------|------|
| Bundle | `evaluation/runs/scenario-live-2026-09-02-r16-v8.json` |
| Corpus validation | `evaluation/runs/scenario-live-2026-09-02-r16-v8-corpus-validation.json` |
| Preflight | `evaluation/runs/scenario-live-2026-09-02-r16-v8-preflight.json` |
| Autorização | `evaluation/reviews/V8-TECHNICAL-REVIEW-AUTHORIZATION-CHECKLIST-2026-09-02.md` |
| Proveniência | `evaluation/reviews/R16-PROVENANCE-ADDENDUM-2026-09-02.md` |
| Índice canônico | `evaluation/runs/r16-canonical-artifacts-2026-09-02.json` |
| QC checklist | `evaluation/reviews/V8-REPLAY-QC-CHECKLIST-2026-09-02.md` |

---

## Política pós-r16

```text
STOP_RERUNS v8
next_authorized_run_id: null
next_collection_priority: new_prac_session_diversity
```
