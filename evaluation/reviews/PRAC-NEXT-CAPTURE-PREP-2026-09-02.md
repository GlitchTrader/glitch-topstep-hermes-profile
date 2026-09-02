# Preparação da próxima captura PRAC

**Data:** 2026-09-02 (pós-r15)  
**Fase ativa:** `evaluation/PHASE-PRAC-COLLECTION-2026-09-02.md`  
**Política:** `STOP_RERUNS` · replay bloqueado até **coorte v8** + autorização humana  
**Coordenação:** `evaluation×cron: LIVE_VALIDATED` (2026-09-02)  
**Captura PRAC:** **permitida** com cron jobs ativos  
**Runbook canônico:** `glitch-topstep/docs/evidence/PRAC-CAPTURE-RUNBOOK.md`  
**Checklist sessão:** `glitch-topstep/docs/evidence/PRAC-NEXT-SESSION-CHECKLIST.md`

---

## Estado atual

```text
produção              saudável
gate cognitivo        2/5
r15                   fechado
evaluation×cron       LIVE_VALIDATED
nova PRAC              permitida
replay cognitivo       bloqueado — coorte v8 + autorização humana
agregador/paralelo     bloqueados
```

---

## Contexto pós-r15

| Item | Valor |
|------|-------|
| r15 | `scenario-live-2026-09-02-r15-v7` · COMPLETE · 0 novos pares |
| Gate | **2/5** inalterado |
| Coordenação | `LIVE_VALIDATED` · `LEASE-COORDINATION-TECHNICAL-REVIEW-2026-09-02.md` |
| Repetir v6/v7 | **PROIBIDO** — smoke live já validou infra |
| Próxima coorte | **v8** — `STRATIFIED-COHORT-V8-PREREGISTRATION-2026-09-02.md` |

---

## Revisão frames diversity (paralelo)

Sessão `PRAC-SOAK-2026-09-02-diversity` — 3 espontâneos:

| frame | Classificação | Nota |
|-------|---------------|------|
| `fedf09de` | elegível | v6 |
| `8ff26413` | capacity FAIL | excluído |
| `56090490` | elegível | v6 |

Auditoria: `PRAC-DIVERSITY-FRAME-CONSUMPTION-AUDIT-2026-09-02.md` · v6 adiada para gate.

---

## Sequência obrigatória (nova sessão → eventual replay)

```text
1. Sessão PRAC diversa (cron ativo OK)
2. Export chain_complete
3. ingest (profile)
4. auditoria consumo + seleção offline
5. digest + verify (sem skip)
6. revisão técnica + autorização humana
7. replay sequencial — SOMENTE após coorte v8 aprovada + autorização humana
8. novo gate (≥5/5 mínimo)
```

---

## Objetivos de captura (diversidade)

| Prioridade | Objetivo |
|------------|----------|
| P0 | Ciclos espontâneos — **todos**, sem filtrar momentos favoráveis |
| P0 | `data_quality.state_complete: true` e barras 1m **fechadas** (`capacity_gate_pass`) |
| P1 | reconciliation + preflight (buckets com par histórico) |
| P1 | Horários diversos (midday, afternoon — não só overnight) |
| P2 | Outro instrumento se política/gateway permitir |
| — | Testes 6–11 dirigidos: evidência operacional; não promover a espontâneo |

**Amostragem temporal contínua** — não selecionar só janelas com NOTHING ou só momentos “bons”.

---

## Revisão do runbook

| Seção | Status | Nota |
|-------|--------|------|
| Pré-requisitos (gateway, HERMES_HOME) | Documentado | Executar só na sessão live |
| Abertura de sessão | OK | Não limpar `state/` |
| Durante sessão | OK | `scenario_tag` explícito para dirigidos |
| Export automático (preferido) | OK | `run-prac-session-export.ps1` |
| Export manual (legado) | OK | `export` + `validate` |
| Fixture local | OK | `minimal-complete` |

---

## Comando de finalize (validado na sessão 2026-09-01)

```powershell
cd C:\Users\arifr\Projects\glitch-topstep
powershell -File scripts\run-prac-session-export.ps1 `
  -EvidenceDir "docs\evidence\PRAC-SOAK-$((Get-Date).ToString('yyyy-MM-dd'))" `
  -SinceUtc "<ISO8601 início sessão>" `
  -Force
