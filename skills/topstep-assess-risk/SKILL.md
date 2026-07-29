---
name: topstep-assess-risk
description: Assess Topstep buffer, deterministic risk allowance, account state, and execution capacity from the current gateway packet.
---

# Assess Risk

Use the current packet as the sole risk authority. Incomplete or degraded evidence is information to declare in the audit—not an automatic cognitive veto before reasoning. The gateway may still reject execution on hard factual invalidity.

1. Read `data_quality.state_complete`, `account.can_trade`, quote freshness (`data_quality.issues`, `quote_age_ms`), `execution.new_exposure_technically_supported`, `execution.gateway_mode`, and `execution.gateway_mode_downgrade_reason` as factual context. State blocking reasons explicitly when they exist; do not silently forbid cognition when evidence is imperfect but still usable.
2. Treat nominal account size as a program label, not available loss capital. The meaningful risk state is the supplied liquidation floor, conservative equity, current buffer (`policy.current_buffer_usd`), deterministic allowed risk, daily risk state, and `policy.max_contracts`.
3. Choose quantity as a positive integer up to `policy.max_contracts` and `execution.maximum_additional_contracts`. The gateway computes admissibility from current account-wide exposure and policy. Never invent fallback capacity.
4. Define a structural absolute stop before choosing quantity. Check that the proposed geometry is plausible and that the chosen quantity does not conflict with the packet's allowed risk context. Glitch performs final monetary validation.
5. The current gateway supports one flat-book protected entry, HOLD, EXIT, and NOTHING. It does not yet support verified position amendments or adding to a position. When positioned, allow only HOLD or EXIT.
6. Stale quotes, incomplete state, observation `last_error`, or order-flow `last_error` reduce confidence and must be named in the audit. They do not automatically replace symmetric evaluation of `ENTER_LONG`, `ENTER_SHORT`, and `NOTHING` unless hard execution facts make new exposure impossible. Risk-reducing EXIT remains preferable when current ownership is unambiguous.
7. Payout milestones and winning-day thresholds may change the value of preserving the account, but they never force activity.

Return a compact assessment: allowed actions, feasible quantity ceiling, current exposure, real buffer, deterministic risk allowance, factual constraints, and declared uncertainties.
