# Revisão de proveniência — coorte v9

**Data:** 2026-09-02  
**Sessão PRAC:** `PRAC-SOAK-2026-09-02-v9`

---

## Veredito: **PASS** (offline)

| # | Item | Status | Evidência |
|---|------|--------|-----------|
| 1 | `chain_complete` | **true** | `session-finalize.json` |
| 2 | Export `validation.valid` | **true** | `validation-report.json` |
| 3 | Ingest `frames_added` | **6** | `prac-corpus-ingest-PRAC-SOAK-2026-09-02-v9.json` |
| 4 | Archive preservado | **sim** | `evaluation/runs/prac-evidence-archive/PRAC-SOAK-2026-09-02-v9/` |
| 5 | `packet → snapshot → intent → decisão → receipt` | **PASS** | 6/6 linhas exportadas |
| 6 | `SinceUtc` = 1º ciclo espontâneo | **PASS** | `2026-09-02T18:10:06.807382Z` |
| 7 | Production paths unchanged | **sim** | pipeline offline apenas |
| 8 | `next_authorized_run_id` | **null** | registry inalterado |

### Hashes archive (ingest)

| Artefato | SHA256 |
|----------|--------|
| `evidence-chain-manifest.json` | `89755d30cf23a7c6cf89b000654ed15f690aa70b046b0d9f72232a99ea98141f` |
| `session-finalize.json` | `5d7758ade5326a0a3a60c498e763fdfb428da9c618f6a11f84379ee0d8df86cc` |

### Coorte

| Artefato | SHA256 |
|----------|--------|
| Digest v9 | `59093a3a770107f0abe0173cfcd98d4746fd908ff3429b55a15ade0e56d56674` |

Digest re-run estável (2026-09-02).
