# GTHP-TRIGGER-02 — typed trigger review (Phase B)

Connects frozen comparison triggers to accountable review cycles without duplicating full cognition every minute.

## Invocation order (flat)

1. `condition_change` when a frozen HELD condition is satisfied (wake monitor or in-cycle evaluation)
2. `held_rescan` on the next flat slot after a NOTHING decision that left active HELD triggers
3. `scheduled` full cognition on flat cadence when no pending review is due

## TRIGGER_REVIEW_V1

- Applies to `held_rescan` and `condition_change` wakes whose `wake_trigger.type` is `COMPARISON_TRIGGER`
- Prompt envelope includes `trigger_review_mode` and `active_frozen_triggers`
- Each candidate block must set `PRIOR_TRIGGER_REVIEW=HELD|FAILED|EXPIRED:<evidence>`
- Validation rejects `NOT_APPLICABLE` on review cycles

## Runtime hygiene (Phase A)

- Reconcile persists expired/superseded rows to `active-comparison-triggers.json` on every read path
- `pending-held-rescan.json` carries `earliest_rescan_utc` so rescan never runs in the same flat tick that created it
- Instruments omitted from a new ledger have prior HELD rows expired

## Tests

- `tests/test_trigger_lifecycle.py`
- `tests/test_scanner_contract.py` (`validate_trigger_review_ledger`)
