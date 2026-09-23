# Incidente — isolamento evaluation × cron de produção (r15)

**Data:** 2026-09-02  
**Run:** `scenario-live-2026-09-02-r15-v7`  
**Severidade:** operacional (abort correto; sem mutação não detectada)  
**Status:** mitigado manualmente · **correção estrutural pendente**

---

## Resumo

O replay cognitivo r15 expôs que o **isolamento de avaliação não é completo** quando cron jobs de produção permanecem ativos:

| Tentativa | Resultado | Causa |
|-----------|-----------|-------|
| 1 | `deferred` | `production_lane_active` (`direct_cycle` com lock) |
| 2 | **Abort** após 1ª invocação | `production_operational_artifacts_mutated` |
| 3 | **COMPLETE 8/8** | cron jobs pausados manualmente antes do replay |

A guarda `assert_operational_artifacts_unchanged` funcionou: detectou escrita em `state/decisions.jsonl` (e possivelmente outros artefatos) **durante** invocação Hermes de evaluation, mesmo com `HERMES_HOME` isolado.

---

## Mecanismo

1. **Lock de produção** (`model-owner.lock` · `owner_kind=direct_cycle`) bloqueia *início* quando lane ativa (`defer`).
2. Entre `acquire` evaluation e fim da invocação Hermes (~12–16 s), **cron pode executar** e append em artefatos de produção.
3. Snapshot pré/pós em `production_state_root()` detecta drift → `PermissionError`.

**Gap:** não há coordenação formal evaluation ↔ cron; pausa manual foi workaround, não contrato.

---

## Mitigação aplicada (r15)

```powershell
hermes --profile glitch-topstep cron pause fb34a7e30b8b  # direct-operator
hermes --profile glitch-topstep cron pause ba7bb89414c7  # learning-supervisor
hermes --profile glitch-topstep cron pause ac5ceb3e6242  # wake-monitor
```

Replay bem-sucedido com jobs pausados. Retomada documentada em `CRON-RESUME-RECORD-2026-09-02.md`.

---

## Impacto

| Área | Impacto |
|------|---------|
| Integridade r15 | **OK** — tentativa 2 abortou; tentativa 3 íntegra |
| Gate cognitivo | **2/5** inalterado |
| Produção | Sem exposição desprotegida; pausa ~5 min |
| Próximo replay | **BLOQUEADO** até correção estrutural |

---

## Pendência técnica (obrigatória antes do próximo replay)

Ver plano: `evaluation/EVALUATION-CRON-COORDINATION-PENDING.md`

```text
documentar incidente          ← este arquivo
→ definir coordenação formal evaluation × cron
→ impedir início se jobs concorrentes
→ testar abort/recovery
→ validar novamente
```

**Paralelo permitido:** preparação nova PRAC diversa.  
**Proibido:** repetir v7 · agregador · replay sem coordenação.

---

## Referências

- `evaluation/reviews/R15-POST-EXECUTION-REPORT-2026-09-02.md`
- `evaluation/OWNERSHIP-EVALUATION-SPEC.md` (§ prioridade vs direct_cycle)
- `scripts/evaluation_cognitive_replay.py` (`operational_artifact_snapshot`)
- `evaluation/runs/stratified-cohort-execution-registry.json` → `evaluation_cron_coordination_pending`
