# Diagnóstico baseline `no_edge` — run r11

**Trilha:** 1 — Diagnóstico baseline  
**Run:** `scenario-live-2026-09-01-r11-v2`  
**Gerado:** 2026-09-01  
**Escopo:** 6 envelopes × 2 perfis (`baseline-current`, `structure`) = 12 invocações  
**Fontes:** `evaluation/runs/scenario-live-2026-09-01-r11-v2.json`, quality/diversity reports, `evaluation/comparable_scenarios.v2.json`, frames em `tests/fixtures/frozen_corpus/enriched/minute-frames/`

---

## Resumo executivo

| Métrica | Valor |
|---------|-------|
| Baseline `no_edge` | **6/6** (100%) |
| Structure `no_edge` | 5/6 (83%) |
| Structure `held` | 1/6 (`SCN-PRAC-RECONCILIATION`) |
| `missing_required_evidence` | **0/12** |
| `capacity_gate.comparable` | **12/12** true |
| `comparable_pair` | **0/6** |
| `no_edge_rate` (run) | 91.7% (11/12) |

O baseline emitiu `no_edge` em todos os envelopes. Nenhuma invocação foi classificada como `missing_required_evidence`. O `comparable_pair: false` em 6/6 cenários é consequência direta da regra bilateral (`thesis_quality` + `thesis_quality`); baseline em `no_edge` **não conta** como par comparável — limitação de categoria, não falha de contrato.

**Veredito:** o `no_edge` baseline em r11 é **predominantemente legítimo** — coerente com geometria de mercado (preço estendido em extremos de range) e com a política de entrada do perfil. Não há evidência de gate de evidência obrigatória bloqueando decisão.

---

## Tabela resumo por envelope

| Cenário | Frame | Regime (manifest) | Baseline | Structure | Evidência obrigatória | Classificação | Coerência baseline | Legítimo? |
|---------|-------|-------------------|----------|-----------|----------------------|---------------|---------------------|-----------|
| SCN-OPERATOR-MIDSESSION | `20260901T134026Z-bb50bbe9` | TREND_DOWN | `no_edge` / flat | `no_edge` / flat | OK (`missing_required: []`) | `no_edge` | Sim — estrutura bearish estendida perto do low local | **Sim** |
| SCN-OPERATOR-AFTERNOON | `20260901T150823Z-d7908a55` | TREND_DOWN | `no_edge` / flat | `no_edge` / flat | OK | `no_edge` | Sim — momentum bearish forte, preço no low 5m/60s | **Sim** |
| SCN-PRAC-TIMEOUT-RECOVERY | `20260901T000528Z-041dc508` | TREND_UP | `no_edge` / flat | `no_edge` / flat | OK | `no_edge` | Sim — rally pressionando high de range, delta misto | **Sim** |
| SCN-PRAC-RESTART-BRACKET | `20260831T235211Z-cdbf204f` | TREND_UP | `no_edge` / flat | `no_edge` / flat | OK | `no_edge` | Sim — estrutura bullish estendida acima de VWAP/EMA | **Sim** |
| SCN-PRAC-RECONCILIATION | `20260901T143431Z-534fefd5` | TRANSITION | `no_edge` / hold | `held` / long | OK | `no_edge`* | Parcial — exposição long existente; baseline recusa novo candidato mas normaliza como `no_edge` com `action: HOLD` | **Parcial**† |
| SCN-PRAC-PREFLIGHT | `20260901T182843Z-b06d9a93` | TREND_DOWN | `no_edge` / flat | `no_edge` / flat | OK | `no_edge` | Sim — downtrend forte, preço esticado no low 5m/60s | **Sim** |

\* Baseline declara `no_edge` com `direction: hold` e `action: HOLD` — abstinência de **novo** candidato, não flat puro.  
† Legítimo como abstinência de nova entrada; divergência com structure (`held`) é interpretação de exposição existente, não gap de evidência obrigatória.

---

## Diagnóstico detalhado por envelope

### SCN-OPERATOR-MIDSESSION (`20260901T134026Z-bb50bbe9`)

