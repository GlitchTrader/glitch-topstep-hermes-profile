# Relatório pós-execução — r14 coorte v5.1

**Data:** 2026-09-02  
**Autorização:** Ari · `executed_2026-09-02_Ari`  
**Run:** `scenario-live-2026-09-02-r14-v5.1`  
**Veredito:** infraestrutura **VALIDADA** · gate cognitivo **INALTERADO** · corpus MNQ v5.1 **ESGOTADO** para novos reruns

---

## 1. Resumo executivo

| Dimensão | Resultado |
|----------|-----------|
| Replay | **COMPLETE** — 18/18 invocações |
| `invalid_count` | **0** |
| `comparable_pair` (run) | **0/9** |
| Gate agregado | **2/5** · `insufficient_sample: true` |
| Custo sessão | **$0.203** |
| Isolamento | `production_paths_untouched: true` |
| Agregador | **não usado** (correto) |

**Leitura:** a infraestrutura mede e isola corretamente. O gargalo é **exclusivamente evidência cognitiva independente** — não robustez de implementação. Novos reruns sobre este corpus **não** são autorizados (`STOP_RERUNS`).

---

## 2. Artefatos canônicos (preservar)

| Artefato | Path |
|----------|------|
| Bundle principal | `evaluation/runs/scenario-live-2026-09-02-r14-v5.1.json` |
| Checklist QC | `evaluation/runs/scenario-live-2026-09-02-r14-v5.1-checklist.json` |
| Corpus validation | `evaluation/runs/scenario-live-2026-09-02-r14-v5.1-corpus-validation.json` |
| Quality report | `evaluation/runs/scenario-live-2026-09-02-r14-v5.1-quality-report.json` |
| Diversity metrics | `evaluation/runs/scenario-live-2026-09-02-r14-v5.1-diversity-metrics.json` |
| Gate agregado | `evaluation/runs/sample-quality-gate-result-2026-09-02.json` |
| Quality report agregado | `evaluation/runs/evaluation-quality-report-2026-09-02.json` |
| Coorte v5.1 manifest | `evaluation/runs/stratified-cohort-manifest-v5.1-2026-09-02.json` |
| Digest v5.1 | `evaluation/runs/stratified-cohort-digest-v5.1-2026-09-02.json` |
| Autorização | `evaluation/reviews/V5.1-R14-AUTHORIZATION-CHECKLIST-2026-09-02.md` |
| Manifest índice | `evaluation/runs/r14-canonical-artifacts-2026-09-02.json` |

18 artefatos por invocação: `evaluation/runs/scenario-live-2026-09-02-r14-v5.1-{profile}-{frame_id}.json`

---

## 3. Resultados por envelope

| # | frame_id | tag | bilateral | baseline | structure |
|---|----------|-----|-----------|----------|-----------|
| 1 | `…b7730ea3` | operator (09-02) | `no_edge`↔`no_edge` | no_edge | no_edge |
| 2 | `…cb1139d6` | operator (09-02) | `no_edge`↔`no_edge` | no_edge | no_edge |
| 3–6 | overnight 09-01 | operator | `no_edge`↔`no_edge` | no_edge | no_edge |
| 7 | `…e8df6b82` | operator | **unilateral** | no_edge | **candidate** short |
| 8 | `…065ef854` | operator | `no_edge`↔`no_edge` | no_edge | no_edge |
| 9 | `…c30de894` | restart (dirigido) | `no_edge`↔`no_edge` | no_edge | no_edge |

`no_edge_rate` run: **94.4%** · `comparable_pair_count`: **0**

---

## 4. Gate cognitivo

| Métrica | Pré-r14 | Pós-r14 |
|---------|---------|---------|
| Pares canônicos agregados | 2/5 | **2/5** |
| `insufficient_sample` | true | **true** |
| Novos pares r14 | — | **0** |

Pares históricos inalterados: r7 `SCN-PRAC-DIRECTED-02`, r10 `SCN-PRAC-RECONCILIATION`.

---

## 5. Política pós-r14

```text
STOP_RERUNS
next_authorized_run_id: null
next_collection_priority: new_prac_session_diversity
```

**Próxima sequência autorizada:**

```text
nova evidência PRAC
→ export chain_complete
→ ingest + seleção offline
→ revisão coorte
→ autorização humana
→ replay sequencial (se coorte válida)
→ gate cognitivo
→ (somente após 5/5) agregador offline → auditoria → shadow controlado
```

---

## 6. Bloqueios mantidos

| Item | Status |
|------|--------|
| Paralelismo Hermes | BLOCKED |
| Agregador executável | BLOCKED |
| Shadow live | BLOCKED |
| Promoção | BLOCKED |
| `promotion_use_allowed` | false |
| Spec/fixtures agregador | **congelados** |

---

## 7. Análises paralelas

- `R14-NO-EDGE-AND-E8DF6B82-ANALYSIS-2026-09-02.md`
- `METRICS-PREP-2026-09-02.md` (baseline r14)
- `PRAC-NEXT-CAPTURE-PREP-2026-09-02.md` (próxima sessão)
