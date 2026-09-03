# Proveniência — gates direcionais v1 e v2

**Data:** 2026-09-02  
**Regra:** não misturar pares dirigidos e espontâneos em conclusão de qualidade única.

---

## Duas visões

| Visão | Artefato | Uso |
|-------|----------|-----|
| `directional_gate_v1` | `evaluation/runs/directional-gate-report-2026-09-02-v1.json` | numerador histórico **2/5** — **imutável** |
| `directional_gate_v2` | `evaluation/runs/directional-gate-report-2026-09-02-v2.json` | estratificação por origem |

---

## Estratificação v2 (53 frames r7–r17)

| Estrato | Count | Notas |
|---------|-------|-------|
| Espontâneo | 40 | operator_minute_frame / prac_soak |
| Dirigido | 7 | prac_directed_test |
| Capacidade insuficiente | 6 | excluir de abstinência espontânea |
| `no_edge` bilateral | 31 | abstinência alinhada |
| Candidato unilateral | 6 | sem par bilateral |
| Pares comparáveis | **2** | **1 dirigido** · **1 espontâneo** (reconciliation) |

---

## Segregação de risco

| Check | Resultado |
|-------|-----------|
| Drift histórico r7 | **3** artefatos preservados (cohort audit) |
| Directed + spontaneous no mesmo numerador agregado legado | **sim** (v1) — v2 corrige interpretação |
| Frames consumidos reutilizados | inventário coorte impede em novas coortes |
| NOTHING / lock operacional | documentado em PRAC v8/v9 — não misturar com falta de capacidade |

**Contaminação:** baixa para integridade de replay · alta para interpretação do gate legado — mitigada por v2.

---

## Abstinência paralela

`abstention_diagnostic` usa os mesmos frames com filtros de elegibilidade — ver `ABSTENTION-DIAGNOSTIC-SPEC.md`.

Não alterar `directional_gate_v1` ao publicar relatórios de abstinência.
