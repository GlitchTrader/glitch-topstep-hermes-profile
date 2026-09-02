# Frozen measurement — offline test suite (S2 trilha L)

**Data:** 2026-09-01  
**Escopo:** validação offline dos harnesses e scripts de medição congelada. **Sem** Hermes, **sem** mutação de componentes frozen.

## Comando único

```powershell
cd C:\Users\arifr\Projects\glitch-topstep-hermes-profile
powershell -File scripts\run-frozen-measurement-tests.ps1
```

Equivalente manual:

```powershell
cd C:\Users\arifr\Projects\glitch-topstep-hermes-profile
python -m unittest `
  tests.test_evaluation_output_adapter `
  tests.test_repeatability_offline `
  tests.test_cohort_provenance_audit `
  tests.test_apply_sample_quality_gate `
  tests.test_cohort_quality_manifest `
  tests.test_insufficient_sample_report `
  tests.test_corpus_coverage_gaps `
  tests.test_frozen_measurement_harness `
  -v
python scripts\review-aggregator-spec-fixtures.py --no-append-md
```

## Módulos cobertos

| Módulo / script | Teste |
|-----------------|-------|
| `evaluation_output_adapter` | `tests.test_evaluation_output_adapter` |
| `repeatability-offline-check` | `tests.test_repeatability_offline` |
| `audit-artifact-provenance` (cohort) | `tests.test_cohort_provenance_audit` |
| `apply-sample-quality-gate` | `tests.test_apply_sample_quality_gate` |
| `build-cohort-quality-manifest` | `tests.test_cohort_quality_manifest` |
| `report-insufficient-sample` | `tests.test_insufficient_sample_report` |
| `report-corpus-coverage-gaps` | `tests.test_corpus_coverage_gaps` |
| `review-aggregator-spec-fixtures` (12 fixtures) | CLI + `passed: true` |
| Harness J–K | `tests.test_frozen_measurement_harness` |

## Harnesses relacionados

```powershell
python scripts\run-frozen-measurement-audit.py
python scripts\run-frozen-measurement-reports.py
```

Gateway (trilha M):

```powershell
cd C:\Users\arifr\Projects\glitch-topstep
powershell -File scripts\run-prac-prep-check.ps1
```
