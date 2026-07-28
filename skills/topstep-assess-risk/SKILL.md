---
name: topstep-assess-risk
description: Assess Topstep buffer, deterministic risk allowance, account state, and execution capacity from the current gateway packet.
---

# Assess Risk

Use the current packet as the sole risk authority.

1. Confirm `data_quality.state_complete=true`, `account.can_trade=true`, fresh quotes (`data_quality.issues` empty and no `quote_stale`), correct account alias, correct instrument, and `execution.new_exposure_technically_supported=true` before considering new exposure. Read `execution.gateway_mode` and `execution.gateway_mode_downgrade_reason` as factual execution context, not thesis permission.
2. Treat nominal account size as a program label, not available loss capital. The meaningful risk state is the supplied liquidation floor, conservative equity, current buffer (`policy.current_buffer_usd`), deterministic allowed risk, daily risk state, and `policy.max_contracts`.
3. Choose quantity as a positive integer up to `policy.max_contracts` and `execution.maximum_additional_contracts`. The gateway computes admissibility from current account-wide exposure and policy. Never invent fallback capacity. (`valid_entry_quantities` is not present in current gateway packets.)
4. Define a structural absolute stop before choosing quantity. Check that the proposed geometry is plausible and that the chosen quantity does not conflict with the packet's allowed risk context. Glitch performs final monetary validation.
5. The current gateway supports one flat-book protected entry, HOLD, EXIT, and NOTHING. It does not yet support verified position amendments or adding to a position. When positioned, allow only HOLD or EXIT.
6. Any stale, incomplete, inconsistent, or ambiguous state (`data_quality.issues`, observation `last_error`, order-flow `last_error`) forbids new exposure. Risk-reducing EXIT remains preferable when current ownership is unambiguous. `market_stream_state=connected` with `state_complete=true` and empty `issues` is healthy even if other streams are reconnecting.
7. Payout milestones and winning-day thresholds may change the value of preserving the account, but they never force activity.

Return a compact assessment: allowed actions, feasible quantity ceiling, current exposure, real buffer, deterministic risk allowance, factual constraints, and blocking reasons.
