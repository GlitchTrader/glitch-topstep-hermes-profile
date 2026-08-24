---
name: topstep-setup-state
description: CURRENT/BULLISH/BEARISH/NEXT paths, trigger invalidation, and setup transitions on Topstep.
---

# topstep-setup-state

Use for per-candidate setup paths and wake trigger lifecycle. Persist triggers locally; never put trigger wire data on gateway intents.

Treat each instrument as an evolving auction. For every candidate maintain four concepts:

- **current setup** — path active at this location
- **bullish path** — long continuation/reclaim with trigger, objective, invalidation, status
- **bearish path** — short continuation/failure with the same fields
- **next transition** — what could become active next and what would disconfirm it

A microstructure break changes setup state; it does not force a reverse trade. Setup-state promotion and entry permission are separate: an accepted transition can promote a path, but it is not required for entry.

When evidence satisfies a prior frozen trigger condition, run `TRIGGER_REVIEW_V1`: classify each prior watch as HELD, FAILED, or EXPIRED in `PRIOR_TRIGGER_REVIEW` before emitting a new thesis. At most one open HELD trigger per instrument. A reclaim or retest alone remains `HELD` while the named invalidation is intact; `FAILED` requires that invalidation or a specific structural contradiction. A fired trigger does not force entry or relax entry quality.

Compare NOW with WAIT for the selected candidate. Enter when current-zone expected value is positive and invalidation survives ordinary noise. WAIT is superior only before the primary objective and only when probability improvement compensates for lost room. Acceptance, confirmation, and retest are probability evidence, not sequential prerequisites.

When evidence satisfies a prior `change_condition`, act or name genuinely new contrary evidence — do not move thresholds because price followed the forecast.
