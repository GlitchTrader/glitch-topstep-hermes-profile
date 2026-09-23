# Proposta formal — estratégia de medição pós-Fase 5

**Status:** `PENDING_HUMAN_APPROVAL`  
**Veredito Fase 5 aceito:** Opção B  
**Gate oficial atual:** inalterado (`2/5` · `insufficient_sample`)

---

## 1. Objetivo da medição

Separar três perguntas que o gate bilateral único não responde:

1. **Direcional:** um perfil forma tese comparável melhor que o outro?
2. **Abstinência:** quando há evidência completa, a abstinência é consistente e justificada?
3. **Cobertura:** a captura produz envelopes onde tese direcional é *observável*?

---

## 2. Unidade estatística

| Estudo | Unidade |
|--------|---------|
| Gate direcional | **par bilateral** (`comparable_pair` por frame) |
| Gate abstinência | **frame espontâneo elegível** (baseline+structure, complete, não dirigido) |
| Cobertura oportunidade | **envelope** na funnel de oportunidade |
| Custo operacional | **invocação** e **sessão PRAC** |

---

## 3. Critérios de inclusão

### Gate direcional (mantido)

- ambos perfis com saída válida;
- categorias cognitivas comparáveis;
- `thesis_quality` bilateral quando aplicável.

### Gate abstinência (proposto)

- `capacity_gate_comparable: true`;
- completude **complete** (não partial);
- `scenario_tag != prac_directed_test`;
- origem espontânea (`operator_minute_frame` / `prac_soak_*`);
- **não** `missing_required_evidence`.

### Funnel oportunidade

```text
evidência completa
→ oportunidade cognitiva observável (≥1 perfil candidate/thesis_quality/held)
→ candidato unilateral ou bilateral
→ comparação bilateral possível
```

---

## 4. Critérios de exclusão

- testes dirigidos (`prac_directed_test`) do numerador de abstinência espontânea;
- frames com `insufficient_capacity`;
- artefatos com drift histórico r7 (preservados, segregados);
- frames já consumidos em bundles anteriores (inventário coorte);
- invocações `invalid` / `schema_invalid`.

---

## 5. Quantidade mínima (proposta — limiares TBD)

| Métrica | Mínimo proposto | Estado atual |
|---------|-----------------|--------------|
| Pares bilaterais direcionais | **5** | **2** |
| Frames abstinência elegíveis | **≥10** espontâneos | ~31 alinhados (muitos partial) |
| Oportunidades direcionais observadas | **≥3** | **7** dirigidos + 3 unilateral |
| Runs sem novo par antes de parada | **1** coleta limitada máx | 7 runs desde r10 |

---

## 6. Limite máximo de novas coletas

```text
MAX_PRAC_COLLECTION_ATTEMPTS_AFTER_OPTION_B = 1
```

Uma única coleta limitada (v10 contingência) **somente após** aprovação desta proposta. Se `0` pares novos → **PARAR** e exigir revisão formal do gate de abstinência ou do desenho de captura.

---

## 7. Critério de parada

```text
STOP quando:
  (a) novo replay adiciona 0 comparable_pair E
  (b) abstention_gate ainda não aprovado OU
  (c) opportunity_funnel spontaneous → bilateral = 0 em 2 coletas consecutivas
```

---

## 8. Métricas

### Primárias (promoção — bloqueadas)

| Gate | Métrica |
|------|---------|
| `quality_gate_directional` | `comparable_pair_count ≥ 5` |
| `quality_gate_abstention` | TBD pós-revisão humana |

### Diagnósticas (sempre permitidas)

- `no_edge_rate` por perfil / completude / instrumento;
- `aligned_abstention_rate`;
- `opportunity_funnel` (ver `phase-5-opportunity-audit-2026-09-02.json`);
- custo/latência por decisão;
- prudence vs no_opportunity classifier.

---

## 9. Risco de viés de seleção

| Risco | Mitigação |
|-------|-----------|
| Cherry-pick de frames com tese | coorte offline pré-registrada antes do replay |
| Inflar coorte com dirigidos | excluir `prac_directed_test` do gate abstinência |
| Repetir mesma janela MNQ/NOTHING | diversidade temporal + instrumento obrigatória na próxima coleta |
| Olhar resposta antes de selecionar | inventário + digest antes de qualquer invocação Hermes |

---

## 10. Decisão de desenho recomendada

**Combinação com gates separados:**

| Trilha | Mede | Gate |
|--------|------|------|
| 1 | Qualidade direcional | `quality_gate_directional` (existente) |
| 2 | Qualidade de abstinência | `quality_gate_abstention` (novo, aprovação pendente) |
| 3 | Cobertura condicional | diagnóstico — informa desenho PRAC, não promoção |

**Não** escolher apenas uma trilha — o projeto precisa distinguir conservadorismo de ausência de oportunidade **antes** de comparar perfis.

---

## 11. Próximos passos (pós-aprovação humana)

1. Formalizar `abstention_quality_gate.v1.json` (schema + limiares).
2. Atualizar `GATE_STATUS.md` e registry.
3. Decidir se v10 contingência é autorizada (única tentativa).
4. Implementar relatórios offline (`report-abstention-metrics.py`) — spec only até aprovação.
