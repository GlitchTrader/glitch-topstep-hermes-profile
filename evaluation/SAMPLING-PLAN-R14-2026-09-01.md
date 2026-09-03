# Plano de amostragem r14 — 2026-09-01

**Status:** `approved_offline_pre_prac_export`  
**Pré-requisito:** novo soak PRAC com `export-prac-evidence-chain.py` + `validate-prac-evidence-chain.py` exit 0  
**Gate formal:** permanece **2/5** até novos pares bilaterais independentes

## Objetivo

Expandir diversidade de corpus e obter até **3 pares comparáveis adicionais** (meta gate: 5/5), sem reruns da coorte MNQ/operator/PRAC-directed esgotada (r7–r13).

## Bloqueador atual

| Dimensão | Estado |
|----------|--------|
| Corpus enriched unused (`complete`) | **0** frames |
| Tags esgotadas | todas no pool MNQ atual |
| Export PRAC cadeia completa | **0** sessões (só fixtures gateway) |
| Instrumentos no corpus | **MNQ** apenas |

**Decisão:** parar reruns; próximo input = **captura PRAC**, não Hermes.

## Cenários desejados (r14 coorte)

| Prioridade | `scenario_tag` | Mín. envelopes | Regime alvo | Origem |
|------------|----------------|----------------|-------------|--------|
| P0 | `reconciliation` | 2 | TRANSITION / CHOP | novo PRAC soak |
| P0 | `restart` | 2 | TREND_UP / CHOP | novo PRAC soak |
| P0 | `timeout` | 1 | TREND_UP | novo PRAC soak |
| P1 | `preflight` | 1 | TREND_DOWN | novo PRAC soak |
| P2 | `operator_minute_frame` | 2 | variado | operator capture pós-export |
| reserva | `prac_directed_test` | ≤1 | — | só se cadeia completa + snapshot único |

**Instrumentos alvo:** MNQ (baseline) + MES ou MGC se gateway/captura permitir no soak.

## Tamanho da coorte r14

| Parâmetro | Valor |
|-----------|-------|
| Envelopes alvo | **8–10** |
| Perfis | `baseline-current`, `structure` (sequencial) |
| Invocações máximas | 20 (10×2) |
| Orçamento custo referência | ≤ $0.25/sessão (r12–r13: ~$0.18–0.20 / 16–18 inv) |

## Critérios de independência (inalterados)

1. `snapshot_hash` único por envelope selecionado
2. `scenario_tag` distinto **ou** `session`/`origin` distinto entre pares contados
3. Excluir todos os frames r7–r13 e coortes v2/v3
4. `capacity_gate_validated: true` offline antes de Hermes
5. Cadeia PRAC completa para frames `prac_*` (packet→decisão→intent→receipt)

## Política de inclusão / exclusão

### Incluir

- Packet v2 com `market.snapshot_hash` verificável
- Evidência `quality: complete` no manifest enriched
- Tags P0–P1 com decisão espontânea ou teste dirigido **com** cadeia completa
- Frames com `allows_directional_evaluation: true` para ambos perfis

### Excluir

- Execução dirigida sem `intent_id` + `receipt` correspondente
- Health/metrics-only captures (sem packet cognitivo)
- Frames já usados em qualquer run canônico
- Seleção pós-observação de `thesis_quality` (viés)
- Conversão artificial de `no_edge` em `candidate`

## Sequência r14 (autorização → replay)

```text
novo soak/export PRAC
  → validate-prac-evidence-chain.py (exit 0)
  → build-enriched-corpus.py ingest
  → inventory-unused-cohort-frames.py
  → build-stratified-cohort.py --cohort-version v4
  → verify-stratified-cohort.py (sem --skip-validation)
  → digest + registry pre_register
  → autorização humana explícita
  → scenario-live-2026-09-01-r14-stratified-v4
  → QC por envelope
  → proveniência + re-gate
```

## Revisão qualitativa (sem promoção)

Divergências `baseline candidate` vs `structure no_edge` (r13) podem ser documentadas em  
`evaluation/reviews/DIVERGENCE-QUALITATIVE-R7-R13-2026-09-01.md` — **não** contam para gate nem promoção.

## Congelado

prompt · adapter · registry · agregador executável · paralelismo · shadow · promoção
