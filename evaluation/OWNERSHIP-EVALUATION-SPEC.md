# OwnerKind=evaluation — especificação formal (v1)

**Status:** implementado em `model_owner_lock.py` + `evaluation_owner.py`; replay cognitivo permanece bloqueado (`COGNITIVE_REPLAY_ALLOWED=false`)  
**Data:** 2026-09-01  
**Schema máquina:** `evaluation/schemas/ownership_evaluation.v1.json`  
**Contexto:** encerramento da avaliação histórica como **insuficiente**; replay cognitivo bloqueado até esta spec + fault injection + testes verdes.

## Objetivo

Isolar invocações Hermes de avaliação/replay cognitivo da lane de produção (`direct_cycle`), do aprendizado (`learning`) e de qualquer escrita em outbox/intents/receipts operacionais.

## Estado acordado (gates)

```text
integridade dos artefatos       PASS
qualidade cognitiva histórica   INSUFICIENTE
captura histórica futura        GAP identificado
replay de artefatos             permitido
replay cognitivo                bloqueado
agregador executável            bloqueado
paralelismo                     bloqueado
shadow ao vivo                  bloqueado
promoção                        bloqueada
```

## Dois tipos de replay

| Tipo | Invoca Hermes | Estado | Operações |
|------|---------------|--------|-----------|
| **Replay de artefatos** | Não | **Permitido** | join, normalização, capacity gate, compare, métricas offline |
| **Replay cognitivo** | Sim | **Bloqueado** | envelopes congelados → Hermes → decisão candidata |

Replay de artefatos é o runner atual (`scripts/run-ensemble-evaluation.py`). Replay cognitivo exige `OwnerKind=evaluation` implementado, `HERMES_HOME` isolado, fault injection com dois processos e ausência de mutação em estado de produção.

## Prioridade vs direct_cycle e learning

Ordem numérica (maior preempta menor):

| OwnerKind | Prioridade | Notas |
|-----------|------------|-------|
| `direct_cycle` | 100 | Produção; nunca preemptado por evaluation |
| `repair` | 90 | Recuperação operacional |
| `wake_monitor` | 80 | Monitor de wake |
| **`evaluation`** | **40** | Replay cognitivo; janelas offline/agendadas |
| `learning` | 10 | Defer quando evaluation segura lock |

Regras:

1. `evaluation` **nunca** preempta `direct_cycle`, `repair` ou `wake_monitor`.
2. Com lock de produção ativo (`direct_cycle` vivo em `state/model-owner.lock`), replay cognitivo **defer ou abort** — não aguardar indefinidamente em HERMES_HOME compartilhado.
3. `learning` defer quando `evaluation` detém lock no mesmo `HERMES_HOME` de avaliação (não no de produção).
4. Prioridade sozinha não basta: evaluation usa **state root e lock separados** da produção.

## Estado e diretório próprios

| Recurso | Produção | Evaluation |
|---------|----------|------------|
| State root | `state/` (profile) | `evaluation/state/<run_id>/` |
| Lock | `state/model-owner.lock` | `evaluation/state/<run_id>/model-owner.lock` |
| Journal decisões | `state/decisions.jsonl` | `evaluation/state/<run_id>/decisions.jsonl` (somente avaliação) |
| Receipts | `state/receipts.jsonl` | **proibido** escrever em produção; receipts de avaliação só em run dir |

Paths de produção **proibidos** para evaluation:

- `state/decisions.jsonl`
- `state/receipts.jsonl`
- `state/outbox/`
- `state/profile-state.sqlite`
- `state/model-owner.lock`

## HERMES_HOME isolado

- Produção: `%LOCALAPPDATA%/hermes/profiles/glitch-topstep` (ou `HERMES_HOME` operacional).
- Evaluation: `%LOCALAPPDATA%/hermes/profiles/glitch-topstep-evaluation` (obrigatório diferente).
- Skills: cópia read-only ou symlink no início do run; sem mutar skills de produção.
- Subárvores graváveis: `state`, `tmp`, `runs` **dentro** do HERMES_HOME de evaluation apenas.

Variável `HERMES_HOME` deve ser setada **antes** de qualquer subprocess Hermes no run de evaluation.

## Ausência de outbox / intents / receipts de produção

Replay cognitivo:

