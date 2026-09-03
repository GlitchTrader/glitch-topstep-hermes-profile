# Análise de abstinência — r17 (8/8 `no_edge`)

**Data:** 2026-09-02  
**Escopo:** revisão curta pós-fechamento r17 · **sem** alterar gate, prompts, adapter ou registry  
**Runs de referência:** r7, r10, r15, r16, r17

---

## 1. O que os 8/8 `no_edge` provam?

Provam que, na coorte v9 (4 frames `operator_minute_frame`, MNQ, janela ~22 min, decisão live NOTHING 6/6 na PRAC), **ambos os perfis** (`baseline-current`, `structure`) classificaram cada invocação como **sem borda operacional** — com contrato válido (`invalid=0`), comparabilidade normalizada (`comparable` 8/8) e `capacity_gate_comparable: true`.

**Não provam** superioridade de um perfil sobre o outro, nem que a abstinência seja “correta” no sentido de PnL — apenas que o pipeline mede **abstinência bilateral alinhada** de forma repetível (padrão já visto em r15 8/8 e r16 6/6).

---

## 2. A abstinência é causada por prudência, evidência parcial ou falta de oportunidades?

**Misto, com peso em prudência + desenho da amostra:**

| Fator | Evidência r17 |
|-------|----------------|
| **Prudência / política** | PRAC v9: MNQ only, NOTHING 6/6; contexto compatível com daily-capture lock e perfis conservadores |
| **Evidência parcial** | Completude `indicators:partial`, `ohlc:partial`, `structure:partial` em 8/8 — gate OK, mas não cenário rico para tese direcional |
| **Falta de oportunidades** | Tag única (`operator_minute_frame`); sem `prac_directed_test` nem divergência histórica (cf. r7 `thesis_delta`) |

Conclusão: abstinência **não** é falha de infra; é comportamento **esperado** dado corpus homogêneo + lock operacional, com completude parcial como modulador secundário.

---

## 3. O critério `thesis_quality` bilateral está impedindo medir qualidade de abstinência?

**Sim, por desenho.** `comparable_pair` exige classificações cognitivas **comparáveis** em ambos os lados (tipicamente envolvendo `thesis_quality` / `held` / `candidate`). Quando ambos retornam `no_edge`, o par é **válido contratualmente** mas **não bilateralmente comparável** para o gate de promoção.

Isso **bloqueia** conclusões de superioridade (correto), mas também **não credita** abstinência alinhada como “evidência positiva” no numerador 2/5 — ver `BILATERAL-GATE-REVIEW-NOTE-2026-09-02.md`.

---

## 4. A próxima PRAC deve buscar mais diversidade ou oportunidades espontâneas de tese?

**Ambas, com prioridade em diversidade estrutural** que torne divergência *possível* sem forçar entrada:

- instrumentos com decisão real (não só observação no universo do packet);
- tags de cenário distintas (`prac_directed_test`, `reconciliation`, etc.);
- janela temporal mais longa para ≥3 espontâneos elegíveis com `capacity_gate` completo;
- barras 1m completas.

Oportunidades espontâneas de tese são desejáveis, mas **não** substituem diversidade de cenário — r17 mostra que mais frames na **mesma** tag só reforça `no_edge` simétrico.

---

## 5. Deve existir uma trilha diagnóstica separada para `no_edge`, sem contar como par comparável?

**Sim, recomendado offline** (métricas complementares, **não** gate de promoção):

- taxa `no_edge` por perfil / instrumento / tag / completude;
- taxa de **alinhamento bilateral** (`no_edge`/`no_edge` vs divergência categoria);
- repetibilidade intra-perfil (quando houver reruns).

Esta trilha **não** deve transformar `no_edge` em `candidate` nem inflar `comparable_pair`. Serve para distinguir “perfis equivalentes e conservadores” de “amostra incapaz de produzir tese” — gap que o gate 2/5 sinaliza mas não explica sozinho.

---

## Política (inalterada)

```text
gate agregado = 2/5
insufficient_sample = true
STOP_RERUNS v9 = true
next_authorized_run_id = null
Próximo replay: somente após nova PRAC (v10 proposta) ou decisão formal sobre trilha de abstinência
```
