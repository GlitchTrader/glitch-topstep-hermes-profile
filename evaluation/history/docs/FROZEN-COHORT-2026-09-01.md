# Cohort congelado — 2026-09-01

**Status:** `frozen_measurement_phase`  
**Manifest:** `evaluation/runs/frozen-cohort-manifest-2026-09-01.json`  
**Runbook de coleta:** `evaluation/FROZEN-COLLECTION-RUNBOOK.md`

## Versões congeladas

| Campo | Valor |
|-------|-------|
| `prompt_version` | `glitch-topstep-v17.1` |
| `adapter_version` (`contract_version`) | `2026-09-01-v1` |
| `schema_version` | `glitch.topstep.evaluation_output_contract.v1` |
| `registry_version` | `2026-09-01-v2` |
| `normalization_version` | `2026-09-01-post-candidate-flat-rule` |

**Nesta fase:** sem alterações em prompts, skills, adapter logic, registry ou aggregator executor.

## Hashes SHA256 (artefatos frozen)

| Arquivo | SHA256 |
|---------|--------|
| `evaluation/evaluation_output_contract.v1.json` | `da1ae8715edf3bfc5fc79ae8646891a72fedfeeaa7cd0944291d849246375b7c` |
| `evaluation/registry.json` | `a5088e2215ad5d33decdeeea520ab6091d1a7442fc51f882406d0963143e164d` |
| `evaluation/sample_quality_gate.v1.json` | `df1352877a8e3303100865f4f640796a2f7ec24c128f63a112f48dfb3d60547b` |
| `evaluation/SAMPLING-PLAN-2026-09-01.md` | `4456a61f67be4bd13b7ea90dd46ca3279070ce32cc802f0b82346f88fa57d01f` |
| `evaluation/comparable_scenarios.v2.json` | `187b9aaf54db35f91e648d8eb758091bdbb64b28a9619bb1886b8e0836cdbedc` |

Verificação offline:

```powershell
python scripts/verify-frozen-cohort.py
```

## Cohort histórico (excluído da nova coleta)

| Run | Papel |
|-----|-------|
| `r7-contract` | **HISTORICAL** — par canônico bilateral (`SCN-PRAC-DIRECTED-02`) |
| `r8-contract` | **HISTORICAL** — contrato válido; sem par bilateral |
| `r9-v2` | **HISTORICAL** — corpus v2 completo; 0/7 `comparable_pair` |

> **r7/r8/r9 são cohort histórico** — inventariados para auditoria e comparação offline; **excluídos** da população de nova coleta frozen.

## Regras de independência

1. **Dedupe `snapshot_hash`:** repetir o mesmo frame em múltiplos runs conta no máximo 1 evidência independente.
2. **Distribuição `scenario_tag`:** preferir tags distintas entre pares comparáveis contados.
3. **Distribuição session/origin:** `scenario_tag` distinto **ou** `session`/`origin` distinto.
4. **Regime:** preferencialmente distinto quando disponível.
5. **Instrumento:** preferencialmente distinto quando o corpus permitir (v2: apenas MNQ).
6. **Par bilateral:** `comparable_pair` exige baseline **e** structure em `thesis_quality`.

## Fila de coleta (próxima população)

Alvos do `SAMPLING-PLAN-2026-09-01.md` **sem** par bilateral `thesis_quality` histórico:

| Ordem | Cenário | Envelope | Tag | Regime |
|-------|---------|----------|-----|--------|
| 1 | `SCN-OPERATOR-MIDSESSION` | `env-8d12d081fc8885a3` | `operator_minute_frame` | TREND_DOWN |
| 2 | `SCN-OPERATOR-AFTERNOON` | `env-d6b73e4e5dacbc1b` | `operator_minute_frame` | TREND_DOWN |
| 3 | `SCN-PRAC-TIMEOUT-RECOVERY` | `env-8d68e765cc68d29e` | `timeout` | TREND_UP |
| 4 | `SCN-PRAC-RESTART-BRACKET` | `env-b4154b9b398983a4` | `restart` | TREND_UP |
| 5 | `SCN-PRAC-RECONCILIATION` | `env-1e829c3158feff4d` | `reconciliation` | TRANSITION |
| 6 | `SCN-PRAC-PREFLIGHT` | `env-8ffdc3e1a920e0c1` | `preflight` (reserva) | TREND_DOWN |

**Excluído da fila:** `SCN-PRAC-DIRECTED-02` — target #1 já obtido em r7.

## Comandos

```powershell
python scripts/verify-frozen-cohort.py
python scripts/qc-envelope-collection.py --run-id <run-id> --frame-id <frame-id>
python -m unittest tests.test_verify_frozen_cohort tests.test_qc_envelope_collection -v
```
