# Estado da suíte de testes — 2026-09-02

**Objetivo:** documentar falhas históricas corrigidas vs. expectativa legítima pós-r14/r15.

## Critério pré-captura PRAC

```text
suporte v8 implementado          ✓
→ testes v8 verdes               ✓ (test_cohort_v8_offline)
→ falhas históricas classificadas  ✓ (abaixo)
→ SHA256SUMS coerente            ✓ (regenerate 2026-09-02)
→ git diff --check               (gateway)
→ npm run check                  (gateway)
→ captura PRAC                   pendente operador
```

**Ingest v8:** somente após PRAC + export + ingest real.

## Correções aplicadas (2026-09-02)

| Teste | Causa | Resolução |
|-------|-------|-----------|
| `test_registry_not_authorized_for_r14` | r14 executado 2026-09-02 | Renomeado `test_registry_r14_executed_historical`; assert `executed_2026-09-02_Ari` |
| `test_verify_passes_on_current_repo` | pins frozen desatualizados (registry/contract) | `frozen-cohort-manifest` pins refreshed + `pin_refresh_notes` |
| `test_manifest_matches_files` | SHA256SUMS drift pós-scripts | `regenerate_sha256sums.py` |
| `test_inventory_counts` | schema v2 + cohort_version default | Passa `cohort_version="v3"` |
| `test_two_evaluation_runs_do_not_collide` | `production_lane_active` no profile real | `production_state` isolado no temp dir |

## Novos testes v8

`tests/test_cohort_v8_offline.py`:

- exclusão v6/v7
- inventário `eligible_for_v8`
- deduplicação verify
- digest repeatável
- metadata manifest v8

## Comando canônico

```powershell
cd C:\Users\arifr\Projects\glitch-topstep-hermes-profile
python -m unittest discover -s tests -p "test_*.py" -v
```

Esperado: **534 OK** (1 skipped) · SHA256SUMS 557 entries.

## Fase 5 / medição (2026-09-02)

| Item | Status |
|------|--------|
| SHA256SUMS | ✓ regenerate pós-manifest v9 |
| Suíte completa | ✓ 534 OK |
| Veredito Fase 5 | Opção B aceito |
| Próximo | aprovação humana `MEASUREMENT-STRATEGY-PROPOSAL-2026-09-02.md` |
