# GTHP-TRIGGER-01 — frozen per-path trigger lifecycle

Comparison triggers live in `decision_audit.decisive_evidence` as an `INSTRUMENT_COMPARISON_V1` line ledger (Phase B); Phase D2 will move the same structure to a native object.

## Runtime

- `scripts/trigger_lifecycle.py` persists triggers to `state/supervisor/active-comparison-triggers.json`
- Status must be one of `HELD`, `FAILED`, `EXPIRED`
- `NOTHING` with any `HELD` trigger schedules `pending-held-rescan.json`
- `run-topstep-cycle.py` consumes the pending rescan as invocation reason `held_rescan`
- Ratchet: changing `condition` without a status transition fails closed

## Tests

- `tests/test_trigger_lifecycle.py`
- `tests/test_scanner_contract.py` (static ledger validation)
