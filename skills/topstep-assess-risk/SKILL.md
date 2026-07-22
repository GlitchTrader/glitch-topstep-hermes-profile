---
name: topstep-assess-risk
description: Assess Topstep buffer, deterministic risk allowance, account state, and valid quantities from the current gateway packet.
---

# Assess Risk

Use the current packet as the sole risk authority.

1. Confirm `state_complete=true`, `can_trade=true`, current quote freshness, correct account alias, correct instrument, and `entry_window_open=true` before considering new exposure.
2. Treat nominal account size as a program label, not available loss capital. The meaningful risk state is the supplied liquidation floor, conservative equity, current buffer, deterministic allowed risk, daily risk state, and current contract ceiling.
3. Choose quantity only from `execution.valid_entry_quantities`. The gateway computes admissibility from current account-wide exposure and policy. Never invent fallback capacity.
4. Define a structural absolute stop before choosing quantity. Check that the proposed geometry is plausible and that the chosen supplied quantity does not conflict with the packet's allowed risk context. Glitch performs final monetary validation.
5. The current gateway supports one flat-book protected entry, HOLD, EXIT, and NOTHING. It does not yet support verified position amendments or adding to a position. When positioned, allow only HOLD or EXIT.
6. Any stale, incomplete, inconsistent, disconnected, or ambiguous state forbids new exposure. Risk-reducing EXIT remains preferable when current ownership is unambiguous.
7. Payout milestones and winning-day thresholds may change the value of preserving the account, but they never force activity.

Return a compact assessment: allowed actions, valid quantities, current exposure, real buffer, deterministic risk allowance, factual constraints, and blocking reasons.