**Contexto congelado**
- Captura: `2026-09-01T13:40:26Z`, MNQ @ 29057.25
- Sessão: `phase=regular`, `entry_window_open=true`, sem posição aberta
- `market_observation`, `structural_levels`, `order_flow`: presentes
- `session_levels_reliable: false` (high/low espelham last)
- Barra 1m parcial (~43%)

**Baseline**
- Estado: `no_edge`, direção `flat`, ação `NOTHING`
- Razão declarada: estrutura bearish multi-timeframe estendida perto do low local; short tardio com risco de reversão; long sem reclaim confirmado
- `capacity_gate`: `comparable=true`, `missing_required=[]`
- `completeness_used`: indicators/ohlc/structure `partial`; quote/orderflow/risk_context/session `available`
- `horizon_bars`: null

**Structure**
- Mesmo `no_edge`; tese alinhada (selloff estendido, área de session-low não confiável)

**no_edge vs missing_required_evidence:** `no_edge` cognitivo. Gate de capacidade passou.

**Coerência:** alta. Frame TREND_DOWN com preço no extremo inferior após movimento — abstinência esperada para baseline conservador.

---

### SCN-OPERATOR-AFTERNOON (`20260901T150823Z-d7908a55`)

**Contexto congelado**
- Captura: `2026-09-01T15:08:23Z`, MNQ @ 29186.25
- Mesma estrutura de sessão (regular, janela aberta, flat)
- Regime manifest: TREND_DOWN

**Baseline**
- Razão: momentum bearish 1m–60m, mas preço já nos lows 5m/60s com tape estabilizado; long exige reclaim, short exige aceitação abaixo do low
- Evidência: completa para gate; parcial em OHLC/indicadores/estrutura

**Structure**
- `no_edge` unânime; tese espelha (flow 15s estabilizado após queda)

**no_edge vs missing_required_evidence:** `no_edge`.

**Coerência:** alta. Segundo frame operator no mesmo regime; padrão idêntico ao midsession.

---

### SCN-PRAC-TIMEOUT-RECOVERY (`20260901T000528Z-041dc508`)

**Contexto congelado**
- Captura: `2026-09-01T00:05:28Z`, MNQ @ 29516.75
- Flat, pós-timeout recovery (tag procedural)
- Regime manifest: TREND_UP

**Baseline**
- Razão: estrutura bullish HTF, mas preço pressionando high de range; delta 60s levemente negativo, delta amplo neutro, depth indisponível
- Cita risco de invalidação estrutural sem assimetria limitada

**Structure**
- `no_edge`; rally forte mas estendido no high 5m

**no_edge vs missing_required_evidence:** `no_edge`. Depth indisponível citado na tese mas **não** acionou `missing_required_evidence`.

**Coerência:** alta para cenário de continuação tardia em TREND_UP.

---

### SCN-PRAC-RESTART-BRACKET (`20260831T235211Z-cdbf204f`)

**Contexto congelado**
- Captura: `2026-08-31T23:52:11Z`, MNQ @ 29511
- Pre-flatten restart bracket; flat
- Regime manifest: TREND_UP
- Barra 1m parcial (~18%)

**Baseline**
- Razão: estrutura bullish 1m–60m, preço estendido acima VWAP/EMA no topo do range; delta neutro, tape flat, participação baixa, evidência de barra parcial

**Structure**
- `no_edge`; high parcial 5m com delta neutro

**no_edge vs missing_required_evidence:** `no_edge`.

**Coerência:** alta. Frame de restart com mercado esticado — abstinência coerente.

---

### SCN-PRAC-RECONCILIATION (`20260901T143431Z-534fefd5`)

**Contexto congelado**
- Captura: `2026-09-01T14:34:31Z`, MNQ @ 29210
- **Exposição ativa:** 2 contratos abertos, 4 working orders
- Proteção `proven` (stop 29136, target 29232.75, tranches com child orders)
- Regime manifest: TRANSITION

**Baseline**
- Estado: `no_edge`, direção `hold`, ação `HOLD`
- Razão: exposição long inferida da geometria protetiva, mas envelope **não fornece preço de entrada preenchido**; preço pressionando highs 5m/tape (~29211–29212) com delta negativo vs rally; 60m ainda down → sem candidato direcional novo
- `missing_required: []`, `comparable: true`

