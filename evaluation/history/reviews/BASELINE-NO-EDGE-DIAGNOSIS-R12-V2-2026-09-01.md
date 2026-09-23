# Diagnóstico baseline `no_edge` — r11

**Gerado:** 2026-09-02T00:29:19.923222Z
**Bundle:** `evaluation/runs/scenario-live-2026-09-01-r12-stratified-v2.json`

## Resumo

- Envelopes baseline analisados: **9**
- Todos `no_edge`: **False**
- `missing_required_evidence`: **0**
- Coerentes com baseline: **9/9**
- `no_edge` legítimo (não corrigir para inflar pares): **True**

## Histograma de motivos

- `partial_evidence:indicators,ohlc,structure`: 9

## Por envelope

### SCN-STRAT-PRAC-DIRECTED-TEST-cbb5cee1 (`20260831T233830Z-cbb5cee1`)

- estado: `no_edge` | motivo: `partial_evidence:indicators,ohlc,structure`
- missing_required_evidence: `False`
- completeness: `{"indicators": "partial", "ohlc": "partial", "orderflow": "available", "quote": "available", "risk_context": "available", "session": "available", "structure": "partial"}`
- coerente: `True`
- tese (trecho): The account is already long or short three MNQ contracts, but the frozen packet does not identify position direction or advertise supported management actions; protection is pending because the stop c

### SCN-STRAT-PRAC-DIRECTED-TEST-a9c3eb80 (`20260831T234106Z-a9c3eb80`)

- estado: `data_quality_insufficient` | motivo: `partial_evidence:indicators,ohlc,structure`
- missing_required_evidence: `False`
- completeness: `{"indicators": "partial", "ohlc": "partial", "orderflow": "available", "quote": "available", "risk_context": "available", "session": "available", "structure": "partial"}`
- coerente: `True`
- tese (trecho): An open MNQ position of three contracts is present, but its direction and executed entry are not supplied; protection is pending with neither stop nor target observed, so no direction-specific candida

### SCN-STRAT-PRAC-DIRECTED-TEST-818c9e79 (`20260901T002738Z-818c9e79`)

- estado: `no_edge` | motivo: `partial_evidence:indicators,ohlc,structure`
- missing_required_evidence: `False`
- completeness: `{"indicators": "partial", "ohlc": "partial", "orderflow": "available", "quote": "available", "risk_context": "available", "session": "available", "structure": "partial"}`
- coerente: `True`
- tese (trecho): No bounded positive-expectancy entry at the current zone: higher-timeframe structure remains bullish, but price is rejecting the 29515–29518.75 area while the incomplete 1-minute bar shows a sharp rol

### SCN-STRAT-RECONCILIATION-5e80e1ac (`20260901T002738Z-5e80e1ac`)

- estado: `no_edge` | motivo: `partial_evidence:indicators,ohlc,structure`
- missing_required_evidence: `False`
- completeness: `{"indicators": "partial", "ohlc": "partial", "orderflow": "available", "quote": "available", "risk_context": "available", "session": "available", "structure": "partial"}`
- coerente: `True`
- tese (trecho): MNQ is in a broader upward regime but the immediate move is progressing into exhaustion: price rejected the 29514.5–29515.0 local high, 15-second flow turned negative, and current location is mid-to-u

### SCN-STRAT-RECONCILIATION-9866a0f9 (`20260901T020441Z-9866a0f9`)

- estado: `no_edge` | motivo: `partial_evidence:indicators,ohlc,structure`
- missing_required_evidence: `False`
- completeness: `{"indicators": "partial", "ohlc": "partial", "orderflow": "available", "quote": "available", "risk_context": "available", "session": "available", "structure": "partial"}`
- coerente: `True`
- tese (trecho): MNQ is mid-range with mixed short-term structure, weak participation, and neutral-to-conflicting tape; no bounded five-minute directional edge is established.

### SCN-STRAT-RESTART-8c371231 (`20260831T235211Z-8c371231`)

- estado: `expired` | motivo: `partial_evidence:indicators,ohlc,structure`
- missing_required_evidence: `False`
- completeness: `{"indicators": "partial", "ohlc": "partial", "orderflow": "available", "quote": "available", "risk_context": "available", "session": "available", "structure": "partial"}`
- coerente: `True`
- tese (trecho): The frozen envelope expired at 2026-08-31T23:57:11.587Z, so no actionable trade candidate can be evaluated from it.

### SCN-STRAT-RESTART-fd331ad4 (`20260831T235620Z-fd331ad4`)

- estado: `no_edge` | motivo: `partial_evidence:indicators,ohlc,structure`
- missing_required_evidence: `False`
- completeness: `{"indicators": "partial", "ohlc": "partial", "orderflow": "available", "quote": "available", "risk_context": "available", "session": "available", "structure": "partial"}`
- coerente: `True`
- tese (trecho): MNQ is mid-range with short-term bearish pressure but conflicting higher-timeframe bullish structure; neither long nor short offers bounded positive expectancy after structural protection and spread.

### SCN-STRAT-OPERATOR-MINUTE-FRAME-a49c317a (`20260901T143311Z-a49c317a`)

- estado: `no_edge` | motivo: `partial_evidence:indicators,ohlc,structure`
- missing_required_evidence: `False`
- completeness: `{"indicators": "partial", "ohlc": "partial", "orderflow": "available", "quote": "available", "risk_context": "available", "session": "available", "structure": "partial"}`
- coerente: `True`
- tese (trecho): Existing exposure is protected, but the long-position entry basis is unavailable; current price is near the 5-minute upper range while 60-minute structure remains bearish and 60-second delta conflicts

### SCN-STRAT-OPERATOR-MINUTE-FRAME-c776a976 (`20260901T145322Z-c776a976`)

- estado: `no_edge` | motivo: `partial_evidence:indicators,ohlc,structure`
- missing_required_evidence: `False`
- completeness: `{"indicators": "partial", "ohlc": "partial", "orderflow": "available", "quote": "available", "risk_context": "available", "session": "available", "structure": "partial"}`
- coerente: `True`
- tese (trecho): MNQ is in a transitional, volatile auction: the 5m rejection and 300s negative delta favor downside continuation, while the 15s bounce and strong 60m recovery support a competing rebound; current pric

## Causas raiz (top 3)

1. baseline declara ausência de edge acionável com evidência parcial (ohlc/structure)
1. frames operacionais/PRAC pós-evento raramente oferecem entrada delimitada ao baseline
1. no_edge não é missing_required_evidence — gate permite avaliação direcional
