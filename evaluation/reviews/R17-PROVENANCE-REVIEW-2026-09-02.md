# Revisão de proveniência — r17 pós-replay

**Data:** 2026-09-02  
**Run:** `scenario-live-2026-09-02-r17-v9`  
**Coorte:** v9 · digest `59093a3a770107f0abe0173cfcd98d4746fd908ff3429b55a15ade0e56d56674`

---

## Auditorias executadas (paths explícitos)

| Auditoria | Artefato | Resultado |
|-----------|----------|-----------|
| Pin manifest/digest v9 | `verify-stratified-cohort.py` | **4/4 PASS** · `all_valid: true` |
| Snapshot/envelope por invocação | `evaluation/runs/r17-provenance-audit-2026-09-02.json` | **8/8** snapshot match · **8/8** envelope match |
| Cohort cross-run | `evaluation/runs/cohort-provenance-audit-2026-09-02-post-r17-v9.json` | **104** invocações · **0** drift novo |
| Artefatos normalização | `evaluation/runs/artifact-provenance-audit-2026-09-02-r17-v9.json` | **3** drift históricos r7 preservados |

---

## Zero drift coorte v9

| Check | Resultado |
|-------|-----------|
| `digest_sha256` pós-replay | `59093a3a…` **inalterado** |
| `digest_pin_match` (r17 audit) | **true** |
| `cohort_drift` | **false** |
| Manifest rows consumidas | 4/4 sem mutação pós-execução |

---

## Isolamento operacional

- `production_paths_untouched: true`
- `operational_artifacts_unchanged: true`
- Sem sobrescrita de auditorias anteriores (outputs sufixados `*-r17-v9` / `*-post-r17-v9`)

**Proveniência:** **PASS**
