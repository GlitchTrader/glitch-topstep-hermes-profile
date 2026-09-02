# QC pós-replay v8 — custo, latência, hashes, isolamento

**Preenchido:** 2026-09-02 pós `scenario-live-2026-09-02-r16-v8`  
**Run:** `scenario-live-2026-09-02-r16-v8` · **6 invocações** sequenciais  
**Proveniência:** `evaluation/reviews/R16-PROVENANCE-ADDENDUM-2026-09-02.md` (addendum pré-1ª invocação)

---

## 1. Completude

| # | Check | Esperado | Resultado |
|---|-------|----------|-----------|
| 1.1 | Invocações executadas | **6/6** | **6/6** |
| 1.2 | `invalid_count` | **0** | **0** |
| 1.3 | Exit code replay | **0** | **0** (`status: completed`) |
| 1.4 | Lease liberado pós-run | cron retomou sem defer permanente | **OK** (lease + `production_evaluation_lease: true`) |

---

## 2. Custo

| Campo | Valor |
|-------|-------|
| `session_cost_usd` | **$0.06705** |
| Custo por invocação (mediana) | **~$0.011** |
| Dentro do orçamento offline (~$0.07–0.09 est.) | [x] sim [ ] não |
| Artefato | `evaluation/runs/scenario-live-2026-09-02-r16-v8-quality-report.json` |

```powershell
python scripts\audit-evaluation-cost.py --run evaluation\runs\scenario-live-2026-09-02-r16-v8.json
```

---

## 3. Latência

| Métrica | Valor |
|---------|-------|
| p50 por invocação (ms) | **11 975.5** |
| p95 por invocação (ms) | **14 094** |
| Soma sequencial (s) | **~73.4** |
| Referência r14 p50 | ~11 679 ms/inv |

---

## 4. Hashes e pinos

| # | Check | Esperado | Resultado |
|---|-------|----------|-----------|
| 4.1 | Manifest v8 inalterado | SHA manifest = pin pré-replay | **OK** |
| 4.2 | Digest v8 | `b4e9289b3a0a57b3a158f8de21fc11cadb1993e1d1d6c678faaade340e043cba` | **OK** |
| 4.3 | `envelope_hash` por frame bate digest | 3/3 | **3/3** |
| 4.4 | `snapshot_hash` por invocação rastreável ao corpus | 3/3 | **3/3** |
| 4.5 | Bundle run JSON checksum registrado | | `evaluation/runs/r16-canonical-artifacts-2026-09-02.json` |

```powershell
python scripts\audit-artifact-provenance.py --run evaluation\runs\scenario-live-2026-09-02-r16-v8.json
```

---

## 5. Isolamento

| # | Check | Esperado | Resultado |
|---|-------|----------|-----------|
| 5.1 | `production_paths_untouched` | **true** | **true** (`operational_artifacts_unchanged: true`) |
| 5.2 | Sem mutação ProjectX durante replay | | **OK** |
| 5.3 | Cron defer apenas durante lease ativo | | **OK** |
| 5.4 | `state/decisions.jsonl` produção sem overwrite por replay | | **OK** |
| 5.5 | Evaluation lease smoke ainda válido pós-run | | **OK** (LIVE_VALIDATED pré/pós) |

---

## 6. Corpus e gate

| # | Check | Resultado |
|---|-------|-----------|
| 6.1 | `corpus_validation.all_valid` no bundle | **true** (3/3) |
| 6.2 | `comparable_pair_count` (run) | **0/3** |
| 6.3 | Gate agregado pós-run | **2/5** |
| 6.4 | `insufficient_sample` | **true** |

```powershell
python scripts\report-evaluation-quality.py --run evaluation\runs\scenario-live-2026-09-02-r16-v8.json
python scripts\apply-sample-quality-gate.py --runs evaluation\runs\scenario-live-2026-09-02-r16-v8.json
```

---

## 7. Decisão QC

| Resultado | Ação |
|-----------|------|
| QC PASS + gate `<5/5` | **STOP_RERUNS v8** · nova PRAC v9 |
| QC PASS + gate `≥5/5` | revisão qualitativa · agregador offline spec apenas |
| QC FAIL | preservar artefatos · não promover · diagnosticar |

**Decisão:** **QC PASS** · gate **2/5** inalterado · **STOP_RERUNS v8** fechado · próximo: **PRAC diversa v9**.
