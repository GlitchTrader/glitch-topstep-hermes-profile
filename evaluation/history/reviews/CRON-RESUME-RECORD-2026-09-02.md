# Registro — retomada cron jobs pós-r15

**Data:** 2026-09-02  
**Contexto:** replay `scenario-live-2026-09-02-r15-v7` **COMPLETE** (8/8) antes da retomada

---

## Cron jobs retomados

| Job ID | Nome | Comando |
|--------|------|---------|
| `fb34a7e30b8b` | `glitch-topstep-direct-operator` | `hermes --profile glitch-topstep cron resume fb34a7e30b8b` |
| `ba7bb89414c7` | `glitch-topstep-learning-supervisor` | `hermes --profile glitch-topstep cron resume ba7bb89414c7` |
| `ac5ceb3e6242` | `glitch-topstep-wake-monitor` | `hermes --profile glitch-topstep cron resume ac5ceb3e6242` |

**Retomada UTC:** `2026-09-02T16:28:32Z`  
**Retomada local (UTC-4):** `2026-09-02T12:28:32`

---

## Intervalo pausado

| Marco | UTC |
|-------|-----|
| Pausa efetiva (pré-replay bem-sucedido) | `~2026-09-02T16:23:25Z` |
| Replay r15 concluído (última invocação) | `2026-09-02T16:25:15Z` |
| Retomada operador | `2026-09-02T16:28:32Z` |

| Intervalo | Duração |
|-----------|---------|
| Pausa total (pausa → retomada) | **~5 min 7 s** |
| Janela mínima necessária (pausa → fim replay) | **~1 min 50 s** |
| Pós-replay até retomada | **~3 min 17 s** |

---

## Verificação pós-retomada (`2026-09-02T16:29:40Z`)

| Check | Resultado |
|-------|-----------|
| Cron `direct-operator` | `[active]` · Last run `12:29:33` **ok** |
| Cron `wake-monitor` | `[active]` · Last run `12:29:33` **ok** |
| Cron `learning-supervisor` | `[active]` · próximo `12:30:00` |
| Gateway `/health` `status` | **ok** |
| `data_quality.state_complete` | **true** |
| `unprotected_open_quantity` | **0** |
| `execution_recovery.blockingAmbiguity` | **false** |
| `execution_recovery.blockingNewExposure` | **false** |
| `invariant_metrics.execution_recovery_blocking` | **false** |
| `task_scheduler.running` | **1** |
| `model-owner.lock` produção | **ausente** (entre ciclos) |

### Produção ativa novamente

Evidência de atividade pós-retomada (não depende só de `decisions.jsonl`):

- `provider_evidence.latestReceivedUtc` avançando (`16:29:36Z`)
- `market_observation.last_succeeded_utc` `16:29:33Z`
- `order_flow.last_succeeded_utc` `16:29:36Z`
- `task_scheduler.completed` **6941** (incrementou vs pré-retomada)
- Ciclos cron com **Last run** atualizado após retomada

**Nota:** `decisions.jsonl` não cresceu no intervalo observado (~70 s) — esperado entre ticks de decisão flat (cadência 5 min). Atividade de mercado/evidência confirma retomada operacional.

**Snapshot:** `evaluation/runs/post-resume-health-2026-09-02.json`

---

## Nota Hermes UI

Jobs retomados aparecem como **`[active]`** (não `running`). Critério operacional: status `active` + `Last run` recente com `ok`.
