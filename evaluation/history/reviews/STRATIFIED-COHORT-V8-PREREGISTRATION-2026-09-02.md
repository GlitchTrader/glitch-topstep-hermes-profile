# Pré-registro coorte estratificada v8 — pendente nova sessão PRAC

**Status:** `pending_prac_session`  
**Criado:** 2026-09-02 (pós-lease `LIVE_VALIDATED`)  
**Substitui:** nenhuma execução — v6/v7 **não** reutilizáveis para inflar amostra

---

## Política anti-inflação

| Coorte / run | Uso permitido |
|--------------|---------------|
| v6 | **PRESERVADA** — não replay para gate |
| v7 + r15 | **EXECUTADA** — 0 novos pares; não repetir |
| v8 | Somente frames **novos** pós-próxima PRAC diversa |
| Smoke lease | Infraestrutura — **não** conta como evidência cognitiva |

---

## Pré-condições (obrigatórias)

- [ ] Nova sessão PRAC diversa (`PRAC-NEXT-CAPTURE-PREP-2026-09-02.md`)
- [ ] Export `chain_complete: true`
- [ ] Ingest: `prac-corpus-ingest-PRAC-SOAK-<date>.json`
- [ ] Testes 6–11 → `prac_directed_execution` (**excluídos**)
- [ ] Inventário: `inventory-unused-cohort-frames.py --cohort-version v8`
- [ ] Auditoria consumo: frames **não** em v2–v7 nem replays r7–r15
- [ ] Preflight coordenação verde no momento do replay (sync + smoke recente)

---

## Política de seleção (rascunho — confirmar pós-ingest)

| Regra | Valor proposto |
|-------|----------------|
| Base | `recency_first_spontaneous` |
| Exclusões | v2–v7 · runs r7–r15 · `prac_directed_execution` · frames diversity já em v6 |
| `state_complete` | Preferir `true`; excluir `false` sem justificativa |
| Barras | `capacity_gate_pass` obrigatório |
| Diversidade | midday/afternoon · reconciliation/preflight buckets · instrumento se disponível |
| Objetivo gate | contribuir pares `thesis_quality` **independentes** (meta ≥5/5 agregado) |

---

## Campos a preencher após ingest

| Campo | Valor |
|-------|-------|
| `prac_session_id` | _TBD_ |
| `prac_ingest` | _TBD_ |
| `temporal_window.since_utc` | _TBD_ |
| `temporal_window.until_utc` | _TBD_ |
| `envelope_count` | _TBD_ |
| `digest_sha256` | _TBD_ |
| `verify_stratified_cohort` | _TBD_ (sem `--skip-validation`) |

---

## Sequência pós-ingest

```text
ingest
  → audit-prac-frame-consumption.py
  → inventory-unused-cohort-frames.py --cohort-version v8
  → build-stratified-cohort.py
  → digest-stratified-cohort.py
  → verify-stratified-cohort.py
  → STRATIFIED-COHORT-V8-SELECTION-<date>.md
  → revisão técnica + autorização humana
  → replay sequencial (run_id dedicado, não v6/v7)
  → QC + proveniência + custo + novo gate
```

---

## Comandos (executar somente pós-export)

Substituir `PRAC-SOAK-AAAA-MM-DD` e `<date>` pela sessão real.

```powershell
cd C:\Users\arifr\Projects\glitch-topstep-hermes-profile

python scripts\build-enriched-corpus.py ingest --session-id PRAC-SOAK-AAAA-MM-DD

python scripts\audit-prac-frame-consumption.py `
  --session-id PRAC-SOAK-AAAA-MM-DD `
  --output evaluation\runs\prac-frame-consumption-audit-AAAA-MM-DD.json

python scripts\inventory-unused-cohort-frames.py --cohort-version v8

python scripts\build-stratified-cohort.py --cohort-version v8 `
  --latest-origin prac_soak_<tag> `
  --output evaluation\runs\stratified-cohort-manifest-v8-AAAA-MM-DD.json

python scripts\digest-stratified-cohort.py `
  --manifest evaluation\runs\stratified-cohort-manifest-v8-AAAA-MM-DD.json `
  --output evaluation\runs\stratified-cohort-digest-v8-AAAA-MM-DD.json

python scripts\verify-stratified-cohort.py `
  --manifest evaluation\runs\stratified-cohort-manifest-v8-AAAA-MM-DD.json `
  --scenarios evaluation\stratified_scenarios.v8.json
```

Gerar seleção: `STRATIFIED-COHORT-V8-SELECTION-<date>.md` (via `--review-output` no build).

---

## Autorização

| Item | Valor |
|------|-------|
| `next_authorized_run_id` | `null` |
| Replay v8 | **BLOCKED** até checklist + assinatura humana |
| Coordenação runtime | `LIVE_VALIDATED` — não equivale a autorização de replay |
