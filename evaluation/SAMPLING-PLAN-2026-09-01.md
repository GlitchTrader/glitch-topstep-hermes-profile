# Plano de amostragem — 2026-09-01

**Status:** `approved_offline`  
**Gate referência:** `evaluation/SAMPLE-QUALITY-GATE-SPEC.md`  
**Corpus ativo:** `evaluation/comparable_scenarios.v2.json` (7 frames, 6 tags)  
**Populações:** `r7-contract`, `r8-contract`, `r9-v2` — **nunca misturar** como uma única população

## Objetivo

Atingir **≥ 5 pares comparáveis independentes** (`comparable_pair: true`, ambos perfis em `thesis_quality`) para desbloquear o gate de processo frozen. Este limiar habilita análise agregada estruturada; **não** constitui prova estatística de superioridade cognitiva.

## Lacuna atual (2026-09-01)

| Run | comparable_pair | notas |
|-----|-----------------|-------|
| r7-contract | **1/3** | único par canônico bilateral (`SCN-PRAC-DIRECTED-02`, `thesis_delta`) |
| r8-contract | **0/3** | contrato válido; sem par bilateral |
| r9-v2 | **0/7** | corpus v2 completo; baseline `no_edge` sistemático impede pares |

**Agregado cross-run:** 1/5 — **insuficiente**.  
**Estimativa independente:** 1 frame distinto (`snapshot_hash` único com par bilateral).

## Regra de independência

> **5 pares do mesmo contexto ≠ 5 evidências independentes.**

Um par comparável conta como **independente** somente quando **todos** os critérios abaixo se aplicam:

1. `comparable_pair: true` (baseline e challenger em `thesis_quality`)
2. `snapshot_hash` distinto dos demais pares já contados
3. `scenario_tag` distinto **ou** `session`/`origin` distinto (ex.: `prac_soak_2026-08-31` vs `operator_minute_frames`)
4. Preferencialmente `regime` distinto quando disponível
5. Preferencialmente `instrument` distinto quando o corpus permitir (hoje: apenas MNQ)

Repetir o mesmo frame em r7, r8 e r9 produz **no máximo 1** evidência independente (mesmo `snapshot_hash`).

## Critérios de inclusão por invocação

| Condição | Ação |
|----------|------|
| Saída normalizada válida (`state` ∈ contrato) | elegível para cohort |
| `completeness_used` sem `partial` em campos obrigatórios | `evidence_quality: complete` |
| Ambos perfis presentes no frame | necessário para par |
| `capacity_gate.comparable: true` para ambos | necessário para par |
| Categoria bilateral `thesis_quality` + `thesis_quality` | conta como par comparável |
| `no_edge` em um perfil + `thesis_quality` no outro | divergência cognitiva; **não** conta como par |
| `historical_normalization_version` (r7 drift) | inventariado; corpo JSON **não mutado** |

## Distribuição alvo (5 pares independentes)

Distribuir pares entre dimensões distintas quando possível:

| # alvo | scenario_tag | regime alvo | session/origin | notas |
|--------|--------------|-------------|----------------|-------|
| 1 | `prac_directed_test` | CHOP | `prac_soak_2026-08-31` | **já obtido** (r7 `SCN-PRAC-DIRECTED-02`) |
| 2 | `operator_minute_frame` | TREND_DOWN ou TREND_UP | `operator_minute_frames` | r9: baseline `no_edge`; precisa frame com bilateral |
| 3 | `timeout` | TREND_UP | `prac_soak_2026-08-31` | 0 pares hoje; evidência completa no corpus |
| 4 | `restart` | TRANSITION ou CHOP | `prac_soak_2026-08-31` | 0 pares; tag sem bilateral thesis_quality |
| 5 | `reconciliation` | TREND_DOWN | `prac_soak_2026-08-31` | r9: divergência `no_edge`↔`held`; não bilateral |
| reserva | `preflight` | — | `prac_soak_2026-08-31` | 0 pares; candidato se tags acima falharem |

**Instrumento:** MNQ apenas no corpus v2 — diversificação por instrumento fica para corpus v3.

## Tags v2 sem bilateral thesis_quality (prioridade de coleta)

Tags presentes no corpus v2 replayed em r9 mas **sem** `candidate_candidate` / `comparable_pair`:

1. `operator_minute_frame` — 2 frames, 0 pares (cand/no_edge observado)
2. `timeout` — 1 frame, 0 pares (abstinência bilateral)
3. `restart` — 1 frame, 0 pares
4. `preflight` — 1 frame, 0 pares
5. `reconciliation` — 1 frame, 0 pares (divergência categórica)

Somente `prac_directed_test` produziu par bilateral (r7). Expansão futura deve priorizar frames do manifest enriquecido com `quality: complete` e tags acima, **sem** alterar prompts/skills/adapter nesta fase offline.

## Procedimento de coleta (futuro, fora deste passo offline)

1. Selecionar frame do manifest com `scenario_tag` alvo e `completeness` completo
2. Replay live dual-profile (`baseline-current` + `structure`) em run dedicado (ex. `r10-v2`)
3. Verificar `comparable_pair` no bundle antes de agregar
4. Registrar no `cohort-quality-manifest` com `run_id` explícito
5. Reaplicar `apply-sample-quality-gate.py` e `report-insufficient-sample.py`

## Artefatos deste plano

| Artefato | Caminho |
|----------|---------|
| Cohort manifest | `evaluation/runs/cohort-quality-manifest-2026-09-01.json` |
| Schema | `evaluation/schemas/cohort_quality_manifest.v1.json` |
| Relatório insuficiência | `evaluation/runs/insufficient-sample-report-2026-09-01.json` |
| Revisão humana | `evaluation/reviews/INSUFFICIENT-SAMPLE-REPORT-2026-09-01.md` |

## Comandos

```powershell
python scripts/build-cohort-quality-manifest.py
python scripts/report-insufficient-sample.py
python -m unittest tests.test_cohort_quality_manifest tests.test_insufficient_sample_report -v
```
