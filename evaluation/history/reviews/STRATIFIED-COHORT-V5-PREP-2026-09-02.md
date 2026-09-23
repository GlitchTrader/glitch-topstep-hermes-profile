# Preparação coorte v5 — seleção offline (pré-sessão)

**Data:** 2026-09-02  
**Objetivo:** +3 pares bilaterais espontâneos (gate 2/5 → 5/5)  
**Status:** planejamento — **não** executar replay até autorização explícita

## Prioridade de `scenario_tag`

| Prioridade | Tag | Motivo |
|------------|-----|--------|
| P0 | `reconciliation` | Lacuna v4; histórico r10 com par canônico |
| P0 | `preflight` | Lacuna v4; nunca na fila estratificada |
| P1 | `operator_minute_frame` | Única fonte espontânea nova (v4 teve 2) |
| P2 | `restart`, `timeout` | Evidência operacional — **não** conta cognitivo |
| P2 | `prac_directed_test` | Contrato/recovery — **não** conta cognitivo |

## Envelopes dirigidos v4 (reutilizar como operacional)

Manter na fila v5 como **proveniência/execução** (máx. 3), sem contagem cognitiva:

- restart `7278cb75` (2026-09-02)
- timeout `46ba8be0` (2026-09-02)
- prac_directed_test legado ou novo da sessão

## Meta v5 (rascunho)

| Bucket | Meta |
|--------|------|
| Espontâneos (`spontaneous_cognitive`) | ≥5 frames únicos, buscar ≥3 novos pares bilaterais |
| Dirigidos (`prac_directed_execution`) | ≤3 na fila replay |
| Tags obrigatórias novas | `reconciliation` + `preflight` |
| Instrumentos | MNQ primeiro; outros só com corpus |

## Independência

- `snapshot_hash` único por envelope selecionado.
- Não reutilizar frames de v2/v3/v4 já em runs r7–r13.
- Teste dirigido da sessão → `directed_tests_dir` = pasta da **mesma** sessão (`build-enriched-corpus.py ingest` default corrigido).

## Sequência (após próxima PRAC)

**Pré-requisito:** `. .\scripts\init-prac-session.ps1 -SessionId <id>` (dot-source no gateway); reutilizar `$env:PRAC_SESSION_ID` em todos os passos.

```text
. init-prac-session (ID único, mesmo shell)
→ validate-prac-capture-chain --example + preflight (exit 0)
→ sessão PRAC + reconciliation/preflight/restart/timeout + espontâneos
→ run-prac-session-export (-SessionId $env:PRAC_SESSION_ID, chain_complete)
→ run-prac-corpus-ingest.ps1
→ inventory/build/digest/verify v5 (sem skip)
→ STRATIFIED-COHORT-V5-AUTHORIZATION-REVIEW
→ autorização humana
→ replay sequencial
```

## Bloqueios atuais removidos nesta rodada

- [x] `validate-prac-capture-chain.py --example` → **PASS**
- [x] `run-r14-preflight.py` → **preflight_pass: true**
- [ ] Gate 2/5 — requer captura espontânea nova
- [ ] `next_authorized_run_id` — permanece `null`
