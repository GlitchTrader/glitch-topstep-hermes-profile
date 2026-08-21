# GTHP-033 — Discard superseded pending outbox before delivery retry loop

**Priority:** P1 (delivery recovery)  
**Status:** open  
**Depends on:** GTHP-013, GTHP-AUDIT-03 (related; narrower fast path)  
**Discovered:** 2026-08-21 live smoke after GTHP-DATA-01 Phase B (`decision_ready` + `packet_superseded_before_delivery` loop)

## Problem

When cognition succeeds but delivery does not finish inside the gateway packet lease (~60s), the worker leaves an intent in `state/outbox/{packet_id}.json`. On every subsequent cron minute:

1. `pending_outbox()` finds the file.
2. `discard_stale_outbox_intent()` **does not** discard because the minute-frame for that `packet_id` is still retained locally (`frame_retention` ≈ 180 minutes).
3. `deliver_intent()` calls `prepare_intent_for_delivery()`, which fetches the **current** `/packet` from the gateway.
4. If `packet_id` or `snapshot_hash` no longer matches, it raises `ValueError: packet_superseded_before_delivery`.
5. The pending branch does not map that error to discard; the cycle fails and retries forever until the frame is pruned **or** an operator deletes the outbox manually.

Observed live: `decision_ready` at `2026-08-21T00:40:53Z` with valid `INSTRUMENT_COMPARISON_V1` ledger; repeated cron failures with `packet_superseded_before_delivery` until manual outbox removal.

## Goal

Stop the minute-cron failure loop **as soon as the gateway packet lease is gone**, without waiting for minute-frame pruning and without blind discard when gateway receipt ambiguity remains.

## Proposed solution

Extend the pending-outbox path in `run-topstep-cycle.py` and `workflows/intent_outbox.py`:

### 1. Early supersession probe (before `deliver_intent`)

When `pending_outbox` is non-empty, after the existing `discard_stale_outbox_intent()` call and **before** delivery:

| Condition | Action |
|-----------|--------|
| `intent.expires_utc` is in the past (UTC) | Discard with reason `packet_lease_expired` after existing gateway receipt gate |
| Current `/packet` `packet_id` ≠ outbox `packet_id` | Discard with reason `packet_superseded` after existing gateway receipt gate |
| `ENTER_*` and scope/contract mismatch vs current packet | Keep existing `entry_scope_superseded` / `entry_intent_expired` semantics |

Reuse the receipt gate already in `discard_stale_outbox_intent()`:

- HTTP 200 receipt → retain outbox (`outbox_retained_gateway_receipt`)
- HTTP 404/410 → safe to discard
- Transport/unknown → retain (`outbox_retained_delivery_unknown`)

On discard: emit `intent_discarded_stale_packet` with the new reason, unlink outbox, `return run_once(args, root)` so the same cron invocation can run fresh cognition on the current packet.

### 2. Map delivery failure to discard (defense in depth)

In the pending-outbox `except ValueError` around `deliver_intent()`, treat these as discard candidates (with the same receipt gate):

- `packet_superseded_before_delivery`
- `entry_intent_expired`
- `entry_scope_superseded`
- `entry_range_superseded`

Today only `discard_unexecutable_entry_outbox()` handles a subset of entry errors.

### 3. Event taxonomy

Add/standardize discard reasons in `events.jsonl`:

- `packet_lease_expired`
- `packet_superseded`
- (existing) `stored_packet_not_found`

Do **not** emit `decision_failed` for superseded pending outbox once discard succeeds; the follow-up cognition attempt in the same worker run is the expected recovery.

## Non-goals

- Changing gateway packet lease duration
- Discarding without receipt check when delivery state is ambiguous
- Replacing GTHP-AUDIT-03 crash-durable outbox state machine (this is the fast supersession path)

## Acceptance

- [ ] Pending outbox with expired `expires_utc` is discarded on the next cron minute when gateway receipt is absent (404/410).
- [ ] Pending outbox whose `packet_id` differs from current `/packet` is discarded under the same receipt gate.
- [ ] Known gateway receipt (200) retains outbox; event `outbox_retained_gateway_receipt`.
- [ ] Unittest: simulate pending outbox + fresh packet id → `intent_discarded_stale_packet` + recursive `run_once` without `packet_superseded_before_delivery` loop.
- [ ] Unittest: receipt 200 → outbox retained, no discard.
- [ ] Regenerate `SHA256SUMS` when scripts change.

## Files (expected)

| File | Change |
|------|--------|
| `scripts/workflows/intent_outbox.py` | `should_discard_superseded_outbox(intent, current_packet, *, token)` + shared receipt gate |
| `scripts/run-topstep-cycle.py` | Call probe in pending branch; extend `ValueError` handler |
| `tests/test_direct_cycle.py` or `tests/test_intent_outbox.py` | Regression fixtures |

## Related

- `scripts/workflows/intent_outbox.py` — `discard_stale_outbox_intent()` (frame-pruning path only today)
- `scripts/run-topstep-cycle.py` — `prepare_intent_for_delivery()` raises `packet_superseded_before_delivery`
- GTHP-AUDIT-03 (#123) — crash-durable outbox + ambiguity reconciliation
- GTHP-DATA-01 Phase B — multi-instrument cognition unblocked; exposed delivery timing gap
