# Revisão de contrato — novos perfis evaluation lane v3

**Data:** 2026-09-02 · **Registry:** `2026-09-02-v3` · **Matrix:** `2026-09-02-v3`  
**Escopo:** `smart-money`, `indicators`, `orderflow` — evaluation lane apenas · **sem autoridade de execução**

## Sequência de integração

| Ordem | Perfil | Testes | Contrato |
|-------|--------|--------|----------|
| 1 | `smart-money` | `test_expanded_evaluation_milestone` · matrix audit | PASS |
| 2 | `indicators` | idem | PASS |
| 3 | `orderflow` | idem | PASS |

Integração final: `run-evaluation-milestone.py` → ensemble 6 perfis → shadow-only offline → proveniência → **PASS**.

## smart-money

| Campo | Valor |
|-------|-------|
| Kit | `evaluation/profiles/smart-money.v1.json` |
| `execution_authority` | `false` |
| Fontes obrigatórias | `ohlc`, `quote`, `structure`, `session` |
| Fontes opcionais | `orderflow`, `risk_context`, `indicators` |
| Tools | `structural_levels`, `setup_state` (documentadas no profile root) |
| Raw / normalized | `profile_raw_output.v1` → `normalized_candidate.v1` |
| Completude | `available` … `not_applicable` (6 estados) |
| Limitações | Sem nomes de padrão como prova direcional; sem intents |

Evidência ausente: classificada via `completeness_states` + normalização; perfil abstém (`no_edge`) quando fontes obrigatórias faltam.

## indicators

| Campo | Valor |
|-------|-------|
| Kit | `evaluation/profiles/indicators.v1.json` |
| `execution_authority` | `false` |
| Fontes obrigatórias | `ohlc`, `quote`, `indicators` |
| Fontes opcionais | `session`, `risk_context`, `structure` |
| Tools | `market_observation`, `scanner_contract` |
| Raw / normalized | `profile_raw_output.v1` → `normalized_candidate.v1` |
| Limitações | Indicadores não são gatilho automático de entrada |

## orderflow

| Campo | Valor |
|-------|-------|
| Kit | `evaluation/profiles/orderflow.v1.json` |
| `execution_authority` | `false` |
| Fontes obrigatórias | `ohlc`, `quote`, `orderflow` |
| Fontes opcionais | `session`, `risk_context`, `structure` |
| Skills | inclui `orderflow-liquidity` |
| Tools | `market_observation`, `scanner_contract` |
| Raw / normalized | `profile_raw_output.v1` → `normalized_candidate.v1` |
| Limitações | Profundidade ausente **não** é veto de execução (apenas classificação de evidência) |

## Agregador (6 perfis)

Fixtures: `evaluation/fixtures/aggregator_decision_cases_six_profiles.v1.json`

Casos cobertos: todos `no_edge` · candidato único · equivalentes · opostos · sem capacidade · timeout múltiplo · adversarial crítico · perfil ausente · `classified_failure` · `no_selection`.

## Shadow-only offline (Fase 7 prep)

Script: `scripts/shadow-observe-offline.py`

Fluxo: envelope → perfis → agregador → baseline → registro contrafactual.

Registra: decisão por perfil · decisão global · candidatos não selecionados · custo · latência · idade do snapshot · completude · divergências · motivo `no_selection`.

**Não** envia intents · **não** toca gateway.

## Gate próxima etapa

| Critério | Status |
|----------|--------|
| Capability matrix válida | PASS |
| Schema válido | PASS |
| Output normalizado | PASS |
| Evidência ausente classificada | PASS |
| Testes verdes (599) | PASS |
| Zero writes operacionais | PASS |
| `evaluation_enabled` nos 3 novos | **true** |
| Shadow live | **BLOCKED** |
| Promoção / roteamento | **BLOCKED** (gate cognitivo 2/5) |

## Próximo marco

```text
6 perfis → mesmo envelope → avaliação paralela → agregador offline → shadow-only offline → relatório estabilidade/diversidade
```

**Status:** executável offline **PASS** (`eval-milestone-six-profiles-2026-09-02`). Decisão humana pendente: preparar shadow live **ou** corrigir perfis/capabilities.
