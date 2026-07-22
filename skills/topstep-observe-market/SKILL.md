---
name: topstep-observe-market
description: Observe the bounded Glitch Topstep decision packet and recent frame path without issuing or submitting a trade.
---

# Observe Market

Use only `CURRENT_CYCLE.decision_packet` and `CURRENT_CYCLE.recent_frames` for current market and account facts.

1. Require the current packet schema, exact snapshot hash, current quote, state-complete flag, and account alias. Numeric ProjectX identifiers are intentionally absent and must never be requested or invented.
2. Use the recent frame path to describe price direction, acceleration, spread, session range location, volatility, and state changes. Treat absent information as unknown; do not invent indicators, DOM, news, bars, or sentiment.
3. When flat, frame the next-five-minute path. When positioned, frame the next-one-minute path and the evidence that would justify HOLD versus EXIT.
4. Distinguish market evidence from account and policy evidence. `current_buffer`, `allowed_risk_usd`, entry eligibility, valid quantities, and entry window are authoritative constraints, not market signals.
5. Plans, guidance, and memory are hypotheses. Fresh authenticated gateway facts win whenever they conflict.

Pass a compact observation to risk and thesis: path, location, spread, volatility clues, directional evidence, contradictory evidence, missing evidence, and data quality. This skill never emits an intent.