```

**Exit 0 obrigatório** antes de `build-enriched-corpus.py ingest`.

Alternativa manual:

```powershell
python scripts\finalize-prac-session.py `
  --state-dir "$env:LOCALAPPDATA\hermes\profiles\glitch-topstep\state" `
  --output-dir $evidence `
  --since-utc "<ISO8601>"
```

---

## Cadeia de evidência (confirmada)

```text
packet (packet_id)
  → market_snapshot_hash (no decision journal)
    → decisão (decisions.jsonl: intent_id nested ou top-level)
      → intent (gateway)
        → receipt (receipts.jsonl)
          → evidence-chain-manifest.json (join pré-computado)
            → session-finalize.json (chain_complete)
```

**Correção aplicada (gateway):** validador indexa `intent.intent_id` (formato Hermes).

---

## Checklist pós-sessão (evidência)

### Export gateway

- [ ] `run-prac-session-export.ps1` exit **0**
- [ ] `validation-report.json` → `"valid": true`
- [ ] `session-finalize.json` → `"chain_complete": true`
- [ ] `decisions.jsonl` + `receipts.jsonl` + `evidence-chain-manifest.json` presentes
- [ ] Anotar `since_utc` / `until_utc` usados no export

### Classificação

- [ ] Testes dirigidos 6–11: JSON em `docs/evidence/PRAC-SOAK-*/test-0*` com PASS
- [ ] Ciclos espontâneos: sem tag dirigida; journal com `packet_id` + `market_snapshot_hash`
- [ ] Registrar `HERMES_HOME`, gateway version, paired contract version

### Ingest profile (offline, pós-sessão)

- [ ] `python scripts/build-enriched-corpus.py ingest --session-id PRAC-SOAK-<date>`
- [ ] Verificar `prac-corpus-ingest-*.json`: `directed_tests` classificados `prac_directed_execution`
- [ ] Confirmar `frames_excluded` (duplicatas) documentado
- [ ] **Não** promover directed → spontaneous

### Coorte (se aplicável)

- [ ] `inventory-unused-cohort-frames.py --cohort-version vN`
- [ ] `build-stratified-cohort.py` + `digest` + `verify` **sem** `--skip-validation`
- [ ] Atualizar registry **sem** definir `next_authorized_run_id` sem aprovação humana

### Proibido antes do export

- [ ] Limpar `state/decisions.jsonl` ou `receipts.jsonl`
- [ ] Reset de epoch
- [ ] Troca de prompt/adapter mid-session

---

## Estado atual (referência)

| Item | Valor |
|------|-------|
| Última sessão exportada | **PRAC-SOAK-2026-09-02** |
| chain_complete | true · manifest_row_count **3** |
| Testes 6–11 | 6/6 PASS |
| Ingest | PASS (+5 frames) |
| Coorte canônica executada | **v5.1** (9 env) · r14 COMPLETE |
| Gate | **2/5** · `next_authorized_run_id: null` |
| Próxima coorte | **v8** — pré-registro pendente PRAC · `next_authorized_run_id: null` |

---

## Prioridades próxima sessão PRAC (se gate <5 pós-r14)

1. **Ciclos espontâneos** — journal sem `directed_test_id`; evitar só testes 6–11.
2. **Barras completas** — fechar 1m antes do packet; reduzir `partial_evidence` e `capacity_gate_pass: false`.
3. **reconciliation / preflight** — buckets esgotados em coortes anteriores; capturar frames novos elegíveis.
4. **Horário** — diversificar além de overnight (midday/afternoon).
5. **Instrumento** — quando política permitir, segundo símbolo para `instrument_preference`.

---

## Bloqueios para próxima sessão

| Item | Status |
|------|--------|
| r14 rerun / greedy offline | **STOP_RERUNS** |
| `next_authorized_run_id` | `null` |
| Agregador / shadow / promoção | BLOCKED |
| Hermes adicional (fora PRAC live) | **não iniciar** |
| `validate-prac-capture-chain.py --example` | PASS (2026-09-02) |
