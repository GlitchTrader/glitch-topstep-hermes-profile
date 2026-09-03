# Plano de encerramento — coleta limitada única

**Status:** `ACTIVE` · aguarda assinatura `MEASUREMENT-POLICY-2026-09-02-v1.md`  
**Pré-requisito:** `measurement_policy_approval = approved` (humano)

```text
preparatory_artifacts: CLOSED
max_prac_sessions_after_approval: 1
```

---

## Bloqueio atual

Não iniciar PRAC, coorte ou replay até assinatura da política v1.

---

## Sequência única pós-assinatura

```text
1. registry → measurement_policy_approval=approved
2. PRAC limitada (1 sessão)
3. export chain_complete
4. ingest
5. auditoria de consumo
6. coorte pré-registrada
7. verify/digest
8. revisão técnica
9. autorização humana replay
10. replay sequencial
11. quality_gate_directional + abstention_diagnostic
```

**Restrições:** sem rerun v9 · sem alterar prompt/adapter/registry semântico · máx 1 sessão.

---

## Critério de parada (após replay)

| Resultado coleta+replay | Ação |
|-------------------------|------|
| **Novos pares bilaterais** suficientes para gate direcional | revisão qualitativa → agregador determinístico **offline** (spec/fixtures) |
| **Zero novos pares** | encerrar estratégia de coleta atual → decisão humana sobre outcome abstinência → **não** abrir PRAC indefinidamente |

---

## Saída da fase de experimentação repetitiva

### Caminho A — pares suficientes

```text
pares suficientes
→ revisão qualitativa
→ agregador determinístico offline
```

(Agregador **executável** continua bloqueado até revisão explícita.)

### Caminho B — pares insuficientes novamente

```text
pares insuficientes
→ medir abstinência com outcomes (build-abstention-outcome-associations.py)
→ decidir formalmente se hipótese ensemble direcional é viável
```

**Não** iniciar segunda coleta sem nova decisão humana formal.

---

## Auditoria de oportunidade (próxima coleta)

Prioridade recomendada — **sem** modificar prompts:

1. **Completude / qualidade de dados** (barras completas, capacity_gate)
2. **Diversidade de instrumentos** (observação natural, não forçada)
3. **Tempo de mercado** (janela longa, períodos distintos)
4. **Regimes** (somente se observáveis sem fabricar candidatos)

Fonte: `directional-gate-stratified-view-2026-09-02-v1.json` → `next_collection_recommendation`

---

## Bloqueios mantidos

```text
PRAC antes da assinatura
reruns v9
agregador executável
paralelismo Hermes
shadow / paper / canary / promoção
```
