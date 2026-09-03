# Checklist operacional — sessão PRAC v10 (pré-registro)

**Data:** 2026-09-02  
**Status:** `PREP_ONLY` — **não iniciar sessão** até decisão humana pós `PHASE-5-SAMPLE-ADEQUACY-REVIEW`  
**Veredito fase 5:** **Opção B** (revisão de medição) — este checklist é **contingência** se humano autorizar override para coleta limitada

**Referências:** `PHASE-5-SAMPLE-ADEQUACY-REVIEW-2026-09-02.md` · `STRATIFIED-COHORT-V10-PREREGISTRATION-2026-09-02.md`

---

## Bloqueios (não negociável)

```text
next_authorized_run_id     null
repetir v9                 PROIBIDO
agregador executável       BLOCKED
paralelismo Hermes         BLOCKED
shadow / paper / canary    BLOCKED
promoção                   BLOCKED
```

**Durante a sessão — proibido alterar:** prompt, adapter, registry, regras de decisão.

---

## Critérios Opção A (se override humano)

| Critério | Meta v10 |
|----------|----------|
| Janela | **≥60 min** contínuos; **≥2 períodos** distintos (ex.: manhã + tarde UTC) |
| Instrumentos | observar naturalmente; registrar `instruments_observed` vs `instrument_decided` |
| Cenários | **≥3** `scenario_tag` distintas se ocorrerem espontaneamente |
| Barras | 1m completas · `capacity_gate_pass` |
| Espontâneos | **≥3** elegíveis pós-ingest |
| Cherry-pick | **proibido** — sem seleção por resposta dos perfis |
| Orçamento | duração máx **90 min** · custo replay estimado **≤$0.15** por coorte proposta |
| Critério de parada | se **0** pares novos pós-replay → **PARAR** cadeia PRAC→rerun |

---

## Antes de abrir a sessão

```powershell
cd C:\Users\arifr\Projects\glitch-topstep
. .\scripts\init-prac-session.ps1 -SessionId "PRAC-SOAK-2026-09-02-v10"
$env:PRAC_SESSION_ID
```

- [ ] Gateway `start.ps1` / health OK
- [ ] `GLITCH_LOCAL_TOKEN` e credenciais ProjectX PRAC
- [ ] `evaluation/PHASE-PRAC-COLLECTION-2026-09-02.md` lido
- [ ] Autorização humana explícita para **override Opção B** registrada
- [ ] `next_authorized_run_id` ainda **null** até coorte v10 + revisão

---

## Durante a captura

- [ ] Registrar `first_spontaneous_cycle_utc`
- [ ] Journal completo (`decisions.jsonl`, `receipts.jsonl`)
- [ ] Por ciclo: `instrument_decided`, lock/capture state, tag de cenário
- [ ] Não forçar entradas nem multi-instrumento

---

## Após encerrar (não pular etapas)

```text
finalize-prac-session / export (chain_complete: true)
→ run-prac-corpus-ingest.ps1
→ audit-prac-frame-consumption.py --output evaluation/runs/prac-frame-consumption-audit-PRAC-SOAK-2026-09-02-v10.json
→ inventory-unused-cohort-frames.py --cohort-version v10
→ build-stratified-cohort.py --cohort-version v10
→ verify-stratified-cohort.py (sem skip)
→ revisão técnica + autorização humana
→ replay sequencial (r18 proposto, não pré-autorizado)
```

---

## Relatório pós-sessão

Preencher: `evaluation/reviews/V10-PRAC-SESSION-REPORT-TEMPLATE-2026-09-02.md`