**Structure**
- Estado: `held`, direção `long`, ação `HOLD`
- Entrada 29210, stop 29132.5; mantém posição com momentum 1m/5m
- Categoria challenger: `thesis_quality` (único frame com divergência categórica)

**no_edge vs missing_required_evidence:** `no_edge` — baseline trata como abstinência de nova tese, não como falha de gate. A lacuna de **filled entry price** é citada na tese como limitação do envelope congelado, mas o capacity gate não bloqueou.

**Coerência:** parcial. Para baseline, `no_edge` + `HOLD` é defensável (sem nova edge). Structure interpreta o mesmo frame como manutenção de posição (`held`). Divergência é **categórica** (`no_edge`↔`thesis_quality`), não evidência ausente. Histórico r9/r10 mostrou variância neste frame (bilateral `thesis_quality` em r10).

---

### SCN-PRAC-PREFLIGHT (`20260901T182843Z-b06d9a93`)

**Contexto congelado**
- Captura: `2026-09-01T18:28:43Z`, MNQ @ 29087.75
- Flat, sessão preflight
- Regime manifest: TREND_DOWN
- Barra 1m parcial (~73%)

**Baseline**
- Razão: estrutura bearish forte, preço esticado nos lows 5m/60s; delta positivo neutro, depth ausente; propõe gatilhos condicionais (break 29085.25 / reclaim 29100.25) sem candidato imediato
- Nota: `raw_profile_output.action` omitido; normalizado como `no_edge`/flat

**Structure**
- `no_edge`; selloff estendido perto da borda inferior do range 5m

**no_edge vs missing_required_evidence:** `no_edge`.

**Coerência:** alta. Preflight flat em downtrend estendido — abstinência alinhada.

---

## Padrões transversais

### Evidência e capacity gate

| Campo | Padrão (12/12) |
|-------|----------------|
| `classification.missing_required_evidence` | `false` |
| `capacity_gate.missing_required` | `[]` |
| `capacity_gate.comparable` | `true` |
| `comparability` (normalizado) | `comparable` |
| `invalid` / `schema_invalid` | 0 |

**Conclusão:** nenhum `no_edge` baseline em r11 é proxy de `missing_required_evidence`. A distinção está limpa.

### Completeness parcial (universal)

Em **todas** as invocações baseline:

```
indicators: partial
ohlc: partial
structure: partial
quote / orderflow / risk_context / session: available
```

Isso reflete fixtures enriquecidos com barras parciais e `session_levels_reliable: false`, não bloqueio de gate. O perfil **usa** a evidência disponível e declara cautela adicional na tese.

### Horizonte

`horizon_bars: null` em 6/6 baseline. O envelope congelado não expõe campo `decision_horizon`; o perfil opera no escopo de minuto implícito do packet (`expires_utc` +1 min). Ausência de horizonte explícito na saída é consistente com abstinência.

### Razões declaradas de `no_edge` (baseline) — temas recorrentes

1. **Preço estendido em extremo de range** (high ou low local / 5m / 60s) após movimento direcional forte
2. **Conflito multi-timeframe ou flow** (delta neutro/negativo contra direção estrutural)
3. **Entrada não limitada** — frase recorrente: *"no sufficiently bounded current-zone entry"*
4. **Confirmação pendente** — reclaim (long) ou aceitação abaixo do low (short)
5. **Barra parcial / participação baixa** (restart, preflight)

### Baseline vs structure

| Cenário | Alinhamento |
|---------|-------------|
| 5 cenários flat | Ambos `no_edge` — teses convergentes |
| SCN-PRAC-RECONCILIATION | Divergência: baseline `no_edge`/hold vs structure `held`/long |

`direction_match_rate` diagnóstico: 83.3% (5/6 frames flat-flat; reconciliation hold vs long).

---

## Top 3 causas-raiz do `no_edge` sistemático (baseline)

### 1. Geometria de mercado: preço estendido em extremos de range

