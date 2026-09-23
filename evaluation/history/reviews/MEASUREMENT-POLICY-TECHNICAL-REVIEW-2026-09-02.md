# Revisão técnica — política de medição v1

**Data:** 2026-09-02  
**Documento:** `evaluation/MEASUREMENT-POLICY-2026-09-02-v1.md`  
**Resultado:** **APROVADO PARA ASSINATURA HUMANA** (revisão técnica offline)

---

## Checklist

| # | Item | Status |
|---|------|--------|
| 1 | Gate direcional v1 preservado (2/5) | ✓ `directional-gate-report-2026-09-02-v1.json` |
| 2 | Gate v2 estratificado sem alterar v1 | ✓ numerador v1=v2=2 |
| 3 | Abstinência `diagnostic_only` | ✓ `ABSTENTION-DIAGNOSTIC-SPEC.md` FROZEN |
| 4 | Funil oportunidade formalizado | ✓ `OPPORTUNITY-FUNNEL-REPORT-2026-09-02.md` |
| 5 | Proveniência directed/spontaneous separada | ✓ `phase-5-provenance-segmentation-audit` |
| 6 | `no_edge` não convertido em `thesis_quality` | ✓ |
| 7 | Suíte profile 534 OK | ✓ |
| 8 | Gateway `npm run check` 552 pass | ✓ |
| 9 | `next_authorized_run_id` null | ✓ registry |
| 10 | STOP_RERUNS ativo | ✓ |
| 11 | v10 não iniciado | ✓ contingência apenas |
| 12 | Máx 1 coleta pós-assinatura | ✓ política |

---

## Consistência v1 / v2

```text
directional_gate_v1.comparable_pairs.count = 2
directional_gate_v2.unique_frames = 2
  directed:    1  (r7 · prac_directed_test)
  spontaneous: 1  (r10 · reconciliation)
```

---

## Riscos residuais

| Risco | Mitigação |
|-------|-----------|
| Interpretar abstinência como qualidade | `promotion_use_allowed=false` |
| Reinflar coleta | critério de parada + máx 1 PRAC |
| Drift SHA256SUMS | regenerate após corpus enrich |

---

## Próximo passo

1. Assinatura humana em `MEASUREMENT-POLICY-2026-09-02-v1.md`
2. Atualizar registry `measurement_policy_approval: approved`
3. Atualizar `GATE_STATUS.md`
4. Decidir se única coleta limitada é autorizada (não automática)
