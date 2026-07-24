# Glitch Topstep local state ledger map

All under `~/AppData/Local/hermes/profiles/glitch-topstep/state/` (Windows;
via bash use `C:\Users\...\state\` or `/c/Users/.../state/`).

## Files
- `decisions.jsonl` — append-only decision records (`glitch.topstep.decision_record.v1`).
  Each wraps the `glitch.intent.v2` object. Read the LAST line for the most recent decision.
  Intent fields incl. `action` (NOTHING | ENTER_LONG | ENTER_SHORT | HOLD | EXIT),
  `quantity`, `stop_loss`, `take_profit_1`, `confidence`, `reason`, `decision_audit`.
- `receipts.jsonl` — append-only delivery receipts (`glitch.topstep.delivery_receipt.v1`).
  EXECUTION-TRUTH file. Joins to a decision via `intent_id`.
- `events.jsonl` — cycle-level events (`glitch.topstep.cycle_event.v1`): `decision_failed`
  with `error` (e.g. `RuntimeError:hermes_failed`, `TimeoutExpired`). These cycles produced
  NO decision — don't count them as decisions.
- `attempts/<UTC>.json` — per-cycle attempt snapshots.
- `minute-frames/<UTC>.json` — captured gateway market frames (one per minute).
- `receipts/`, `outbox/`, `supervisor/` — dirs for extended detail.
- `gateway.heartbeat`, `direct-cycle.lock` — liveness/lock, not history.
- `../gateway_state.json` — gateway process state (pid, running, updated_at).

## Answering "did we actually trade?" (shadow vs live)
A decision with `action: ENTER_LONG/ENTER_SHORT` is only a PROPOSAL. Not a trade until the
gateway submits to the venue. Check the receipt body:
- `result.body.shadow == true` AND `result.body.venue_result == null`
  => SHADOW MODE: intent recorded, NO venue order, NO fill, NO position, NO PnL.
  Message: "Intent recorded in shadow mode; no venue order submitted."
- Real trade => `shadow: false` and non-null `venue_result` (fills/order IDs).

Count ENTER_* decisions for intent activity, but confirm real execution ONLY from
receipts.jsonl. In shadow mode, zero real trades occur regardless of ENTER_* count.

## Fast recipes
- Last decision: `tail -n 1 decisions.jsonl` then pretty-print the JSON.
- Action tally (execute_code): iterate decisions.jsonl, `collections.Counter` over `intent.action`.
- Shadow check: grep receipts.jsonl for `"shadow":true` / `"venue_result":null`.
- Failed cycles: grep events.jsonl for `decision_failed`.

## Observed example (2026-07-23 session)
15 decisions: 10 NOTHING, 4 ENTER_SHORT, 1 ENTER_LONG. All 15 receipts were shadow
(`venue_result: null`) => zero real trades. events.jsonl also held 11 failed cycles
(6 RuntimeError, 5 TimeoutExpired) that produced no decision at all.

## Note
Shadow mode is a gateway POLICY setting (human control). Do not disable it or push to live
from an operator session — surface it and let the human decide.
