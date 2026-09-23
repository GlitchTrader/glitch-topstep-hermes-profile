# Relatório formal — funil de oportunidade cognitiva

**Versão:** `2026-09-02-v1`  
**JSON:** `evaluation/runs/opportunity-funnel-report-2026-09-02-v1.json`  
**Runs:** r7, r10, r11, r12-v2, r13-v3, r14, r15, r16, r17

---

## Funil

```text
envelope completo (capacity + evidência mínima)
    ↓
oportunidade direcional observável (≥1 perfil candidate/thesis_quality/held)
    ↓
candidato bilateral OU unilateral
    ↓
abstinência (no_edge alinhado ou divergente)
    ↓
outcome posterior (futuro — não medido nesta fase)
```

`outcome posterior` (PnL, decisão live correta) **não** faz parte deste relatório — requer evidência futura.

---

## Classificação de outcomes (frame-level)

| Outcome | Significado | Count |
|---------|-------------|-------|
| `no_observable_edge_bilateral_abstention` | não havia edge observável — ambos `no_edge` | **31** |
| `abstained_with_complete_evidence` | havia evidência completa, perfis abstiveram | *subconjunto de bilateral* |
| `abstained_with_partial_evidence` | evidência parcial, abstinência | *subconjunto* |
| `insufficient_data` | não havia dados suficientes (capacity) | **6** |
| `profile_presented_candidate` | perfil apresentou candidato (unilateral) | **6** |
| `directed_bilateral_thesis` | tese bilateral em teste **dirigido** | **2** |
| `directed_unilateral_or_divergence` | sinal em envelope dirigido sem par | variável |

Fonte: `opportunity-funnel-report-2026-09-02-v1.json`

---

## Distinções obrigatórias

### “Não havia edge observável”

- Ambos perfis `no_edge`
- Envelope espontâneo, capacity OK
- Nenhum `candidate`/`thesis_quality` em qualquer lado

### “Havia evidência, mas o perfil se absteve”

- `completeness_tier` = `complete` ou `partial`
- `capacity_gate_comparable: true`
- `no_edge` em ≥1 perfil onde `directional_opportunity` poderia ser esperada (heurística offline)

### “Não havia dados suficientes”

- `capacity_gate_comparable: false`
- ou `missing_required_evidence`
- **excluir** do numerador de abstinência espontânea

### “O perfil apresentou candidato”

- `candidate` | `thesis_quality` | `held` em um perfil
- `comparable_pair: false` (unilateral)

### “A tese foi dirigida pelo teste”

- `scenario_tag = prac_directed_test`
- **não** misturar com espontâneo na conclusão de qualidade

---

## Leitura consolidada (r7–r17)

| Métrica | Valor |
|---------|-------|
| Frames espontâneos | **40** |
| Abstinência bilateral espontânea | **31** |
| Candidato unilateral espontâneo | **6** |
| Pares bilaterais válidos | **2** (1 **dirigido** r7 · 1 **espontâneo** r10/reconciliation) |
| Pares bilaterais espontâneos pós-r10 | **0** |

**Conclusão:** oportunidade direcional observável concentra-se em envelopes **dirigidos**. Espontâneos recentes produzem abstinência alinhada, não pares `thesis_quality`.

---

## Uso

- Informar desenho PRAC e coorte — **não** promoção
- Alimentar `abstention_diagnostic` e `directional_gate_v2`
- Nova versão (`-v2`) se runs ou classificador mudarem
