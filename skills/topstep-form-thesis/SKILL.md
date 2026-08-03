---
name: topstep-form-thesis
description: Form a falsifiable short-horizon market hypothesis and structural invalidation from bounded gateway evidence.
---

# Form Thesis

Judge bull, bear, and flat cases from current observable evidence. Aggressive and conservative cases are perspectives, not separate strategies.

## Regime labels

State one explicit regime label from packet evidence:

- `TREND_UP` — aligned higher-timeframe location and slope support continuation higher.
- `TREND_DOWN` — aligned higher-timeframe location and slope support continuation lower.
- `CHOP` — overlapping structure, conflicting slopes, or mid-range location without directional edge.
- `LOW_LIQUIDITY` — thin tape or sparse order-flow windows; reduce conviction and prefer smaller size or NOTHING.
- `DATA_DEGRADED` — incomplete state, `data_quality.issues`, observation or order-flow `last_error`, or stale quotes.

## HTF hierarchy

Prefer the 60m timeframe for regime: `range_position_20` extremes (high or low in the 20-bar range) plus aligned `ema_20_slope_bps` and `ema_50_slope_bps`. Use 5m and 1m for timing and invalidation, not to override a clear 60m conflict without new evidence.

## Confidence for NOTHING

- Use confidence **0.95+** for NOTHING only when data is invalid or execution facts forbid action (`DATA_DEGRADED`, clear blocking `data_quality.issues`, or `new_exposure_technically_supported=false` when flat).
- Use **0.70–0.85** for NOTHING when structure conflicts, chop dominates, or evidence is symmetric but data is usable.
- Do not inflate NOTHING confidence merely because no trade feels comfortable.

## Price zones

Do not cite hardcoded price bands (e.g. "28010–28015") unless `reference_levels` or equivalent structural levels are present in the packet. Use supplied features, session range, and observation features instead.

## Thesis rules

1. When flat, state the most likely next-five-minute path and its concrete invalidation. When positioned, state the most likely next-one-minute path and choose among `HOLD`, `MOVE_STOP`, `MOVE_TP`, partial or full `EXIT`, and scale-in only when `execution.supported_actions` includes the matching `ENTER_*` action.
2. Consider continuation, pullback, breakout, mean reversion, scalp, and transition hypotheses without requiring a named archetype.
3. Define invalidation before reward. Place the absolute stop beyond relevant structure and normal noise, not at an arbitrary offset or cosmetic reward/risk point.
4. Select a target reachable within the stated horizon and regime. If structural risk is too large, choose a smaller quantity or NOTHING.
5. Do not force activity because a payout threshold, daily target, or prior plan exists. Preserve account survival, rule compliance, and evidence quality.
6. After a stop, require materially changed price or evidence before re-entry. Repeating the same thesis near the same level is churn.
7. HOLD is not passive certainty. If the prior `change_condition` has occurred, choose `MOVE_STOP`, `MOVE_TP`, `EXIT`, or explain genuinely new evidence that invalidates the old trigger.
8. `HOLD` and `NOTHING` carry the same burden of proof as every other action. When current evidence satisfies the prior review's `change_condition`, choose the newly supported action or identify genuinely new contrary evidence; price following the forecast is not sufficient reason to move the threshold.
9. Treat a flat `NOTHING` as active observation: preserve the developing path, favorable participation condition, and invalidation in `decisive_evidence`, `disconfirming_evidence`, and `change_condition`. Later learning may classify the matured decision, but must never invent counterfactual fills or PnL.

Choose `ENTER_LONG`, `ENTER_SHORT`, `HOLD`, `MOVE_STOP`, `MOVE_TP`, `EXIT`, or `NOTHING`. Pass only a compact factual audit; never reveal private chain-of-thought.
