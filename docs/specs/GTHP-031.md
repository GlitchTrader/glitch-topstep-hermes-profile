# GTHP-031 — Calibration metrics and NOTHING accountability (#75)

**Priority:** P3 (learning calibration)  
**Status:** done  
**Issue:** #75  
**Depends on:** GTHP-028, GTHP-029, #74 structural packet fields

## Problem

Flat `NOTHING` abstentions lacked deterministic counterfactual accounting, weekly aggregates for schema validity and late entries, and explicit `change_condition` follow-up. Learning loops could not compare declared participation conditions with observed paths without inventing fills or PnL.

## Scope

### `scripts/calibration_metrics.py`

- [x] `compute_session_metrics(state_root)` → `schema_validity_rate`, `late_entry_pct`, `missed_participation_pct`
- [x] Schema invalidity from receipts with HTTP 422 or `intent_schema_invalid`
- [x] Missed participation from `decision-episodes.jsonl` classifications
- [x] Late entry from `ENTER_*` decisions with `range_position_20` > 0.85 or < 0.15

### `scripts/parity.py`

- [x] `compute_nothing_counterfactual(decision, forward_observations)` → MFE/MAE ticks + classification
- [x] `review_change_condition(prior_decision, next_frame)` → `unmet|met_with_reassessment|met_without_reassessment|unknown`

### `scripts/run-topstep-learning.py`

- [x] Enrich `collect_decision_episodes` with counterfactual fields and `change_condition_review`
- [x] Inject `calibration_metrics` into weekly `invoke_loop` evidence

### Skills / docs

- [x] `topstep-assess-risk` — `risk_per_contract` guidance formula
- [x] `topstep-learning-loop` — setup taxonomy for `missed_directional_participation`

## Non-goals

- Worker gates on metrics or classifications
- Automatic entry pressure from missed participation rate
- Gateway changes (receipt shape already sufficient)

## Acceptance

- Unittest coverage in `tests/test_calibration_metrics.py`, extended `tests/test_learning.py`, `tests/test_regime.py` (TRANSITION), `tests/test_packet_model.py` (new fields)
- Weekly loop evidence includes bounded calibration metrics object
- Decision episodes persist counterfactual ticks without inventing fills

## Related

- Issue #74 (structural evidence + `decision_scores`)
- GTHP-028 cognition delta audit
