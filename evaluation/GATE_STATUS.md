# Ensemble evaluation gate status

**Updated:** 2026-09-03 (delivery_complete coherent capture merged #212) · **PRAC-LIMITED encerrada** · coleta direcional **CONGELADA** · decisão produto **complete**
**Gate direcional v1:** **2/5** preservado · **`next_authorized_run_id: null`** · **`STOP_RERUNS` ativo**
**Veredito:** `close_directional_evaluation` · `ensemble_inviable_with_current_data` · r18 **não autorizado**
**Relatório:** `evaluation/reviews/LIMITED-2026-09-02-EXECUTIVE-DECISION-REPORT.md` (FINAL)
**Health↔frames:** `evaluation/runs/health-frame-correlation-PRAC-LIMITED-2026-09-02.json` — 8/8 `operationally_blocked`, 0 `valid_abstention`
**Viabilidade medição:** `evaluation/reviews/MEASUREMENT-VIABILITY-DECISION-2026-09-02.md` — **ensemble direcional encerrado** · fonte histórica **indisponível**
**Gate prontidão:** `evaluation_measurement_ready` · `scripts/evaluation-measurement-ready.py`

**Harness frozen measurement S2 (J–M):** `scripts/run-frozen-measurement-audit.py` · `scripts/run-frozen-measurement-reports.py` · `scripts/run-frozen-measurement-tests.ps1` · gateway `scripts/run-prac-prep-check.ps1` · suite `evaluation/FROZEN-MEASUREMENT-TEST-SUITE.md`

## Classificação

```text
contrato de saída        PASS (r8/r9: 100% válidos)
isolamento/custo         PASS (r9: $0.017939 / 14 invocações)
corpus comparável v2     PASS — 7 cenários, replay live r9
métricas/relatórios      PASS — multi-run comparison com numerator/denominator (report-evaluation-runs-comparison.py)
gate amostra/qualidade   FROZEN — SAMPLE-QUALITY-GATE-SPEC.md + sample_quality_gate.v1.json
proveniência normalização OFFLINE — cohort audit **104/104** (r12 v1 audit-only) + 3 drift r7 preservados
comparabilidade          **2/5** v1 preservado · v2 estratificado (`directional-gate-report-2026-09-02-v2.json`)
measurement_policy       **v1 APPROVED** (Ari · 2026-09-02) · coleta limitada: **EXECUTADA E ENCERRADA**
validations_2026-09-02 leakage_audit PASS · stratified_view PASS · product_decision complete
preparatory_artifacts    **CLOSED**
collection_closure_plan  `evaluation/COLLECTION-CLOSURE-PLAN.md`
quality_gate_directional gate legado 2/5 · v2: 1 par dirigido + 1 espontâneo (reconciliation)
abstention_diagnostic    `ABSTENTION-DIAGNOSTIC-SPEC.md` FROZEN · promotion_use_allowed=false
lacunas cobertura corpus STOP_RERUNS — **coleta direcional CONGELADA**
evaluation×cron          **LIVE_VALIDATED** — r17 COMPLETE · `next_authorized_run_id: null`
PRAC-LIMITED-2026-09-02  **COMPLETE** — 8 frames · 31 health samples · 0 pares · 0 valid_abstention
nova PRAC                **BLOCKED** — aguarda nova política de medição humana
replay cognitivo r18      **BLOCKED** — não autorizado
agregador executável     **BLOCKED** — produção/shadow; **offline** `aggregator_offline = implemented/tested`
parallel_evaluation_runner **implemented/tested** — `scripts/run-parallel-ensemble-evaluation.py` · `max_parallel_slots=2`
parallel_evaluation_acceptance **PASS** — offline 2026-09-02
parallel_evaluation_real       **PASS** — `trail-a-multi-envelope-2026-09-02` · 3 envelopes · 9/9 Hermes · $0.046 · isolamento OK
aggregator_offline_real        **PASS** — envelope selado end-to-end · identidade unânime por frame
trail_a_complete               **PASS** — 2026-09-02 multi-envelope
six_profile_evaluation_lane    **PASS** — registry v3 · 6 perfis `evaluation_enabled` · milestone offline 2026-09-02
shadow_only_offline            **implemented/tested** — `scripts/shadow-observe-offline.py` · 0 intents · gateway untouched
shadow_fixture_offline         **PASS** — modos `fixture_offline`/`snapshot_file` · `evaluation_offline=true` · `shadow_live=false`
coherent_delivery_complete     **implemented** — `capture_coherent_evaluation_bundle.py` · modo `delivery_complete` · PR #212 merged
shadow_live_read_only          **PENDING** — preflight `shadow-live-001-retry` not_ready (`release_package_hash_drift`, live anchor incoherent) · zero shadow cycle
stability_metrics_trail_a      **implemented** — `scripts/report-trail-a-stability.py` · bundle multi-envelope
provenance_chain_validation    **implemented/tested** — `scripts/validate-evaluation-provenance-chain.py`
phase_7_shadow_live            **PREP** — observador + preflight + pacote congelado · live **BLOCKED**
shadow_preflight               **implemented** — `scripts/shadow-preflight.py` · `delivery_complete` mode · 2026-09-03 retry not_ready
shadow_observer_live_prep      **implemented/tested** — `scripts/shadow-observe-live.py` · modos explícitos · `--authorize` só em `gateway_read_only_live`
evaluation_release_package     **frozen** — `evaluation/release/six-profile-evaluation-package-2026-09-02.json`
shadow_phase7_validation       **implemented** — `scripts/run-shadow-phase7-validation.py`
production_parallelism   **blocked**
paralelismo              **BLOCKED** (produção) · evaluation lane **2 slots**
fase ativa               **MEASUREMENT_VIABILITY_CLOSED** — direcional encerrado; diagnóstico offline permitido
phase_5_verdict          **OPTION_B** — confirmado por PRAC-LIMITED
measurement_review       **CLOSED** — `MEASUREMENT-VIABILITY-DECISION-2026-09-02.md`
measurement_ready_gate   **IMPLEMENTED** — `evaluation_measurement_ready` (evaluation lane only)
historical_opportunity   **UNAVAILABLE** — 0 espontâneo real com outcome
```
r17 v9                   **COMPLETE** — `scenario-live-2026-09-02-r17-v9` · 8/8 · 0 invalid · $0.089 · 0 novos pares
coorte v9                **EXECUTADA** — digest `59093a3a…` · r17 canônico · 8/8 `no_edge` bilateral
STOP_RERUNS v9           **FECHADO** 2026-09-02 pós-r17
r16 v8                   **COMPLETE** — `scenario-live-2026-09-02-r16-v8` · 6/6 · 0 invalid · $0.067 · 0 novos pares
coorte v8                **EXECUTADA** — digest `b4e9289b…` · r16 canônico c/ addendum proveniência
STOP_RERUNS v8           **FECHADO** 2026-09-02 pós-r16
próxima PRAC             **v10 proposta** — maior diversidade; não repetir v9
r14 v5.1                 **COMPLETE** — `scenario-live-2026-09-02-r14-v5.1` · 18/18 · 0 invalid · $0.203
coorte v5.1              **EXECUTADA** — digest `11a45e8f…` · 0 novos `comparable_pair`
collection_policy        **STOP_RERUNS** · `next_authorized_run_id: null` (r15 executado)
r15 v7                   **COMPLETE** — 8/8 · 0 invalid · $0.091 · 0 novos `comparable_pair`
fase ativa               **MEASUREMENT_STRATEGY_REVIEW** — Opção B Fase 5 · v10 prep apenas (override humano)
phase_5_verdict          **OPTION_B** — `PHASE-5-SAMPLE-ADEQUACY-REVIEW-2026-09-02.md`
measurement_review       **PENDING_HUMAN_APPROVAL** — `MEASUREMENT-STRATEGY-REVIEW-2026-09-02.md`
abstention_spec          `ABSTENTION-DIAGNOSTIC-SPEC.md` (draft)
test_suite               **627 OK** (2026-09-02) · SHA256SUMS coerente (636 entries)
evidência                source-tested · replay-proven · PRAC-proven · armed-promoted (sem promoção cruzada)
coorte v6                **PRÉ-REGISTRADA** — 2 env · replay **NÃO** recomendado p/ gate (máx 4/5) · adiada
coorte v7                **EXECUTADA** — `R15-POST-EXECUTION-REPORT-2026-09-02.md` · gate **2/5** inalterado
decisão v6               `V6-GATE-DECISION-2026-09-02.md`
relatório pós-r14        `R14-POST-EXECUTION-REPORT-2026-09-02.md`
próxima PRAC             `PRAC-NEXT-CAPTURE-PREP-2026-09-02.md` + `PRAC-NEXT-SESSION-CHECKLIST.md`
r14 (histórico)          ~~BLOCKED~~ → **executed** 2026-09-02 Ari
coorte estratificada v3    **EXECUTADA** — digest `dffba9f1…` · run `r13-stratified-v3` · 16/16 válidos
r13 stratified-v3          **COMPLETE** — `protocol_conformance:PASS` · `canonical_evidence:YES` · `promotion_eligible:NO`
r12 stratified (v1)        HISTÓRICO — `provenance_integrity:PASS` · `protocol_conformance:CONDITIONAL` · `promotion_eligible:NO`
r12 stratified-v2          **COMPLETE** — canônico; `promotion_eligible:NO` (amostra 2/5)
r13 stratified-v3          **COMPLETE** — último rerun MNQ pré-r14; corpus esgotado para gate
proveniência 2026-09-02    `PROVENANCE-AUDIT-2026-09-02.md` — **0** drift novo; 3 r7 históricos
testes offline v4          `tests/test_v4_offline_review.py` — manifest, independência, digest, skip denied
prac_corpus_ingest         **PASS** — `prac-corpus-ingest-PRAC-SOAK-2026-09-01.json` · `chain_complete:true` · +11 frames
coorte estratificada v4    **PRÉ-REGISTRADA** — digest `7b858bd3…` · 5 envelopes · verify 5/5 sem skip
reruns coorte esgotada     **STOP_RERUNS** (formal 2026-09-02)
prac_auto_export           `finalize-prac-session.py` + `run-prac-session-export.ps1` (gateway)
r14_preflight              `run-r14-preflight.py` — **preflight_pass: true** (2026-09-02); não autoriza replay
prac_session_sequence       `docs/evidence/PRAC-SESSION-SEQUENCE.md` — ID único `PRAC_SESSION_ID`
prac_session_pin            `. .\scripts\init-prac-session.ps1` (gateway, dot-source — não `-File`)
prac_corpus_ingest          `scripts/run-prac-corpus-ingest.ps1` (profile)
qualidade cognitiva      PARCIAL — baseline `no_edge` predominante; r12-v2: 8/9 baseline `no_edge`, 1 divergência categoria
diversidade observável   r7 SCN-PRAC-DIRECTED-02 (thesis_delta canônico)
aggregator_offline       **implemented/tested** — `scripts/ensemble_aggregator.py` · fixtures 12/12
parallel_evaluation_runner **implemented/tested** — evaluation lane only
agregador executável     **BLOCKED** (produção/shadow)
PRAC próxima sessão      docs/evidence/PRAC-NEXT-SESSION-CHECKLIST.md (gateway)
production_parallelism   **blocked**
paralelismo              **BLOCKED** (produção)
shadow / promoção        **BLOCKED**
```

## Trilhas offline A–G (2026-09-01)

| Trilha | Escopo | Resultado |
|--------|--------|-----------|
| **A** | Gate amostra/qualidade | `SAMPLE-QUALITY-GATE-SPEC.md` **FROZEN**; `insufficient_sample` bloqueia promoção |
| **B** | Proveniência r7 | `historical_normalization_version` em 3 artefatos com drift conhecido; sidecars `*-provenance.json` (r7/r8/r9) **sem mutar** corpos JSON do r7 |
| **C** | Agregador spec-only | `AGGREGATOR-SPEC-CHECKLIST-2026-09-01.md` — fixtures **12/12 PASS**; executor ensemble **BLOCKED** |
| **D** | Comparação multi-run | `evaluation-runs-comparison-2026-09-01.json` com rates `numerator`/`denominator` |
| **E** | Cadeia PRAC (gateway) | fixtures **7/7 PASS**; `validate-prac-capture-chain.py --example` OK; **0** sessões reais com export completo |
| **E′** | Inventário fontes r14 | `PRAC-SOURCE-INVENTORY-R14-2026-09-01.md` — bloqueador: novo soak + export |
| **E″** | `partial_evidence` | `PARTIAL-EVIDENCE-DIAGNOSIS-2026-09-01.md` — corpus estrutural (barra 1m parcial) |
| **E‴** | Divergências qualitativas | `DIVERGENCE-QUALITATIVE-R7-R13-2026-09-01.md` — diagnóstico, sem promoção |
| **F** | Registry audit | `profile-registry-audit.json` — **`valid: true`**, 0 issues |
| **G** | Orçamento operacional | `OPERATIONS-BUDGET-SPEC.md`; cost audit `evaluation-cost-audit-r7-r8-r9.json` — latência agregada r7+r8+r9 **181333 ms > 180000 ms** (informativo; por sessão OK) |
| **H** | Lacunas de cobertura corpus | `evaluation/reviews/CORPUS-COVERAGE-GAPS-2026-09-01.md` + `evaluation/runs/corpus-coverage-gaps-2026-09-01.json` — **more_collection** (1/5 pares comparáveis) |
| **I** | PRAC próxima sessão (gateway) | `docs/evidence/PRAC-NEXT-SESSION-CHECKLIST.md` — cadeia packet→snapshot→intent→decisão→receipt + smoke pré-sessão |
| **J** | Plano de amostragem + cohort manifest | `evaluation/SAMPLING-PLAN-2026-09-01.md` + `evaluation/runs/cohort-quality-manifest-2026-09-01.json` — 1 par independente / 5 mínimo |
| **K** | Relatório amostra insuficiente | `evaluation/reviews/INSUFFICIENT-SAMPLE-REPORT-2026-09-01.md` + `evaluation/runs/insufficient-sample-report-2026-09-01.json` |
| **L** | Proveniência cohort + repeatability | `cohort-provenance-audit-2026-09-01.json` (26/26) + `repeatability-offline-batch-2026-09-01.json` (PASS); 3 drift r7 preservados |
| **M** | Agregador static review (artefatos) | `AGGREGATOR-STATIC-REVIEW-RUN-ARTIFACTS-2026-09-01.md` — r7 par canônico + r9 divergências; executor **BLOCKED** |

Artefatos gerados offline (`audit-artifact-provenance.py --cohort-output`, `repeatability-offline-check.py --scan-cohort`, `report-evaluation-runs-comparison.py`, `audit-profile-registry.py`, `audit-evaluation-cost.py`, `build-cohort-quality-manifest.py`, `report-insufficient-sample.py`).

## Parallel ensemble offline (Trilha A — 2026-09-02)

| Componente | Status |
|------------|--------|
| `parallel_evaluation_runner` | **implemented/tested** — `scripts/run-parallel-ensemble-evaluation.py` · `ensemble_parallel_runner.py` |
| `parallel_evaluation_acceptance` | **PASS** — offline 2026-09-02 |
| `parallel_evaluation_real` | **PASS** — `trail-a-multi-envelope-2026-09-02` |
| `aggregator_offline_real` | **PASS** — selagem canônica por frame |
| `trail_a_complete` | **PASS** |
| `aggregator_offline` | **implemented/tested** — `scripts/ensemble_aggregator.py` · fixtures **12/12** |
| `ensemble_metrics` | **implemented** — custo/latência/divergência · `promotion_gate: false` |
| `production_parallelism` | **blocked** |
| `shadow` | **blocked** |
| `promotion` | **blocked** |

Replay offline com fixtures congelados:

```powershell
python scripts/run-parallel-ensemble-evaluation.py `
  --frames-dir tests/fixtures/frozen_corpus/minute-frames `
  --candidate-fixtures-dir tests/fixtures/ensemble_candidates `
  --output evaluation/runs/parallel-ensemble-offline-2026-09-02.json
```

| Métrica | Valor |
|---------|-------|
| Perfis | 3 (`baseline-current`, `structure`, `adversarial-risk`) |
| `max_parallel_slots` | **2** (evaluation lane only) |
| Frames | fixtures frozen corpus |
| Produção intocada | sim (`evaluation_only: true`) |
| Artefato | `evaluation/runs/parallel-ensemble-offline-2026-09-02.json` |

## Marco six-profile offline (2026-09-02)

| Componente | Status |
|------------|--------|
| Registry | `evaluation/registry.json` **v3** — 6 perfis · `evaluation_enabled: true` · `execution_authority: false` |
| Novos perfis | `smart-money`, `indicators`, `orderflow` — kits em `evaluation/profiles/*.v1.json` |
| Capability matrix | `evaluation/capability-matrix.json` **v3** — matrix audit **PASS** |
| Agregador 6p | `evaluation/fixtures/aggregator_decision_cases_six_profiles.v1.json` — **9/9** casos |
| Ensemble offline | `eval-milestone-six-profiles-2026-09-02-six-profile-ensemble.json` |
| Shadow-only offline | `eval-milestone-six-profiles-2026-09-02-shadow-offline.json` · `intents_sent: 0` |
| Estabilidade Trilha A | `eval-milestone-six-profiles-2026-09-02-stability-report.json` |
| Proveniência | `eval-milestone-six-profiles-2026-09-02-provenance-chain.json` |
| Milestone bundle | `eval-milestone-six-profiles-2026-09-02.json` — **verdict: PASS** |
| Revisão de contrato | `evaluation/reviews/SIX-PROFILE-CONTRACT-REVIEW-2026-09-02.md` |
| Shadow live / gateway | **BLOCKED** — sem `start.ps1` · sem intents · gate cognitivo **2/5** inalterado |

Garantias verificadas offline:

```text
ordem dos perfis não altera o resultado
perfil ausente não gera decisão falsa
no_edge não vira candidato
```

Runner:

```powershell
python scripts/run-evaluation-milestone.py --run-id eval-milestone-six-profiles-2026-09-02
python -m unittest tests.test_expanded_evaluation_milestone -v
```

Gate `evaluation_enabled` nos novos perfis: capability matrix válida · schema válido · output normalizado · evidência ausente classificada · testes verdes · zero writes operacionais.

## Fase 7 — shadow live (preparação 2026-09-02)

| Componente | Status |
|------------|--------|
| Pacote congelado | `evaluation/release/six-profile-evaluation-package-2026-09-02.json` |
| Preflight | `scripts/shadow-preflight.py` — **não** inicia gateway/Hermes |
| Observador offline 6p | `shadow-observe-offline.py` · `shadow-observe-live.py --offline-prep` |
| Métricas shadow | `scripts/report-shadow-metrics.py` |
| Isolamento | `scripts/audit-shadow-isolation.py` |
| Validação | `scripts/run-shadow-phase7-validation.py` |
| Runbook | `evaluation/SHADOW-LIVE-RUNBOOK.md` |
| Revisão técnica | `evaluation/reviews/PHASE-7-TECHNICAL-REVIEW-2026-09-02.md` |
| Coherent capture `delivery_complete` | **merged** (#212) — ancora em cycle-empirical + minute-frame congelado |
| Shadow live execução | **BLOCKED** — preflight not_ready 2026-09-03 · requer PASS + `--authorize` |
| Gate cognitivo 2/5 | **inalterado** — promoção/roteamento bloqueados |

```powershell
python scripts/run-shadow-phase7-validation.py --run-id shadow-phase7-validation-2026-09-02
python -m unittest tests.test_shadow_phase7 -v
```

## r17 — coorte v9 (`scenario-live-2026-09-02-r17-v9`)

| Métrica | Valor |
|---------|-------|
| Envelopes processados | **4/4** (manifest v9; `operator_minute_frame`) |
| Invocações | **8/8** válidas (`invalid` **0**) |
| Corpus validation | **4/4** (`all_valid`; sem `--skip-validation`) |
| `comparable_pair` (r17) | **0/4** |
| Pares agregados (r7…r17) | **2/5** |
| `session_cost_usd` | **$0.08949** |
| Latência p50 / p95 | **11 507.5 ms** / **14 781 ms** |
| Produção intocada | sim |
| `no_edge` bilateral | **8/8** (4/4 frames alinhados) |
| Classificação pós-fechamento | QC **PASS** · proveniência **PASS** · custo **PASS** |

### Artefatos r17

| Artefato | Caminho |
|----------|---------|
| Índice canônico | `evaluation/runs/r17-canonical-artifacts-2026-09-02.json` |
| Bundle | `evaluation/runs/scenario-live-2026-09-02-r17-v9.json` |
| Gate agregado pós-r17 | `evaluation/runs/sample-quality-gate-result-2026-09-02-r17-v9.json` |
| Cost audit | `evaluation/runs/scenario-live-2026-09-02-r17-v9-cost-audit.json` |
| Provenance | `evaluation/runs/r17-provenance-audit-2026-09-02.json` |
| Cohort post-r17 | `evaluation/runs/cohort-provenance-audit-2026-09-02-post-r17-v9.json` |
| QC / pós-exec / abstinência | `evaluation/reviews/V9-REPLAY-QC-CHECKLIST-2026-09-02.md`, `R17-POST-EXECUTION-REPORT-2026-09-02.md`, `R17-ABSTENTION-ANALYSIS-2026-09-02.md` |

## r9 — corpus v2 live (`scenario-live-2026-09-01-r9-v2`)

| Métrica | Valor |
|---------|-------|
| Invocações | **14/14** |
| `invalid` | **0** |
| `valid_output_rate` | **100%** |
| `no_edge_rate` | **85.7%** (12/14) |
| `comparable_pair` | **0/7** |
| `session_cost_usd` | **$0.017939** |
| Produção intocada | sim |

### Divergências cognitivas (não falhas)

| Cenário | baseline | structure | Leitura |
|---------|----------|-----------|---------|
| SCN-PRAC-DIRECTED-02 | no_edge | held | categoria divergente |
| SCN-PRAC-RECONCILIATION | no_edge | held | categoria divergente |
| Demais 5 | no_edge | no_edge | alinhamento abstinência |

**Nota:** `comparable_pair` exige ambos `thesis_quality` (candidate/held comparáveis). Baseline em `no_edge` impede par bilateral — limitação de evidência/categoria, não falha de perfil.

### Evidência histórica preservada

- **r7** — diversidade canônica (`comparable_pair` 1/3, `thesis_delta: true`)
- **r8** — correção contratual (6/6 válidos, v1)
- **r9** — amostra v2 expandida (14/14 válidos)

## r11 — fila frozen sequencial (`scenario-live-2026-09-01-r11-v2`)

| Métrica | Valor |
|---------|-------|
| Envelopes processados | **6/6** (fila frozen; exclui SCN-PRAC-DIRECTED-02) |
| Invocações | **12/12** válidas |
| `invalid` | **0** |
| `comparable_pair` (r11) | **0/6** |
| Pares agregados (r7+r10 canônicos) | **2/5** |
| `session_cost_usd` | **$0.135218** |
| Latência soma | **156387 ms** (p50 **13672 ms**) |
| Produção intocada | sim |
| OAuth | `gpt-5.6-luna` / `openai-codex` |

**Divergência observada (não falha):** SCN-PRAC-RECONCILIATION — baseline `no_edge`, structure `held` (r10 tinha bilateral `thesis_quality` no mesmo frame).

## r12 — coorte estratificada (`scenario-live-2026-09-01-r12-stratified`)

| Métrica | Valor |
|---------|-------|
| Envelopes processados | **9/9** (frames novos; exclui fila frozen r10/r11) |
| Invocações | **18/18** válidas (`invalid` **0**) |
| `comparable_pair` (r12) | **0/9** |
| Pares agregados (r7+r10+r11+r12) | **2/5** |
| `session_cost_usd` | **$0.202542** (`estimated_tokens` / `gpt-5.6-luna`) |
| Latência p50 / p95 | **9844 ms** / **12468 ms** |
| Produção intocada | sim |
| OAuth | `gpt-5.6-luna` / `openai-codex` |
| QC pós-envelope | **9/9** exit 0 |

**Pré-voo:** `verify-stratified-cohort.py` exit 0; `verify-frozen-cohort.py` exit 0. Corpus validation **7/9** (2 `operator_minute_frame` falham capacity-gate offline) — coleta com `--skip-validation`.

### Amostra comparável (r12)

| Categoria | Frames | Leitura |
|-----------|--------|---------|
| `not_comparable` (data_quality_insufficient) | 2 prac_directed_test | gate OK; qualidade de dados insuficiente |
| `no_edge` bilateral | 5 (prac/restart/reconciliation) | abstinência alinhada — sem `thesis_quality` |
| `missing_required_evidence` | 2 operator_minute_frame | capacity-gate inconsistente (quote/session) |

### Proveniência e custo (r12)

| Artefato | Caminho |
|----------|---------|
| Bundle | `evaluation/runs/scenario-live-2026-09-01-r12-stratified.json` |
| Quality / diversity | `*-quality-report.json`, `*-diversity-metrics.json` |
| Gate agregado r7+r10+r11+r12 | `evaluation/runs/sample-quality-gate-result-2026-09-01-r12.json` |
| Cohort provenance | `evaluation/runs/cohort-provenance-audit-2026-09-01-r12.json` (**70** invocações) |
| Frozen measurement audit | `evaluation/runs/frozen-measurement-audit-2026-09-01-r12.json` |
| Coleta stdout | `evaluation/runs/scenario-live-2026-09-01-r12-stratified-collect-stdout.log` |

## r12-v2 — coorte estratificada canônica (`scenario-live-2026-09-01-r12-stratified-v2`)

| Métrica | Valor |
|---------|-------|
| Envelopes processados | **9/9** (manifest v2; frames `a49c317a`/`c776a976`) |
| Invocações | **18/18** válidas (`invalid` **0**) |
| Corpus validation | **9/9** (`all_valid`; sem `--skip-validation`) |
| `comparable_pair` (r12-v2) | **0/9** |
| Pares agregados (r7+r10+r11+r12-v2) | **2/5** |
| `session_cost_usd` | **$0.203388** (`estimated_tokens` / `gpt-5.6-luna`) |
| Produção intocada | sim |
| OAuth | `gpt-5.6-luna` / `openai-codex` |
| Classificação protocolo | `protocol_conformance:PASS` · `canonical_evidence:YES` |

**Pré-voo:** `verify-stratified-cohort.py` exit 0; `verify-frozen-cohort.py` exit 0; digest v2 `f8c212f606934224e6d06ae212e9544ecf2a1d0a5c1e5724fd2fffab7be1ba7a` confirmado.

### Amostra comparável (r12-v2)

| Categoria | Frames | Leitura |
|-----------|--------|---------|
| `not_comparable` (data_quality_insufficient/expired) | 3 prac/restart | gate OK; qualidade de dados ou estado expirado |
| `no_edge` bilateral | 5 (prac/restart/reconciliation/operator) | abstinência alinhada — sem `thesis_quality` bilateral |
| divergência categoria | 1 operator (`a49c317a`) | baseline `no_edge`, structure `thesis_quality` — sem par |

### Proveniência e custo (r12-v2)

| Artefato | Caminho |
|----------|---------|
| Bundle | `evaluation/runs/scenario-live-2026-09-01-r12-stratified-v2.json` |
| Quality / diversity | `*-quality-report.json`, `*-diversity-metrics.json` |
| Gate agregado r7+r10+r11+r12-v2 | `evaluation/runs/sample-quality-gate-result-2026-09-01-r12-v2.json` |
| Cohort provenance | `evaluation/runs/cohort-provenance-audit-2026-09-01-r12-v2.json` (**88** invocações) |
| Frozen measurement audit | `evaluation/runs/frozen-measurement-audit-2026-09-01-r12-v2.json` |
| Classificação protocolo | `evaluation/runs/r12-stratified-v2-protocol-classification-2026-09-01.json` |
| Registry execução | `evaluation/runs/stratified-cohort-execution-registry.json` |
| Coleta stdout | `evaluation/runs/scenario-live-2026-09-01-r12-stratified-v2-collect-stdout.log` |

## Artefatos r9

- `evaluation/runs/scenario-live-2026-09-01-r9-v2.json`
- `evaluation/runs/scenario-live-2026-09-01-r9-v2-diversity-metrics.json`
- `evaluation/runs/scenario-live-2026-09-01-r9-v2-quality-report.json`
- `evaluation/runs/scenario-live-2026-09-01-r9-v2-checklist.json`
- `evaluation/runs/evaluation-runs-comparison-2026-09-01.json` (r7+r8+r9 offline, rates com denominator)
- `evaluation/runs/cohort-provenance-audit-2026-09-01.json`
- `evaluation/runs/repeatability-offline-batch-2026-09-01.json`
- `evaluation/reviews/REPEATABILITY-OFFLINE-BATCH-2026-09-01.md`
- `evaluation/reviews/AGGREGATOR-STATIC-REVIEW-RUN-ARTIFACTS-2026-09-01.md`
- `evaluation/runs/scenario-live-2026-09-01-r7-contract-provenance.json` (+ r8, r9 sidecars)

## Comandos

```powershell
python scripts/run-scenario-live-replay.py --run-id scenario-live-2026-09-01-r9-v2 --scenarios evaluation/comparable_scenarios.v2.json
python scripts/report-evaluation-runs-comparison.py
python scripts/audit-artifact-provenance.py --cohort-output evaluation/runs/cohort-provenance-audit-2026-09-01.json
python scripts/repeatability-offline-check.py --scan-cohort --output evaluation/runs/repeatability-offline-batch-2026-09-01.json
python scripts/audit-artifact-provenance.py --write-sidecars
python scripts/validate_comparable_corpus.py --scenarios evaluation/comparable_scenarios.v2.json
python -m unittest tests.test_cohort_provenance_audit tests.test_repeatability_offline -v
```

## Decisão cognitiva (2026-09-01)

Revisão humana offline: `evaluation/reviews/COGNITIVE-QUALITY-REVIEW-2026-09-01.md`

| Artefato | Conteúdo |
|----------|----------|
| Gate aplicado | `evaluation/runs/sample-quality-gate-result-2026-09-01-r12-v2.json` |
| Proveniência decisão | `evaluation/runs/provenance-decision-audit-2026-09-01.json` |
| Script gate | `scripts/apply-sample-quality-gate.py` |

**Decisão:** `amostra ainda insuficiente → enriquecer corpus`

- Agregado r7+r10+r11+r12-v2: `comparable_pairs` **2/5** (`insufficient_sample` mantido)
- r12-v2: **18/18** válidos, **0/9** `comparable_pair` (sem novo par thesis_quality)
- r7: 3 artefatos `historical_normalization_version` preservados (sem mutação de corpo)
- Conclusões de promoção/superioridade cognitiva **bloqueadas** pelo gate frozen

```powershell
python scripts/apply-sample-quality-gate.py
python scripts/build-cohort-quality-manifest.py
python scripts/report-insufficient-sample.py
python scripts/audit-artifact-provenance.py --decision-output evaluation/runs/provenance-decision-audit-2026-09-01.json
python -m unittest tests.test_apply_sample_quality_gate tests.test_cohort_quality_manifest tests.test_insufficient_sample_report -v
```

### Medição congelada (S1–S7)

| Passo | Artefato / script | Status |
|-------|-------------------|--------|
| **S1** Cohort freeze | `evaluation/FROZEN-COHORT-2026-09-01.md` + `evaluation/runs/frozen-cohort-manifest-2026-09-01.json` | **FROZEN** — hashes + versões pinadas; r7/r8/r9 histórico excluído |
| **S1** Verificação | `scripts/verify-frozen-cohort.py` | offline — falha se hashes driftarem |
| **S2** Runbook sequencial | `evaluation/FROZEN-COLLECTION-RUNBOOK.md` | `1 envelope → baseline → structure → QC → next` |
| **S3** QC pós-envelope | `scripts/qc-envelope-collection.py` | exit ≠ 0 → **PAUSE** coleta |
| **S3** Replay guard | `run-scenario-live-replay.py --frozen-manifest` | verifica hashes antes de iniciar |
| **S4–S7** | coleta live + re-gate | **r12-v2 COMPLETE** — 9/9 envelopes v2; protocolo PASS; 0 novos `comparable_pair` |
| **S4** r12 v1 | `r12-protocol-classification-2026-09-01.json` | **CONDITIONAL** — histórico não canônico |
| **S4** v1↔v2 audit | `STRATIFIED-COHORT-V1-V2-AUDIT-2026-09-01.md` | **rerun_required_v2** (operator frames diferem) — **resolvido** por r12-v2 |
| **S4** r12-v2 | `scenario-live-2026-09-01-r12-stratified-v2` | **COMPLETE** — corpus validation 9/9; `protocol_conformance:PASS` |
| **S4** v3 coorte | `stratified-cohort-manifest-v3-2026-09-01.json` | **EXECUTADA** — r13 8/8 validados; 0 novos pares |
| **S4** r13-v3 | `scenario-live-2026-09-01-r13-stratified-v3` | **COMPLETE** — protocolo PASS; corpus 8/8 |

**Fila de coleta (sem bilateral histórico):** `SCN-OPERATOR-MIDSESSION`, `SCN-OPERATOR-AFTERNOON`, `SCN-PRAC-TIMEOUT-RECOVERY`, `SCN-PRAC-RESTART-BRACKET`, `SCN-PRAC-RECONCILIATION`, `SCN-PRAC-PREFLIGHT` (reserva).

```powershell
python scripts/verify-frozen-cohort.py
python scripts/qc-envelope-collection.py --run-id scenario-live-2026-09-01-r9-v2 --frame-id 20260901T134026Z-bb50bbe9
python -m unittest tests.test_verify_frozen_cohort tests.test_qc_envelope_collection -v
```

### Amostragem e cohort (trilha J–K)

| Artefato | Caminho |
|----------|---------|
| Plano de amostragem | `evaluation/SAMPLING-PLAN-2026-09-01.md` |
| Schema cohort manifest | `evaluation/schemas/cohort_quality_manifest.v1.json` |
| Cohort manifest | `evaluation/runs/cohort-quality-manifest-2026-09-01.json` |
| Relatório insuficiência (JSON) | `evaluation/runs/insufficient-sample-report-2026-09-01.json` |
| Relatório insuficiência (MD) | `evaluation/reviews/INSUFFICIENT-SAMPLE-REPORT-2026-09-01.md` |
