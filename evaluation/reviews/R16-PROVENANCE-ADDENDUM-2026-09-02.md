# Addendum de proveniência — r16 (`scenario-live-2026-09-02-r16-v8`)

**Data:** 2026-09-02  
**Classificação:** **addendum pré-primeira-invocação** (não desvio durante replay)  
**Autorização base:** `V8-TECHNICAL-REVIEW-AUTHORIZATION-CHECKLIST-2026-09-02.md` · Ari 2026-09-02

---

## Veredito

O r16 **pode ser aceito como evidência canônica de medição** com este addendum registrado.

| Pergunta | Resposta |
|----------|----------|
| Código diferente do checklist assinado? | **Sim** — runner + preflight (coordenação LIVE_VALIDATED) |
| Mudança **durante** invocações do run completo? | **Não** |
| Mudança **antes** da 1ª invocação bem-sucedida? | **Sim** |
| Pinos de coorte alterados? | **Não** |

**Classificação:** `mudança antes do replay` → **addendum de proveniência** (não invalidação automática).

---

## Linha do tempo (UTC)

| UTC | Evento | Invocações? |
|-----|--------|-------------|
| ~17:34:00 | Assinatura humana replay v8 | — |
| 17:34:08 | Tentativa 1 — `ModuleNotFoundError` (import preflight) | **0** |
| 17:34:22 | Tentativa 2 — preflight `production_lane_inactive` | **0** |
| 17:34:50 | Tentativa 3 — preflight `production_lane_inactive` | **0** |
| 17:34:46–17:35:35 | Correções: importlib preflight; lane check LIVE_VALIDATED; remoção de block `production_lane_active` pré-lease no runner | — |
| 17:35:35 | `sync-evaluation-lease-scripts.ps1` + início run bem-sucedido | — |
| **17:35:49** | **1ª invocação** (`baseline-current` · `20260902T172547Z-c62a7390`) | **1** |
| 17:36:54 | Run **COMPLETE** 6/6 | 6 |

Nenhuma invocação do bundle canônico executou com código pré-correção.

---

## Pinos de coorte (inalterados — checklist assinado)

| Artefato | SHA256 / valor |
|----------|----------------|
| Digest v8 | `b4e9289b3a0a57b3a158f8de21fc11cadb1993e1d1d6c678faaade340e043cba` |
| Manifest | `evaluation/runs/stratified-cohort-manifest-v8-2026-09-02.json` |
| Scenarios | `evaluation/stratified_scenarios.v8.json` |
| Envelopes | 3 · verify 3/3 sem skip |

---

## Scripts de execução (divergência registrada)

| Script | Hash no checklist / live validation | Hash no sync r16 (`17:35:35Z`) | Hash pós-run (repo) |
|--------|-------------------------------------|--------------------------------|---------------------|
| `preflight-evaluation-replay.py` | `8a6d0144…d74a01` | **`43e54479…ada74`** | `43e54479…ada74` |
| `run-scenario-live-replay.py` | *(não pinado no checklist)* | repo direto | `d6fd6ff2…1c10b4` |

**Natureza das mudanças (operacionais, não cognitivas):**

1. Import via `importlib` do preflight com hífen no nome do arquivo.
2. Preflight: `production_lane_inactive` passa com `coordination_live_validated` (lease defere cron).
3. Runner: remove block pré-lease em `production_lane_active`; adquire lease primeiro.

**Congelados inalterados:** prompt `v17.1` · adapter/registry `2026-09-01-v1` · modelo · regras agregador (spec).

---

## Evidência de execução

| Campo | Valor |
|-------|-------|
| Preflight run | `evaluation/runs/scenario-live-2026-09-02-r16-v8-preflight.json` · `ok: true` |
| `coordination_live_validated` | `true` |
| `lease_scripts_synced` | `all_matched` @ `2026-09-02T17:35:35Z` |
| Bundle | `evaluation/runs/scenario-live-2026-09-02-r16-v8.json` |
| `invalid_count` | **0** |
| `comparable_pair` | **0/3** |
| Gate | **2/5** |

---

## Implicação para canonicidade

- r16 documenta **abstinência bilateral** (`no_edge` 6/6), não superioridade de perfil.
- A divergência de runner/preflight **não altera** envelopes, digest ou corpus pinado.
- Repetir v8 **proibido** (`STOP_RERUNS`).

**Referências:** `R16-POST-EXECUTION-REPORT-2026-09-02.md` · `R15-R16-ABSTENTION-CONSOLIDATION-2026-09-02.md`
