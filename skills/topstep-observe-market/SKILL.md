---
name: topstep-observe-market
description: Observe the bounded Glitch Topstep decision packet and recent frame path without issuing or submitting a trade.
---

# Observe Market

Use only `CURRENT_CYCLE.decision_packet` and `CURRENT_CYCLE.recent_frames` for current market and account facts.

1. Require the current packet schema, exact snapshot hash, current quote, `data_quality.state_complete`, and account alias. Numeric ProjectX identifiers are intentionally absent and must never be requested or invented.
2. Use `market_observation` timeframes (1m, 5m, 15m, 60m) and the recent frame path to describe price direction, acceleration, spread, session range location, volatility, and state changes. Use `order_flow` rolling windows for tape context. Treat absent information as unknown; do not invent indicators, DOM, news, bars, or sentiment.
3. When flat, frame the next-five-minute path. When positioned, frame the next-one-minute path and the evidence that would justify HOLD versus EXIT.
4. Distinguish market evidence from account and policy evidence. `policy.current_buffer_usd`, `execution.new_exposure_technically_supported`, `execution.maximum_additional_contracts`, and `policy.max_contracts` are authoritative constraints, not market signals.
5. Data health: `market_stream_state=connected` is acceptable when `data_quality.state_complete=true` and `data_quality.issues` is empty. Do not treat connected market stream as unhealthy by default. Quote freshness uses `data_quality.quote_age_ms` together with `data_quality.issues` (e.g. `quote_stale`); do not apply a hardcoded millisecond threshold unless the packet flags staleness.
6. Plans, guidance, and memory are hypotheses. Fresh authenticated gateway facts win whenever they conflict.

Pass a compact observation to risk and thesis: path, location, spread, volatility clues, directional evidence, contradictory evidence, missing evidence, inferred regime label (TREND_UP, TREND_DOWN, CHOP, LOW_LIQUIDITY, DATA_DEGRADED), and data quality. This skill never emits an intent.
