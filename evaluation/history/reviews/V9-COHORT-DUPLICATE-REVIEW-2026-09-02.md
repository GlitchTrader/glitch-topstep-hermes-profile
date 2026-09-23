# Revisão de duplicatas — coorte v9

**Data:** 2026-09-02  
**Coorte:** `v9-pre-registered` · 4 envelopes

---

## Veredito: **PASS**

| # | Check | Resultado |
|---|-------|-----------|
| 1 | `packet_id` únicos na fila v9 | **4/4** distintos |
| 2 | `snapshot_hash` (envelope) únicos | **4/4** distintos |
| 3 | `frame_id` únicos | **4/4** distintos |
| 4 | Overlap com coortes v2–v8 | **nenhum** (51 IDs em `excluded_frame_ids`) |
| 5 | Overlap com bundles `scenario-live-*` | **nenhum** |
| 6 | `already_consumed` na auditoria | **0** |

**Evidência:** `evaluation/runs/stratified-cohort-manifest-v9-2026-09-02.json` · `evaluation/runs/prac-frame-consumption-audit-PRAC-SOAK-2026-09-02-v9.json`

Frames **excluídos** da coorte (não duplicatas — capacidade):

- `20260902T181554Z-79fa9dae` · `insufficient_capacity`
- `20260902T182551Z-54dde640` · `insufficient_capacity`
