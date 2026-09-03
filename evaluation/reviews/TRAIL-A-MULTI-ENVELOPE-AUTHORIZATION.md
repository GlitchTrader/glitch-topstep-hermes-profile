# Trilha A — autorização execução multi-envelope Hermes real

**Data:** 2026-09-02  
**Run ID:** `trail-a-multi-envelope-2026-09-02`  
**Status:** **AUTHORIZED** (evaluation lane only)

## Escopo autorizado

| Item | Valor |
|------|-------|
| Envelopes | **3** congelados (SCN-TRAIL-A-MULTI-01 … 03) |
| Perfis | `baseline-current`, `structure`, `adversarial-risk` |
| Paralelismo | `max_parallel_slots=2` |
| Invocações Hermes | até **9** (3×3) |
| Custo máximo | **$2.50** / sessão |
| Identidade | `ensemble_envelope_seal.py` — selagem por frame |

## Pré-requisitos satisfeitos

- [x] Fix identidade envelope implementado e testado (588 regressões)
- [x] Agregador pós-hoc run single-envelope PASS (`no_selection`)
- [x] Aceitação offline Trilha A PASS
- [x] Gateway `npm run check` 552/552
- [x] `next_authorized_run_id=null` (gate direcional — não bloqueia evaluation lane)

## Bloqueios mantidos

```text
PRAC · shadow live · paper · canary · promoção · gateway operacional
start.ps1 · pausa de cron · roteamento dinâmico · retry automático
```

## Comando autorizado

```powershell
python scripts\run-trail-a-parallel-live-evaluation.py `
  --run-id trail-a-multi-envelope-2026-09-02 `
  --authorize `
  --config evaluation\trail-a-multi-envelope-run-config.v1.json `
  --scenarios evaluation\trail-a-multi-envelope-scenarios.v1.json `
  --output evaluation\runs\trail-a-multi-envelope-2026-09-02.json
```

## Critério Trilha A PASS

Por envelope:

- mesmo `snapshot_hash` e `envelope_hash` em todos os perfis
- 3 perfis `completed`
- agregador `selected` ou `no_selection` (não `classified_failure` por identidade)
- zero writes operacionais · lease liberado

Global:

```text
parallel_evaluation_real = PASS
aggregator_offline_real = PASS
parallel_evaluation_acceptance = PASS
```

## Pós-PASS

Preparar transição **Fase 7 shadow-only** (observacional — sem intent, sem ordem, sem shadow live automático).
