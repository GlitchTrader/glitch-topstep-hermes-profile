# Diagnóstico baseline `no_edge` — r11

**Gerado:** 2026-09-02T00:37:01.989214Z
**Bundle:** `evaluation/runs/scenario-live-2026-09-01-r13-stratified-v3.json`

## Resumo

- Envelopes baseline analisados: **8**
- Todos `no_edge`: **False**
- `missing_required_evidence`: **0**
- Coerentes com baseline: **8/8**
- `no_edge` legítimo (não corrigir para inflar pares): **True**

## Histograma de motivos

- `partial_evidence:indicators,ohlc,structure`: 8

## Por envelope

### SCN-STRAT-OPERATOR-MINUTE-FRAME-24fe8a4d (`20260901T152524Z-24fe8a4d`)

- estado: `no_edge` | motivo: `partial_evidence:indicators,ohlc,structure`
- missing_required_evidence: `False`
- completeness: `{"indicators": "partial", "ohlc": "partial", "orderflow": "available", "quote": "available", "risk_context": "available", "session": "available", "structure": "partial"}`
- coerente: `True`
- tese (trecho): Mixed transition: 60m trend remains bearish while 15m is rebounding, 1m selling is recent but 5m price is elevated within its local range; wait for rejection below 29207.5 to favor short continuation 

### SCN-STRAT-OPERATOR-MINUTE-FRAME-52265102 (`20260901T154226Z-52265102`)

- estado: `no_edge` | motivo: `partial_evidence:indicators,ohlc,structure`
- missing_required_evidence: `False`
- completeness: `{"indicators": "partial", "ohlc": "partial", "orderflow": "available", "quote": "available", "risk_context": "available", "session": "available", "structure": "partial"}`
- coerente: `True`
- tese (trecho): Price is extended near the 5m range high after a strong 15m advance, while aligned short-term selling conflicts with the broader upward impulse; no bounded five-minute edge is sufficient without a cle

### SCN-STRAT-OPERATOR-MINUTE-FRAME-8b20659b (`20260901T165456Z-8b20659b`)

- estado: `candidate` | motivo: `partial_evidence:indicators,ohlc,structure`
- missing_required_evidence: `False`
- completeness: `{"indicators": "partial", "ohlc": "partial", "orderflow": "available", "quote": "available", "risk_context": "available", "session": "available", "structure": "partial"}`
- coerente: `True`
- tese (trecho): Bearish continuation has the better bounded five-minute path: price is rebounding into the 5m prior high and partial-bar high while 5m, 15m, and 60m structure remains below declining EMA/VWAP referenc

### SCN-STRAT-OPERATOR-MINUTE-FRAME-2cfca7a6 (`20260901T174044Z-2cfca7a6`)

- estado: `no_edge` | motivo: `partial_evidence:indicators,ohlc,structure`
- missing_required_evidence: `False`
- completeness: `{"indicators": "partial", "ohlc": "partial", "orderflow": "available", "quote": "available", "risk_context": "available", "session": "available", "structure": "partial"}`
- coerente: `True`
- tese (trecho): MNQ remains in a broad bearish regime, but price is near the recent 5-minute and 60-second lows after a modest bounce; immediate delta is neutral, depth is unavailable, and the current zone does not o

### SCN-STRAT-OPERATOR-MINUTE-FRAME-a71c2714 (`20260901T175947Z-a71c2714`)

- estado: `candidate` | motivo: `partial_evidence:indicators,ohlc,structure`
- missing_required_evidence: `False`
- completeness: `{"indicators": "partial", "ohlc": "partial", "orderflow": "available", "quote": "available", "risk_context": "available", "session": "available", "structure": "partial"}`
- coerente: `True`
- tese (trecho): Broader 5m, 15m, and 60m structure remains bearish with price below VWAP and falling EMAs; the immediate rebound into the 29142.75 local high is showing rejection, while a break back below 29138 favor

### SCN-STRAT-OPERATOR-MINUTE-FRAME-e1ff909a (`20260901T181807Z-e1ff909a`)

- estado: `no_edge` | motivo: `partial_evidence:indicators,ohlc,structure`
- missing_required_evidence: `False`
- completeness: `{"indicators": "partial", "ohlc": "partial", "orderflow": "available", "quote": "available", "risk_context": "available", "session": "available", "structure": "partial"}`
- coerente: `True`
- tese (trecho): MNQ is in a broader bearish regime below declining 5m, 15m, and 60m VWAP/EMA structure, but the immediate rebound from 29093 to the 29111 area has aligned 60-second buying and is pressing the partial 

### SCN-STRAT-PRAC-DIRECTED-TEST-ddd5ffb5 (`20260901T002742Z-ddd5ffb5`)

- estado: `data_quality_insufficient` | motivo: `partial_evidence:indicators,ohlc,structure`
- missing_required_evidence: `False`
- completeness: `{"indicators": "partial", "ohlc": "partial", "orderflow": "available", "quote": "available", "risk_context": "available", "session": "available", "structure": "partial"}`
- coerente: `True`
- tese (trecho): An open protected contract is reported, but the frozen envelope does not identify position direction or entry price; the position cannot be evaluated safely.

### SCN-STRAT-PRAC-DIRECTED-TEST-f5fb2cc7 (`20260901T002828Z-f5fb2cc7`)

- estado: `no_edge` | motivo: `partial_evidence:indicators,ohlc,structure`
- missing_required_evidence: `False`
- completeness: `{"indicators": "partial", "ohlc": "partial", "orderflow": "available", "quote": "available", "risk_context": "available", "session": "available", "structure": "partial"}`
- coerente: `True`
- tese (trecho): Price is rebounding from the 29497-29502.25 local support area, but the five-minute auction remains mid-range with mixed short-term momentum, neutral 60-second delta, and unreliable depth; no bounded 

## Causas raiz (top 3)

1. baseline declara ausência de edge acionável com evidência parcial (ohlc/structure)
1. frames operacionais/PRAC pós-evento raramente oferecem entrada delimitada ao baseline
1. no_edge não é missing_required_evidence — gate permite avaliação direcional
