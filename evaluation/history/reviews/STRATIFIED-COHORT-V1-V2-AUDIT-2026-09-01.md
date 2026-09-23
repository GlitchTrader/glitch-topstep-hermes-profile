# Auditoria coorte v1 (r12 executada) vs v2 (manifest)

**Veredito:** `rerun_required_v2`
**Idênticos (arquivos/hashes/timestamps):** `False`
**Reutilizável histórico:** `True`
**Reutilizável canônico:** `False`

- Somente v1: `['20260901T135732Z-d3e2d816', '20260901T141348Z-65a590aa']`
- Somente v2: `['20260901T143311Z-a49c317a', '20260901T145322Z-c776a976']`

## Classificação r12

| Dimensão | Valor |
|----------|-------|
| provenance_integrity | PASS |
| protocol_conformance | CONDITIONAL |
| promotion_eligible | NO |

**Ação:** rerodar coleta com manifest v2 validado (sem `--skip-validation`).
