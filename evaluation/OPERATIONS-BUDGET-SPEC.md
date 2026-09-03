# Orçamento e operação — avaliação offline (Trilha G)

**Data:** 2026-09-01  
**Config canónica:** `evaluation/ensemble_config.json`  
**Rates:** `evaluation/evaluation_cost_rates.v1.json`  
**Audit CLI:** `scripts/audit-evaluation-cost.py`  
**Ownership:** `evaluation/OWNERSHIP-EVALUATION-SPEC.md`

## Escopo

Define tetos de custo, chamadas, tokens e tempo para runs de avaliação (r7/r8/r9+). **Documentação e auditoria offline apenas** — sem Hermes adicional nesta trilha.

## Breakdown estimado vs confirmado

| `cost_basis` | Significado | Gate |
|--------------|-------------|------|
| `estimated_tokens` | tokens estimados por chars (`evaluation_cost_rates.v1.json`) | conta em `estimated_total_usd` |
| `provider_reported_usage` | usage reportado pelo provider | conta em `confirmed_total_usd` |
| `provider_reported_cost` | `cost_usd` direto no output do modelo | conta em `confirmed_total_usd` |
| `unknown` | sem pricing | **falha** `audit_gate_passed` |

O audit agrega `cost_breakdown` com totais separados e contagens por basis. `unknown` bloqueia expansão (`expansion_blocked_if_unknown: true`).

## Tetos de sessão e por perfil

Fonte: `ensemble_config.json` → `budget`:

| Campo | Default | Enforcement |
|-------|---------|-------------|
| `max_cost_usd_per_session` | 2.5 | acumulado por `session_id` |
| `max_tokens_per_call` | 50_000 | por invocação |
| `max_tokens_per_session` | 500_000 | acumulado por sessão |
| `max_calls_per_snapshot` | 6 | documentado; runner sequencial |
| `max_calls_per_session` | 36 | audit conta invocações por sessão |
| `per_profile` (opcional) | — | se presente em budget, teto `max_cost_usd_per_session` por perfil |

## Limites de tempo de execução

Referência `ensemble_config.json`:

| Campo | ms | Política |
|-------|-----|----------|
| `per_profile_timeout_ms` | 35_000 | tree-kill por perfil |
| `total_timeout_ms` | 120_000 | cap global sequencial |
| `total_latency_budget_ms` | 180_000 | orçamento de latência agregada |
| `aggregation_budget_ms` | 10_000 | reservado agregador (spec-only) |

`timeout_policy.mode`: `sequential_global_cap`  
`on_global_timeout`: `cancel_remaining_profiles`  
`record_state`: `timeout`

## Política de recuperação após timeout (documentação)

1. Supervisor (`process_supervisor.run_supervised`) aplica **tree-kill** (Windows: `taskkill /F /T`).
2. Perfil afetado: estado normalizado `timeout` — **excluído** do pool agregador; trace `PROFILE_TIMEOUT`.
3. Budget global esgotado antes de candidatos finais: `classified_failure` / `ensemble_timeout`.
4. Lock de avaliação libertado após tree-kill; **não** reconcilia com gateway nem reenvia intents.
5. Restart: retoma de `evaluation/state/<run_id>/checkpoint.json` se existir; senão aborta com auditoria.

## Retenção de artefatos

| Path | Conteúdo | Retenção |
|------|----------|----------|
| `evaluation/runs/` | bundles, artefatos por invocação, audits JSON | manter runs nomeados (r7, r8, r9); pruning manual por data |
| `evaluation/state/<run_id>/` | state isolado por run (decisions, lock, checkpoint) | safe cleanup quando run arquivado |

**Proibido** apagar ou mutar `state/` de produção (`state/decisions.jsonl`, `state/receipts.jsonl`, `state/outbox/`, `state/model-owner.lock`).

## Regras de cleanup seguro (evaluation state only)

1. Só remover subdirs em `evaluation/state/` cujo `run_id` está documentado como arquivado.
2. Nunca seguir symlinks para fora de `evaluation/`.
3. Preservar artefatos referenciados em `evaluation/runs/*.json` (`artifact_path`).
4. Cleanup não executa automaticamente — operador confirma run_id antes de `rm -rf evaluation/state/<run_id>`.

## Auditoria offline

```powershell
python scripts/audit-evaluation-cost.py `
  evaluation/runs/scenario-live-2026-09-01-r7-contract.json `
  evaluation/runs/scenario-live-2026-09-01-r8-contract.json `
  evaluation/runs/scenario-live-2026-09-01-r9-v2.json `
  --output evaluation/runs/evaluation-cost-audit-r7-r8-r9.json
```

Saída inclui `budget_reference`, `cost_breakdown`, `calls_audit`, `execution_time_audit`.
