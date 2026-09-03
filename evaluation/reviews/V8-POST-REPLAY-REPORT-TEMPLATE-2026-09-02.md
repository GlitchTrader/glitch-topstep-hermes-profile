# Relatório pós-execução — r16 coorte v8

**Preencher após replay autorizado.**  
**Run:** `scenario-live-2026-09-02-r16-v8`  
**Classificação coorte:** `READY_WITH_LIMITATIONS`  
**Veredito preliminar:** _infraestrutura · gate cognitivo · próxima ação_

---

## 1. Resumo executivo

| Dimensão | Resultado |
|----------|-----------|
| Replay | _COMPLETE / ABORTED_ — _6/6_ invocações |
| `invalid_count` | |
| `comparable_pair` (run) | _/3 envelopes_ |
| Gate agregado pré | **2/5** |
| Gate agregado pós | **_/5** |
| `insufficient_sample` | |
| Custo sessão | **$** |
| Isolamento | `production_paths_untouched:` |
| Agregador | **não usado** (correto) |

**Leitura:** _uma frase sobre se a medição fechou o gate mínimo ou se nova PRAC é necessária_

---

## 2. Artefatos canônicos (preservar)

| Artefato | Path |
|----------|------|
| Bundle principal | `evaluation/runs/scenario-live-2026-09-02-r16-v8.json` |
| Checklist QC | `evaluation/runs/scenario-live-2026-09-02-r16-v8-checklist.json` |
| Corpus validation | `evaluation/runs/scenario-live-2026-09-02-r16-v8-corpus-validation.json` |
| Quality report | `evaluation/runs/scenario-live-2026-09-02-r16-v8-quality-report.json` |
| Gate agregado | `evaluation/runs/sample-quality-gate-result-<date>.json` |
| Coorte v8 manifest | `evaluation/runs/stratified-cohort-manifest-v8-2026-09-02.json` |
| Digest v8 | `evaluation/runs/stratified-cohort-digest-v8-2026-09-02.json` |
| Autorização | `evaluation/reviews/V8-TECHNICAL-REVIEW-AUTHORIZATION-CHECKLIST-2026-09-02.md` |
| QC checklist | `evaluation/reviews/V8-REPLAY-QC-CHECKLIST-2026-09-02.md` |

6 artefatos por invocação: `evaluation/runs/scenario-live-2026-09-02-r16-v8-{profile}-{frame_id}.json`

---

## 3. Resultados por envelope

| # | frame_id | tag | bilateral | baseline | structure |
|---|----------|-----|-----------|----------|-----------|
| 1 | `20260902T172547Z-c62a7390` | operator_minute_frame | | | |
| 2 | `20260902T172046Z-86a52bbc` | operator_minute_frame | | | |
| 3 | `20260902T171541Z-4fdd308c` | operator_minute_frame | | | |

`no_edge_rate` run: **%** · `comparable_pair_count`: **

---

## 4. Gate cognitivo

| Métrica | Pré-r16 | Pós-r16 |
|---------|---------|---------|
| Pares canônicos agregados | 2/5 | _/5 |
| `insufficient_sample` | true | |
| Novos pares r16 | — | |

Pares históricos: r7 `SCN-PRAC-DIRECTED-02`, r10 `SCN-PRAC-RECONCILIATION`.

**Nota:** `≥5/5` é gate mínimo — não implica superioridade de perfil.

---

## 5. Limitações v8 (recordar na leitura)

- Janela PRAC ~12 min · tag/origem únicas
- Decisões MNQ/NOTHING · observação multi-instrumento ≠ decisão multi-instrumento
- Coorte **não** suporta alegação de diversidade forte

---

## 6. Política pós-r16

| Condição | Ação |
|----------|------|
| Gate `<5/5` | `STOP_RERUNS` v8 · nova PRAC com diversidade |
| Gate `≥5/5` | revisão qualitativa · agregador offline spec · **sem** promoção |
| QC FAIL | diagnosticar · preservar artefatos |

```text
next_authorized_run_id: null  # até nova autorização explícita
```
