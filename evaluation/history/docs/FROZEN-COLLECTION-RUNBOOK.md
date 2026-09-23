# Runbook de coleta frozen — 2026-09-01

**Fase:** medição congelada (S2–S3)  
**Cohort:** `evaluation/FROZEN-COHORT-2026-09-01.md`  
**Manifest:** `evaluation/runs/frozen-cohort-manifest-2026-09-01.json`

## Pré-voo (antes de qualquer envelope)

```powershell
python scripts/verify-frozen-cohort.py
```

### Gate de prontidão da medição (evaluation lane — não bloqueia trading)

Antes de **qualquer** captura cognitiva PRAC ou ingest como evidência:

```powershell
# Sessão — health do gateway apenas
python scripts/evaluation-measurement-ready.py `
  --mode preflight `
  --gateway-health ..\glitch-topstep\docs\evidence\<SESSION>\gateway-health-preflight.json `
  --output evaluation/runs/measurement-ready-preflight-<SESSION>.json

# Frame — packet + decisão + receipt (cadeia exata)
python scripts/evaluation-measurement-ready.py `
  --mode capture `
  --packet tests/fixtures/frozen_corpus/enriched/minute-frames/<frame_id>.json `
  --decision ..\glitch-topstep\docs\evidence\<SESSION>\decision-sample.json `
  --receipt ..\glitch-topstep\docs\evidence\<SESSION>\receipt-sample.json `
  --output evaluation/runs/measurement-ready-capture-<frame_id>.json
```

| Resultado | Ação |
|-----------|------|
| `ready=true` | Pode registrar captura como evidência cognitiva |
| `ready=false` | **Não** ingerir frame — `blocking_reasons` documenta o motivo |
| `daily_capture_locked` | Abortar coleta direcional (lock domina) |
| `maintenance_window` / `market_not_valid` | Não capturar em manutenção ou mercado inválido |

Schema: `evaluation/schemas/evaluation_measurement_ready.v1.json`  
Script: `scripts/evaluation-measurement-ready.py` · testes: `tests/test_evaluation_measurement_ready.py`

Se hashes ou versões divergirem → **PARAR** e não iniciar coleta.

### Auth Hermes (OAuth — padrão, igual produção)

```powershell
# Uma vez no profile de evaluation (HERMES_HOME isolado):
hermes -p glitch-topstep-evaluation auth add openai-codex --type oauth
```

- Modelo/provider: `config.yaml` (`gpt-5.6-luna` / `openai-codex`) via routing Hermes — **sem** `EVALUATION_OPENROUTER_API_KEY`.
- OAuth de `glitch-topstep` (produção) **não** cobre evaluation; autentique no profile `glitch-topstep-evaluation`.
- Legado OpenRouter: `EVALUATION_AUTH_MODE=api_key` + `evaluation/.env` (ver `evaluation/.env.EXAMPLE`).

## Loop sequencial (1 envelope por vez)

```text
1 envelope → baseline-current → structure → artifacts → QC → next
```

### Passo a passo

| # | Ação | Critério de saída |
|---|------|-------------------|
| 1 | Selecionar próximo envelope da `collection_queue` no manifest | `queue_order` ascendente; pular se já tiver par bilateral na nova run |
| 2 | Verificar frozen hashes | `verify-frozen-cohort.py` → exit 0 |
| 3 | Replay `baseline-current` | artefato JSON em `evaluation/runs/` |
| 4 | Replay `structure` (mesmo frame) | artefato JSON pareado |
| 5 | QC pós-envelope | `qc-envelope-collection.py` → exit 0 |
| 5b | Gate prontidão medição | `evaluation-measurement-ready.py --mode capture` → `ready=true` |
| 6 | Registrar resultado | anotar categoria (`thesis_quality` / `no_edge` / `missing_required_evidence`) |
| 7 | Próximo envelope | repetir até fila esgotada ou PAUSE |

### Comando de replay (exemplo)

```powershell
python scripts/run-scenario-live-replay.py `
  --run-id scenario-live-2026-09-01-r10-v2 `
  --scenarios evaluation/comparable_scenarios.v2.json `
  --frozen-manifest evaluation/runs/frozen-cohort-manifest-2026-09-01.json `
  --stop-on-invalid
```

> Replay sequencial por design: um frame, dois perfis, QC, depois avançar.

### QC pós-envelope

```powershell
python scripts/qc-envelope-collection.py `
  --run-id scenario-live-2026-09-01-r10-v2 `
  --frame-id 20260901T134026Z-bb50bbe9
```

## Checks do QC (`qc-envelope-collection.py`)

| Check | Falha → |
|-------|---------|
| Mesmo `snapshot_hash` nos dois artefatos | **PAUSE** |
| Saída válida (sem `invalid` / `schema_invalid`) | **PAUSE** |
| Sem writes operacionais (`production_paths_untouched`, `lock_released`) | **PAUSE** |
| Custo dentro do teto (`ensemble_config.budget.max_cost_usd_per_session`) | **PAUSE** |
| Classificação por perfil (`thesis_quality` / `no_edge` / `missing_required_evidence`) | informativo |
| Proveniência (`normalization_version` + `raw_profile_output` intacto) | **PAUSE** |

**Exit code ≠ 0** em invalid ou quebra de proveniência → **PAUSE collection** até revisão humana.

## Regras de independência (durante coleta)

- Não contar o mesmo `snapshot_hash` duas vezes como evidência independente.
- Preferir `scenario_tag` / session / regime distintos entre pares comparáveis.
- r7/r8/r9 são **HISTORICAL** — não misturar com a nova população de coleta.

## Após coleta (fora deste runbook)

```powershell
python scripts/build-cohort-quality-manifest.py
python scripts/apply-sample-quality-gate.py
python scripts/report-insufficient-sample.py
python scripts/run-measurement-viability-decision.py
```

### Decisão de viabilidade (pós-congelamento direcional)

```powershell
python scripts/audit-historical-opportunity-sources.py
python scripts/build-viability-decision-matrix.py
```

Artefatos: `evaluation/runs/historical-opportunity-audit-2026-09-02.json`, `evaluation/runs/viability-decision-matrix-2026-09-02.json`  
Revisão: `evaluation/reviews/MEASUREMENT-VIABILITY-DECISION-2026-09-02.md`

## Referências

| Artefato | Caminho |
|----------|---------|
| Plano de amostragem | `evaluation/SAMPLING-PLAN-2026-09-01.md` |
| Gate status | `evaluation/GATE_STATUS.md` |
| Orçamento | `evaluation/ensemble_config.json` |
