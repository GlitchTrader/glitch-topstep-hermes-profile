---
name: topstep-state-introspection
description: Answer operational questions about the local Glitch Topstep operator by reading its state ledgers — last decision, action tally, and whether any real trade actually executed (shadow vs live).
---

# Glitch Topstep State Introspection

Use this when the user asks operational-history questions OUTSIDE a scheduled decision
cycle, e.g. "qual foi a última decisão?", "did we trade yet?", "how many entries?",
"what's the gateway doing?". These are read-only investigations of local state files —
NOT a `glitch.intent.v2` cycle, so respond in normal prose (match the user's language).

All state lives under:
`~/AppData/Local/hermes/profiles/glitch-topstep/state/`
(bash: `C:\Users\<user>\AppData\Local\hermes\profiles\glitch-topstep\state\` or `/c/Users/.../state/`)

## The critical distinction: intent != trade
An `ENTER_LONG` / `ENTER_SHORT` decision in `decisions.jsonl` is only a PROPOSAL.
It is NOT a trade until the gateway submits to the venue. EXECUTION TRUTH lives in
`receipts.jsonl`, not `decisions.jsonl`. Always confirm real execution from receipts:

- `result.body.shadow == true` AND `result.body.venue_result == null`
  => SHADOW MODE: no venue order, no fill, no position, no PnL. Zero real trades.
  Body message: "Intent recorded in shadow mode; no venue order submitted."
- Real trade needs `shadow: false` + non-null `venue_result`.

Never report "we entered short" from a decision record alone. Cross-check the matching
receipt (join on `intent_id`) before telling the user a trade happened.

## Key files
- `decisions.jsonl` — append-only decision records; last line = latest decision. Wraps the
  intent (`action`, `quantity`, `stop_loss`, `take_profit_1`, `confidence`, `reason`, `decision_audit`).
- `receipts.jsonl` — delivery receipts (execution truth); join via `intent_id`.
- `events.jsonl` — cycle events; `decision_failed` (RuntimeError / TimeoutExpired) means the
  cycle produced NO decision — don't count these as decisions.
- `minute-frames/`, `attempts/` — captured market frames and per-cycle snapshots.
- `gateway.heartbeat`, `direct-cycle.lock` — liveness/lock, not history.

Detailed layout + fast bash/read_file recipes: references/state-ledger-map.md

## Recipes
- Last decision: `tail -n 1 decisions.jsonl`, pretty-print JSON.
- Action tally: iterate decisions.jsonl, Counter over `intent.action`.
- Trade check: grep receipts.jsonl for `"shadow":true` / `"venue_result":null`.
- Failed cycles: grep events.jsonl for `decision_failed`.

## Pitfalls
- Do NOT confuse machine hostname with the Windows user for paths — use the real home dir.
- Do NOT disable shadow mode or push to live from an operator session. Shadow mode is a
  gateway policy (human control). Surface it; let the human decide.
- Never expose ProjectX usernames, keys, JWTs, numeric account IDs, or numeric contract IDs
  found in any state file.

## Overlap note
Territory overlaps the protected `topstep-review-outcomes` skill (manually authored, not
editable by curation). This skill is the read-only "answer a quick history question" entry
point; topstep-review-outcomes governs formal canonical outcome debriefs.
