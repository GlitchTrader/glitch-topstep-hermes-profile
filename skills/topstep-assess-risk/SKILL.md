---
name: topstep-assess-risk
description: Assess Topstep buffer, deterministic risk allowance, account state, and valid quantities from the current gateway packet.
---

# Assess Risk

Use the current packet as the sole risk authority.

1. Confirm `reconciliation.state_trusted=true`, `protection.stop_confirmed` when positioned, `can_trade=true`, and fresh quote before new exposure.
2. Use `policy.current_buffer`, `policy.allowed_risk_usd`, `policy.daily_loss_remaining_usd`, and `policy.consecutive_losses`. If `policy.entry_cooldown_after_losses=true`, forbid new entries.
3. Choose quantity only from `execution.valid_entry_quantities`. Prefer `execution.setup_candidates` for structural stop/target geometry that already fits allowed risk.
4. When positioned, allow HOLD, EXIT, and MOVE_STOP only when `execution.move_stop_available=true`. MOVE_STOP must tighten the existing stop only.
5. Any stale, untrusted, or ambiguous reconciliation state forbids new exposure. Risk-reducing EXIT remains valid when ownership is clear.

Return allowed actions, valid quantities, setup candidates, buffer, daily risk remaining, and blocking reasons.
