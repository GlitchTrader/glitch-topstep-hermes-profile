---
name: topstep-market-scan
description: Symmetric multi-instrument scan and INSTRUMENT_COMPARISON_V1 line ledger before ranking or NOTHING on Glitch Topstep.
---

# Topstep Market Scan

Use when `decision_packet.market_universe.candidates` has more than one instrument.

## Mandatory order

1. Scan every candidate symmetrically before ranking or choosing `NOTHING`.
2. Do not default to MNQ, the first list entry, or the most familiar symbol.
3. For each candidate, fill one `INSTRUMENT <ROOT>:` block in `decision_audit.decisive_evidence`.

## Per-instrument fields (line ledger)

| Field | Source |
|-------|--------|
| `CURRENT_AUCTION` | Current setup from that candidate's scanner evidence only |
| `BULLISH_PATH` | Bull continuation or reclaim path, or explicitly absent/conditional |
| `BEARISH_PATH` | Bear continuation or failure path, or explicitly absent/conditional |
| `NEXT_TRANSITION` | Next state change plus evidence |
| `PRIOR_TRIGGER_REVIEW` | `NOT_APPLICABLE` when no prior trigger; otherwise review vs prior frame |
| `ASYMMETRY` | Coarse edge summary; `UNKNOWN` only when evidence is unusable |
| `TRIGGER_*` | One frozen trigger per candidate (`HELD`, `FAILED`, or `EXPIRED`) |

## Ranking rules (#171)

- Rank using evidence classes present for **every** candidate: bars, quote, and observation quality from the scanner packet.
- Do **not** use selected-contract order flow as a ranking bonus.
- `MCL` is Micro Crude Oil; `MCLE` is ProjectX identity only.
- When `market.session_levels_reliable` is false, do not treat session high/low as structural edges.
- When `market_alignment.synchronized` is false, use quote and order flow of the selected contract for timing; use 5m/60m plus partial 1m for structure; state lag in `disconfirming_evidence`, not as automatic NOTHING.
- `account_selection.mode=single_active_position`: cognitive ranking picks the best candidate; when the account is flat any eligible candidate may receive `ENTER_*`; only one instrument may be positioned account-wide.
- `execution_mode=eligible` means the candidate may receive entries while flat; `flat_required` means another instrument is currently positioned; `selected` is the active positioned contract or the packet target while managing.

## Output contract

- Put the **full** line ledger in `decision_audit.decisive_evidence` exactly as in `required_output_template.decision_audit.decisive_evidence`.
- Put frame continuity in `disconfirming_evidence` (`prior_hypothesis=...`) when `recent_frames` is non-empty.
- Close with `RANKING`, `SELECTION_INSTRUMENT`, `SELECTION_ACTION`, and `SELECTION_REASON`.
- No placeholders (`REPLACE`, `REPLACE_WITH_*`, `...`, `?`), JSON, or Markdown fences.
- `NOTHING` is allowed only after every instrument block is complete.

See `topstep-build-intent` for final strict `glitch.intent.v3` serialization.
