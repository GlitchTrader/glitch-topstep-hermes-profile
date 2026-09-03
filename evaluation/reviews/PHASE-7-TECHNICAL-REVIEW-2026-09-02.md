# Fase 7 — revisão técnica shadow live (preparação)

**Data:** 2026-09-02  
**Escopo:** preparação observacional · **sem execução live autorizada**

## Resumo

| Item | Status |
|------|--------|
| Pacote six-profile congelado | `build-evaluation-release-package.py` |
| Observador offline 6 perfis | `shadow-observe-offline.py` · `shadow-observe-live.py` (prep) |
| Preflight shadow | `shadow-preflight.py` |
| Métricas multi-sessão | `report-shadow-metrics.py` |
| Auditoria isolamento | `audit-shadow-isolation.py` |
| Sequência validação | `run-shadow-phase7-validation.py` |
| Testes segurança | `tests/test_shadow_phase7.py` |
| Shadow live | **BLOCKED** |

## Arquitetura observador

```text
snapshot (real ou preservado)
  → 6 perfis (evaluation lane, slots=2)
  → agregador observacional
  → registro shadow_observation
  → comparação baseline
  → contrafactual / no_selection
```

Campos obrigatórios: decisão por perfil · candidatos · decisão global · não selecionados · `snapshot_hash` · `envelope_hash` · idade · completude · custo · latência · divergência · falhas isolamento.

## Garantias de segurança

```text
execution_authority=false (todos os 6 perfis)
intents_sent=0
orders_sent=0
writes_operacionais=0
production_parallelism=blocked
promotion_use_allowed=false
```

Verificação: `operational_artifact_snapshot` antes/depois · marcador `HERMES_HOME_ISOLATED` por slot.

## Preflight

Retorna `shadow_not_ready:maintenance_window` quando health degradado/recovery — **sem** iniciar gateway, Hermes ou sessão.

Outros bloqueios: `daily_capture_locked` · `state_complete=false` · barra parcial · lease ocupado · cron sem defer · custo desconhecido · drift de pacote.

## Replay eventos preservados

Trilha A (`trail-a-multi-envelope-2026-09-02`) usada **somente leitura** na validação — **não** repetida.

## Métricas shadow (multi-sessão)

`report-shadow-metrics.py`: latência p50/p95/p99 · custo · taxa erro · `no_selection` · divergência · correlação direcional · disponibilidade evidência · idade snapshot · writes operacionais.

## Gate cognitivo 2/5

Permanece bloqueio de promoção e roteamento dinâmico. Não alterado por esta preparação.

## Próximo passo humano

1. Revisar este documento + `SHADOW-LIVE-RUNBOOK.md`
2. Confirmar preflight em janela de mercado válida
3. Autorizar **uma** sessão shadow curta e limitada (`--authorize`)
4. Acumular **várias** sessões estáveis antes de paper simulado

## Não implementado (deliberado)

```text
roteamento dinâmico · seleção operacional · promoção · execução de intents
```
