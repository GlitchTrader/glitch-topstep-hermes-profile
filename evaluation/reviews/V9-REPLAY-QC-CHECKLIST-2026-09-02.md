# QC pós-replay v9 — custo, latência, hashes, isolamento

**Preenchido:** 2026-09-02 pós `scenario-live-2026-09-02-r17-v9`  
**Run:** `scenario-live-2026-09-02-r17-v9` · **8 invocações** sequenciais (4 envelopes × 2 perfis)  
**Coorte:** v9 · digest `59093a3a770107f0abe0173cfcd98d4746fd908ff3429b55a15ade0e56d56674`

---

## 1. Completude

| # | Check | Esperado | Resultado |
|---|-------|----------|-----------|
| 1.1 | Invocações executadas | **8/8** | **8/8** |
| 1.2 | `invalid_count` | **0** | **0** |
| 1.3 | Exit code replay | **0** | **0** (`status: completed`) |
| 1.4 | Lease liberado pós-run | cron retomou sem defer permanente | **OK** (`production_evaluation_lease: true` · `operational_artifacts_unchanged: true`) |

---

## 2. Custo

| Campo | Valor |
|-------|-------|
| `session_cost_usd` | **$0.08949** |
| Custo por invocação (mediana) | **~$0.0112** |
| Dentro do orçamento offline (~$0.09–0.12 est.) | [x] sim [ ] não |
| Artefato | `evaluation/runs/scenario-live-2026-09-02-r17-v9-quality-report.json` |
| Auditoria dedicada | `evaluation/runs/scenario-live-2026-09-02-r17-v9-cost-audit.json` |

```powershell
python scripts\audit-evaluation-cost.py evaluation\runs\scenario-live-2026-09-02-r17-v9.json --output evaluation\runs\scenario-live-2026-09-02-r17-v9-cost-audit.json
```

---

## 3. Latência

| Métrica | Valor |
|---------|-------|
| p50 por invocação (ms) | **11 507.5** |
| p95 por invocação (ms) | **14 781** |
| Soma sequencial (s) | **~92.5** (92 452 ms) |
| Referência r16 p50 | ~11 976 ms/inv |

---

## 4. Hashes e pinos

| # | Check | Esperado | Resultado |
|---|-------|----------|-----------|
| 4.1 | Manifest v9 inalterado | SHA manifest = pin pré-replay | **OK** (`verify-stratified-cohort` 4/4) |
| 4.2 | Digest v9 | `59093a3a770107f0abe0173cfcd98d4746fd908ff3429b55a15ade0e56d56674` | **OK** (pin inalterado pós-replay) |
| 4.3 | `envelope_hash` por frame bate digest | 4/4 | **4/4** |
| 4.4 | `snapshot_hash` por invocação rastreável ao corpus | 4/4 | **4/4** (8/8 invocações) |
| 4.5 | Auditoria r17 dedicada | | `evaluation/runs/r17-provenance-audit-2026-09-02.json` |

```powershell
python scripts\qc-envelope-collection.py --run-id scenario-live-2026-09-02-r17-v9 --frame-id <frame_id>
python scripts\verify-stratified-cohort.py --manifest evaluation\runs\stratified-cohort-manifest-v9-2026-09-02.json --scenarios evaluation\stratified_scenarios.v9.json
```

**QC por envelope (4/4 PASS):**

| frame_id | QC `ok` |
|----------|---------|
| `20260902T183055Z-92f0a8a8` | true |
| `20260902T182055Z-08066af5` | true |
| `20260902T181051Z-ab6e5383` | true |
| `20260902T180851Z-c5f24442` | true |

---

## 5. Isolamento

| # | Check | Esperado | Resultado |
|---|-------|----------|-----------|
| 5.1 | `production_paths_untouched` | **true** | **true** |
| 5.2 | Sem mutação ProjectX durante replay | | **OK** |
| 5.3 | Cron defer apenas durante lease ativo | | **OK** |
| 5.4 | `state/decisions.jsonl` produção sem overwrite por replay | | **OK** (`operational_artifacts_unchanged: true`) |
| 5.5 | Evaluation lease smoke ainda válido pós-run | | **OK** (LIVE_VALIDATED pré/pós) |

---

## 6. Corpus e gate

| # | Check | Resultado |
|---|-------|-----------|
| 6.1 | `corpus_validation.all_valid` no bundle | **true** (4/4) |
| 6.2 | `comparable_pair_count` (run r17) | **0/4** |
| 6.3 | Gate agregado pós-run | **2/5** |
| 6.4 | Novos pares bilaterais vs histórico | **0** |
| 6.5 | `insufficient_sample` | **true** |

```powershell
python scripts\apply-sample-quality-gate.py ...r7...r17... --output evaluation\runs\sample-quality-gate-result-2026-09-02-r17-v9.json
python scripts\report-evaluation-quality.py --gate-output evaluation\runs\sample-quality-gate-result-2026-09-02-r17-v9.json --output evaluation\runs\evaluation-quality-report-2026-09-02-r17-v9.json
```

---

## 7. Decisão QC

| Resultado | Ação |
|-----------|------|
| QC PASS + gate `<5/5` | **STOP_RERUNS v9** · nova PRAC v10 |
| QC PASS + gate `≥5/5` | revisão qualitativa · agregador offline spec apenas |
| QC FAIL | preservar artefatos · não promover · diagnosticar |

**Decisão:** **QC PASS** · gate **2/5** inalterado · **0** novos `comparable_pair` · **STOP_RERUNS v9** fechado · próximo: **PRAC diversa v10** (não repetir v9).