**Evidência:** 6/6 teses baseline citam preço "near local low/high", "pressing range high/low", "extended selloff/rally". Frames congelados capturam momentos pós-movimento (TREND_DOWN nos lows, TREND_UP nos highs). Tanto baseline quanto structure concordam em 5/6.

**Impacto:** abstinência é resposta racional ao risco de continuação tardia vs reversão de curto prazo.

### 2. Política de entrada do baseline: exige zona de entrada limitada e confirmada

**Evidência:** frase estrutural repetida em operator, timeout, restart, preflight. Baseline reconhece direção estrutural mas recusa candidato por falta de assimetria limitada **na zona atual**.

**Impacto:** mesmo com `capacity_gate.comparable=true`, o perfil opta por `no_edge` — comportamento **by design**, não defeito de pipeline.

### 3. Completeness parcial + contexto de sessão não confiável (reforço de cautela)

**Evidência:** `indicators/ohlc/structure: partial` em 12/12; `session_levels_reliable: false` em todos os frames; barras 1m parciais (18%–73%). Citado explicitamente em restart (partial-bar evidence) e operator (unreliable session-low area).

**Impacto:** não dispara `missing_required_evidence`, mas aparece nas teses como fator de incerteza adicional. Contribui para abstinência sem invalidar o gate.

---

## `no_edge` é legítimo?

| Critério | Avaliação |
|----------|-----------|
| Gate de evidência obrigatória | **Passou** em 6/6 — não é `missing_required_evidence` disfarçado |
| Coerência com frame congelado | **Alta** em 5/6; **parcial** em reconciliation (hold vs no_edge) |
| Alinhamento bilateral | 5/6 unânime com structure; 1 divergência categórica esperada |
| Contrato de saída | 6/6 válidos (`semantic_alias_candidate`) |
| Expectativa do sampling plan | r9 já documentou baseline `no_edge` sistemático nestes tags; r11 **reproduz** o padrão |

**Resposta:** **Sim, predominantemente legítimo.** O baseline está abstendo com teses estruturadas que referenciam condições reais do envelope. O `comparable_pair: 0` não indica falha cognitiva — indica que o baseline não produziu `thesis_quality` em nenhum frame, o que é compatível com corpus selecionado (momentos de extremo / abstinência bilateral histórica em r8–r10).

**Única ressalva:** `SCN-PRAC-RECONCILIATION` — baseline em `no_edge` com `HOLD` enquanto structure em `held` sugere ambiguidade na taxonomia de exposição existente, não ausência de edge de mercado. Isso é divergência interpretativa, não evidência faltante.

---

## Implicações para Trilha 1 (sem alterar baseline)

Conforme escopo desta trilha, **não** se recomenda alterar o baseline para aumentar `comparable_pair`. Observações acionáveis fora do perfil:

1. **Corpus:** frames atuais concentram-se em extremos pós-movimento — úteis para testar abstinência, insuficientes para pares bilaterais `thesis_quality` (confirmado em `SAMPLING-PLAN-2026-09-01.md` e `corpus-coverage-gaps`).
2. **Reconciliation:** variância baseline/structure neste frame merece monitoramento em reruns; não é sintoma de gate quebrado.
3. **Métricas r11:** `no_edge_rate` 91.7%, `comparable_pair_rate` 0% — consistente com runs anteriores (r9–r10); amostra insuficiente para promoção (gate `≥5` pares independentes).

---

## Referências

| Artefato | Path |
|----------|------|
| Bundle r11 | `evaluation/runs/scenario-live-2026-09-01-r11-v2.json` |
| Quality report | `evaluation/runs/scenario-live-2026-09-01-r11-v2-quality-report.json` |
| Diversity metrics | `evaluation/runs/scenario-live-2026-09-01-r11-v2-diversity-metrics.json` |
| Cenários v2 | `evaluation/comparable_scenarios.v2.json` |
| Cohort manifest | `evaluation/runs/frozen-cohort-manifest-2026-09-01.json` |
| Sampling plan | `evaluation/SAMPLING-PLAN-2026-09-01.md` |
| Corpus gaps | `evaluation/reviews/CORPUS-COVERAGE-GAPS-2026-09-01.md` |
