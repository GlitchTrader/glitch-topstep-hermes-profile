# Inventário fontes PRAC — r14 (2026-09-01)

**Gerado:** 2026-09-02T01:01:24.955415Z

## Resumo

- Sessões PRAC auditadas: **3**
- Exports cadeia completa: **0**
- Frames corpus não usados (`complete`): **8**
- Bloqueador r14: `needs_new_prac_soak_with_export`

## Corpus enriquecido

- Tags esgotadas (0 unused complete): `['reconciliation', 'timeout', 'preflight']`
- Tags prioritárias ausentes no unused pool: `['reconciliation', 'timeout']`

## Sessões PRAC

- `PRAC-SOAK-2026-08-21` — chain=`none` raw=0 export=False
- `PRAC-SOAK-2026-08-25-post-audit-wave` — chain=`none` raw=0 export=False
- `PRAC-SOAK-2026-08-31` — chain=`intent_receipt_partial` raw=15 export=False

## Próximo soak

Priorizar capturas com cadeia completa:

```text
packet → snapshot_hash → decisão → intent_id → receipt
```

Ver `glitch-topstep/docs/evidence/PRAC-NEXT-SESSION-CHECKLIST.md`.
