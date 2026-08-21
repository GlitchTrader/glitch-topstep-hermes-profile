---
name: topstep-setup-state
description: CURRENT/BULLISH/BEARISH/NEXT paths, trigger invalidation, and setup transitions on Topstep.
---

# topstep-setup-state

Use for per-candidate setup paths and wake trigger lifecycle. Persist triggers locally; never put trigger wire data on gateway intents.

When evidence satisfies a prior frozen trigger condition, run `TRIGGER_REVIEW_V1`: classify each prior watch as HELD, FAILED, or EXPIRED in `PRIOR_TRIGGER_REVIEW` before emitting a new thesis. At most one open HELD trigger per instrument.

When evidence satisfies a prior `change_condition`, act or name genuinely new contrary evidence — do not move thresholds because price followed the forecast.
