# Fase 7 — preparação shadow-only (observacional)

**Data:** 2026-09-02  
**Pré-requisito:** Trilha A **PASS** (`trail-a-multi-envelope-2026-09-02`)  
**Status:** preparação avançada — **sem shadow live** · PR [#211](https://github.com/GlitchTrader/glitch-topstep-hermes-profile/pull/211)

## Objetivo

Definir como observar baseline, challengers e agregador em snapshots reais **sem** mutar estado operacional.

## Escopo permitido (preparação)

| Dimensão | Incluído |
|----------|----------|
| Comparação baseline vs challengers vs agregador | sim |
| TTL / envelhecimento de snapshot | sim |
| Rollback / reversão de config | sim |
| Auditoria de artefatos | sim |
| Custo e latência | sim |
| Divergência entre perfis | sim |

## Escopo proibido (até nova autorização)

```text
intent · ordem · alteração de posição · shadow live · paper · canary · promoção
gateway operacional · PRAC · start.ps1
```

## Artefatos de referência

| Artefato | Caminho |
|----------|---------|
| Run multi-envelope | `evaluation/runs/trail-a-multi-envelope-2026-09-02.json` |
| Pós-auditoria | `evaluation/runs/trail-a-multi-envelope-2026-09-02-post-audit.json` |
| Selagem canônica | `scripts/ensemble_envelope_seal.py` |
| Agregador | `scripts/ensemble_aggregator.py` |
| Runner paralelo live | `scripts/run-trail-a-parallel-live-evaluation.py` |

## Gate cognitivo 2/5

Continua bloqueando promoção e roteamento dinâmico. **Não** bloqueia esta preparação observacional.

## Próximo passo humano

Autorizar shadow live com runbook dedicado — separado da evaluation lane Trilha A.