- **Não** importa `intent_outbox`, `entry_delivery`, `workflows` de produção.
- **Não** submete intents ao gateway (`glitch.intent.v3` permanece congelado nesta fase).
- **Não** append em `state/receipts.jsonl` de produção.
- Saída: artefatos em `evaluation/runs/<run_id>.json` e `evaluation/state/<run_id>/events.jsonl`.

## Credenciais e rate limits

- **Auth padrão (OAuth):** mesmo modelo/provider de `config.yaml` (`gpt-5.6-luna` / `openai-codex`), via routing Hermes — **sem** API key no `.env`.
- Configurar OAuth **uma vez** no profile de evaluation:
  ```text
  hermes -p glitch-topstep-evaluation auth add openai-codex --type oauth
  ```
- `HERMES_HOME` de evaluation permanece isolado (`glitch-topstep-evaluation`); OAuth é **por perfil**, não compartilhado com produção.
- **Legado (opt-in):** `EVALUATION_AUTH_MODE=api_key` + `EVALUATION_OPENROUTER_API_KEY` em `evaluation/.env`.
- Orçamentos (defaults em `ensemble_config.json` / spec JSON):
  - `max_calls_per_snapshot`: 6
  - `max_calls_per_session`: 36
  - `per_profile_timeout_ms`: 35000
  - `total_timeout_ms`: 120000
  - `max_cost_usd_per_session`: 2.5

## Timeout e tree-kill

- Supervisor: `process_supervisor.run_supervised` (mesmo padrão do cycle).
- Timeout por perfil e total: ao estourar, **tree-kill** obrigatório.
- Windows: `taskkill /F /T`; Unix: `killpg`.
- Pós-timeout: estado `failed` ou `timeout` no run dir; lock libertado.

## Restart e recuperação

1. Run identificado por `run_id` (UUID ou timestamp UTC).
2. Restart retoma de `evaluation/state/<run_id>/checkpoint.json` se existir; senão aborta com auditoria.
3. Lock órfão: mesma heurística de `model_owner_lock` (pid + `process_start_utc`).
4. Recovery **não** reconcilia com gateway nem reenvia intents.

## Comportamento quando production lane está ativa

Sinais de produção ativa:

- `state/model-owner.lock` com `owner_kind=direct_cycle` e processo vivo
- Gateway `trading_mode` armed com exposição aberta
- PID do scheduler/cycle de produção vivo

Comportamento evaluation:

- Replay cognitivo: **abort** ou **defer** (default **defer** com backoff).
- `defer_if_production_lane=False` é **proibido** em operação normal; só permitido com `EVALUATION_TEST_ALLOW_LANE_OVERLAP=true` (testes).
- Nunca escrever em paths de produção.
- Nunca submeter intents ao gateway.
- Replay de artefatos (offline runner) permanece permitido — não toca Hermes nem produção.

## Fault injection (dois processos)

**Obrigatório** antes de abrir paralelismo ou agregador executável.

Cenário mínimo:

1. Processo A: evaluation run em `HERMES_HOME` isolado, `run_id=A`.
2. Processo B: segundo evaluation run ou learning legítimo em home distinto.
3. Verificar:
   - zero mutação em `state/` de produção
   - zero bleed entre HERMES_HOME
   - tree-kill sem órfãos
   - segundo processo defer ou corre em `run_id` separado

Evidência: `tests/test_fault_injection.py` estendido (fase futura).

## Rollback e auditoria

Modos de rollback:

- `abort_run`: tree-kill + descartar lock
- `discard_run_directory`: remover `evaluation/state/<run_id>/`
- `baseline_fixture_only`: voltar a fixtures congelados sem Hermes

Artefatos de auditoria obrigatórios:

- `evaluation/runs/<run_id>.json`
- `evaluation/state/<run_id>/events.jsonl`
- logs de invocação por perfil

## Implementação (fase seguinte — fora deste entregável)

1. Adicionar `evaluation` a `OwnerKind` e `PRIORITY` em `model_owner_lock.py`
2. Entrypoint `scripts/run-evaluation-replay.py` (cognitive) com gates acima
3. Estender fault injection
4. **Não** implementar agregador executável nesta fase

## Referências

- `docs/evidence/HERMES-CLI-ISOLATION-MATRIX.md` (gateway)
- `docs/evidence/PRAC-EVIDENCE-CHAIN-FORMAT.md` (gateway) — captura futura PRAC
- `evaluation/schemas/prac_evidence_chain.v1.json`
- `docs/evidence/PRAC-DECISION-EXPORT-INVENTORY-2026-09-01.md`
