# Pré-registro coorte v10 — contingência pós Fase 5

**Data:** 2026-09-02  
**Status:** `PRE_REGISTERED_OFFLINE` · **aguarda decisão humana**  
**Veredito Fase 5:** Opção B — **não** executar sequência abaixo sem override explícito

---

## Objetivo (se autorizado)

Última coleta limitada com critérios Opção A antes de revisão formal do gate — **não** repetir padrão v9 (janela curta, tag única, MNQ/NOTHING).

---

## Critérios de captura

| Critério | Meta v10 |
|----------|----------|
| Janela | ≥60 min · ≥2 períodos UTC |
| Instrumentos | observação natural; ≥2 no universo se disponível |
| Cenários | ≥3 tags distintas quando espontâneas |
| Espontâneos elegíveis | ≥3 pós-ingest |
| Exclusão | coortes v2–v9 · frames já em bundles `scenario-live-*` |

---

## Sequência offline (pronta, não executada)

```powershell
# Após PRAC com chain_complete
python scripts/run-prac-corpus-ingest.ps1   # wrapper profile
python scripts/audit-prac-frame-consumption.py --session PRAC-SOAK-2026-09-02-v10 --output evaluation/runs/prac-frame-consumption-audit-PRAC-SOAK-2026-09-02-v10.json
python scripts/inventory-unused-cohort-frames.py --cohort-version v10 --output evaluation/runs/unused-cohort-frame-inventory-v10-2026-09-02.json
python scripts/build-stratified-cohort.py --cohort-version v10 --output-manifest evaluation/runs/stratified-cohort-manifest-v10-2026-09-02.json
python scripts/verify-stratified-cohort.py --manifest evaluation/runs/stratified-cohort-manifest-v10-2026-09-02.json --scenarios evaluation/stratified_scenarios.v10.json
```

**Digest proposto:** `evaluation/runs/stratified-cohort-digest-v10-2026-09-02.json` (gerar após build)

---

## Replay proposto (não autorizado)

| Campo | Valor |
|-------|-------|
| Run ID proposto | `scenario-live-2026-09-XX-r18-v10` |
| `next_authorized_run_id` | **null** até assinatura humana |
| Critério de parada | 0 pares novos → decisão formal abstinência |

---

## Bloqueios

- Repetir v9 · agregador · paralelismo · shadow · promoção
- Seleção de frames por olhar resposta dos perfis

---

## Referências

- `evaluation/reviews/PHASE-5-SAMPLE-ADEQUACY-REVIEW-2026-09-02.md`
- `evaluation/reviews/V10-PRAC-SESSION-OPERATOR-CHECKLIST-2026-09-02.md`
