# Fase 7 — shadow live runbook (preparação)

**Status:** preparação · **execução live BLOQUEADA** até preflight PASS + autorização humana específica  
**Gate cognitivo 2/5:** inalterado — bloqueia promoção/roteamento, não esta preparação

## Pré-requisitos

- Marco six-profile offline **PASS** (`eval-milestone-six-profiles-2026-09-02`)
- Pacote congelado: `evaluation/release/six-profile-evaluation-package-2026-09-02.json`
- `HERMES_HOME` evaluation isolado (`glitch-topstep-evaluation`)
- Mercado **fora** de janela de manutenção

## Preflight (não inicia gateway/Hermes)

```powershell
python scripts/build-evaluation-release-package.py
python scripts/shadow-preflight.py --run-id shadow-live-prep-2026-09-02 `
  --gateway-health evaluation/runs/gateway-health-preflight.json `
  --output evaluation/runs/shadow-live-preflight-2026-09-02.json
```

Se mercado em manutenção:

```text
status: shadow_not_ready:maintenance_window
```

**Não** executar `start.ps1` · **não** iniciar Hermes · **não** abrir sessão live.

## Checklist preflight

| Check | Esperado |
|-------|----------|
| gateway health | `status: ok` · `state_complete: true` |
| market valid | streams connected |
| `daily_capture_locked` | `false` |
| barras 1m | completas |
| lease | disponível ou coordenação LIVE_VALIDATED |
| cron defer | funcional |
| custo | cap conhecido (`max_cost_usd_per_session`) |
| 6 perfis | `evaluation_enabled` · `execution_authority: false` |

## Sessão shadow (somente após revisão técnica + autorização)

```powershell
# BLOQUEADO por padrão — requer --authorize explícito
python scripts/shadow-observe-live.py `
  --run-id shadow-live-session-001 `
  --authorize `
  --output evaluation/runs/shadow-live-session-001.json
```

### Parar imediatamente se

```text
write operacional
hash divergente
perfil fora do HERMES_HOME evaluation
lease incorreto
custo desconhecido
snapshot inválido
```

### Garantias obrigatórias

```text
intents_sent=0
orders_sent=0
writes_operacionais=0
production_parallelism=blocked
promotion_use_allowed=false
```

## Critério de avanço Fase 7

**Não** avançar para paper/canary/promoção com uma única sessão.

Exigir várias sessões estáveis:

- zero writes
- zero divergências inexplicadas
- custo/latência aceitáveis
- proveniência completa
- agregador determinístico
- rollback comprovado

## Validação offline (sem live)

```powershell
python scripts/run-shadow-phase7-validation.py --run-id shadow-phase7-validation-2026-09-02
python -m unittest tests.test_shadow_phase7 -v
```

## Proibido até nova autorização

```text
roteamento dinâmico · seleção operacional · promoção · execução de intents · shadow sem preflight
```
