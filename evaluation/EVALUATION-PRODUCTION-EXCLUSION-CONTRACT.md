# Contrato de exclusão — evaluation × produção (rascunho)

**Status:** `IMPLEMENTED_v1` — lease + cron defer + preflight (fault injection / live validation pending)  
**Bloqueia replay até:** preflight + testes verdes  
**Substitui:** pausa manual de cron como procedimento permanente (workaround r15 apenas)

---

## Princípio

Replay cognitivo **nunca** compete com mutação operacional em `state/` de produção. Evaluation detém um **lease** explícito; produção (cron `direct_cycle`, `wake_monitor`, `learning`) **reconhece** o lease e **adia** — não escreve em artefatos monitorados.

---

## Lease evaluation

| Campo | Valor proposto |
|-------|----------------|
| Schema | `glitch.topstep.evaluation_lease.v1` |
| Path | `state/evaluation-lease.json` |
| `owner_kind` | `evaluation` |
| Prioridade | 40 (não preempta `direct_cycle` 100) |
| Duração | TTL renovável por invocação; hard cap = `total_timeout_ms` budget |
| Artefatos protegidos | `decisions.jsonl`, `receipts.jsonl`, `outbox/`, `profile-state.sqlite`, `model-owner.lock` (produção) |

---

## Regras de exclusão

1. **Início bloqueado** se `production_lane_active` (`direct_cycle`/`repair`/`wake_monitor` com lock ativo).
2. **Início bloqueado** se lease evaluation não puder ser registrado atomicamente.
3. **Durante lease:** cron que mutaria produção deve **adiar** (não falhar silenciosamente nem escrever).
4. **Fim lease:** cron retoma no próximo tick; sem intervenção manual.
5. **Abort:** mutação detectada em snapshot pré/pós → `production_operational_artifacts_mutated` · preservar artefatos parciais · exit ≠ 0.
6. **Timeout:** lease expira; evaluation aborta; cron pode retomar.
7. **Restart/recovery:** lease órfão detectável; TTL evita deadlock permanente.

---

## Teste crítico (aceitação)

```text
evaluation inicia (lease adquirido)
  → cron tenta executar
  → cron adia (sem mutação operacional)
  → evaluation termina (lease liberado)
  → cron retoma normalmente
```

Validar também: abort mid-run, timeout, restart com lease stale, zero mutação operacional em replay completo.

---

## Sequência de implementação

```text
definir contrato de exclusão evaluation × produção     ← este documento
  → impedir início com lease conflitante
  → fazer cron reconhecer o lease e adiar o ciclo
  → testar cron iniciando durante evaluation
  → validar abort, timeout, restart e recuperação
  → confirmar zero mutação operacional
  → atualizar preflight
```

Entrega preflight: `scripts/preflight-evaluation-replay.py` integrado a `run-scenario-live-replay.py`.

---

## Fora de escopo do lease

| Atividade | Cron ativo? |
|-----------|-------------|
| Captura PRAC operacional (gateway) | **sim** — fluxo normal |
| Ingest / coorte offline | **sim** |
| Replay cognitivo Hermes | **não** até preflight verde |

---

## Referências

- `evaluation/EVALUATION-CRON-COORDINATION-PENDING.md`
- `evaluation/reviews/R15-EVALUATION-CRON-COORDINATION-INCIDENT-2026-09-02.md`
- `evaluation/OWNERSHIP-EVALUATION-SPEC.md`
