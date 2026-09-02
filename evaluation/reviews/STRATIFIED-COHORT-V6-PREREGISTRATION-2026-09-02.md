# Pré-registro coorte estratificada v6 — pendente nova sessão PRAC

**Status:** `pending_prac_session`  
**Criado:** 2026-09-02 (pós-r14 · `STOP_RERUNS`)  
**Substitui:** nenhuma — v5.1 permanece canônica executada até v6 ser construída offline

---

## Pré-condições (obrigatórias antes de preencher envelopes)

- [ ] Nova sessão PRAC concluída com export `chain_complete: true`
- [ ] Ingest: `prac-corpus-ingest-PRAC-SOAK-<date>.json`
- [ ] Testes 6–11 classificados `prac_directed_execution` — **excluídos** da fila espontânea
- [ ] Inventário: `inventory-unused-cohort-frames.py --cohort-version v6`

---

## Política de seleção (rascunho — confirmar pós-ingest)

| Regra | Valor proposto |
|-------|----------------|
| Base | `recency_first_spontaneous` (herda v5.1) |
| Exclusões | v2–v5.1 consumidos · runs r7–r14 · `prac_directed_execution` |
| `state_complete` | Preferir `true`; documentar frames `false` excluídos |
| Barras | `capacity_gate_pass` obrigatório para espontâneos |
| Diversidade | Maximizar `session_bucket` (midday/afternoon) e `instrument` quando disponível |
| Operacional | ≤1 slot `restart` se elegível |

---

## Campos a preencher após ingest

| Campo | Valor |
|-------|-------|
| `prac_session_id` | _TBD_ |
| `prac_ingest` | _TBD_ |
| `temporal_window.since_utc` | _TBD_ |
| `temporal_window.until_utc` | _TBD_ |
| `manifest_row_count` (espontâneos) | _TBD_ |
| `envelope_count` | _TBD_ |
| `spontaneous_cognitive_count` | _TBD_ |
| `digest_sha256` | _TBD_ (via `digest-stratified-cohort.py`) |
| `verify_stratified_cohort` | _TBD_ (sem `--skip-validation`) |

---

## Comandos (executar somente pós-export)

Os paths e `--cohort-version v6` nos scripts serão adicionados na mesma rodada do primeiro ingest elegível. Até lá, usar como checklist:
1. `build-enriched-corpus.py ingest --session-id PRAC-SOAK-<date>`
2. `inventory-unused-cohort-frames.py --cohort-version v6`
3. `build-stratified-cohort.py` + `digest-stratified-cohort.py` + `verify-stratified-cohort.py` (sem `--skip-validation`)

Gerar seleção: `STRATIFIED-COHORT-V6-SELECTION-<date>.md`.

---

## Autorização

| Item | Valor |
|------|-------|
| `next_authorized_run_id` | `null` até revisão técnica + checklist humano |
| Gate mínimo esperado | 5 pares `thesis_quality` bilaterais (agregado histórico + novos) |
| Promoção | `promotion_eligible: false` |

---

## Pós-sessão (ordem obrigatória)

```text
export chain_complete
  → ingest
  → coorte v6 (este pré-registro)
  → verify/digest
  → revisão técnica
  → autorização humana
  → replay sequencial
  → novo gate
```

Evidência PRAC = **PRAC-proven** — não implica armed-promoted.

---

## Artefatos esperados (pós-build)

- `evaluation/runs/stratified-cohort-manifest-v6-<date>.json`
- `evaluation/stratified_scenarios.v6.json`
- `evaluation/runs/stratified-cohort-digest-v6-<date>.json`
- `evaluation/reviews/STRATIFIED-COHORT-V6-SELECTION-<date>.md`
- `evaluation/reviews/STRATIFIED-COHORT-V6-AUTHORIZATION-REVIEW-<date>.md`
