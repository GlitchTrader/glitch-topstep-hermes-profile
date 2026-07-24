---
name: topstep-observe-market
description: Observe the bounded Glitch Topstep decision packet and recent frame path without issuing or submitting a trade.
---

# Observe Market

Use `CURRENT_CYCLE.decision_packet` and `CURRENT_CYCLE.recent_frames` for current market and account facts.

1. Require packet schema v2 fields: `market.bars_1m`, `market.features`, `market.levels`, `market.correlation`, `position_state`, `protection`, `reconciliation`, and `policy`.
2. Describe structure from supplied bars and levels — session range, VWAP distance, swing highs/lows, `features.regime_1m`, `features.relative_volume`, and ES/MNQ correlation when present.
3. Use recent frames for continuity, not to reinvent missing bars. Treat absent realtime tape/depth as unknown.
4. When flat, frame the next decision window using `execution.setup_candidates` as admissible geometry hints. When positioned, frame HOLD vs EXIT vs MOVE_STOP using `protection` and `position_state`.
5. Distinguish market evidence from policy evidence. `policy.daily_loss_remaining_usd`, `policy.entry_cooldown_after_losses`, and `reconciliation.state_trusted` are hard constraints.

Pass compact observation: regime, location in range, structure, correlation, data quality, and blocking reasons. Never emit an intent.
