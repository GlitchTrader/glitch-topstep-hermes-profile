---
name: topstep-build-intent
description: Convert one Glitch Topstep decision into the exact strict `glitch.intent.v3` object accepted by the local gateway.
---

# Build Intent

Return exactly one JSON object and no Markdown or prose.

- Preserve the supplied account alias, instrument, operator profile `glitch-topstep`, and snapshot hash exactly.
- Required core fields: `schema_version`, UUID `intent_id`, `created_utc`, `instrument`, `account`, `operator_profile`, `action`, `confidence`, `snapshot_hash`, `model_version`, `prompt_version`, `reason`, and `decision_audit`.
- Replace template placeholders (`<CHOOSE_FROM_supported_actions>`, `<0.0-1.0>`, `Replace`) with real values; never emit placeholder strings.
- `decision_audit` contains exactly: `bull_case`, `bear_case`, `flat_case`, `aggressive_case`, `conservative_case`, `decisive_evidence`, `disconfirming_evidence`, `change_condition`, and `final_choice`. `final_choice` equals `action`.
- Keep `bull_case`, `bear_case`, `flat_case`, `aggressive_case`, `conservative_case`, `change_condition`, and `reason` to **one compact evidence-dense sentence** each; do not repeat the same fact across fields.
- When flat with a single candidate, `decisive_evidence` must begin with `prior_hypothesis=<CONFIRMED|INVALIDATED|PARTIALLY_CONFIRMED|UNCHANGED>` when `recent_frames` is non-empty, then state material deltas since the immediately prior frame in compact evidence-dense sentences, and include one `SELECTION_EV=` line for flat `ENTER_*` or `NOTHING`.
- When positioned on a single active instrument, write the compact `POSITION_MANAGEMENT_V1` template in `decisive_evidence` (see `topstep-position-management`) and put `prior_hypothesis` continuity in `disconfirming_evidence` when `recent_frames` is non-empty.
- Choose `action` only from `execution.supported_actions` in the current packet. Rebuild the action from current evidence; do not copy a prior cycle default. Never `HOLD` while flat; never `NOTHING` while positioned.
- For `ENTER_LONG` and `ENTER_SHORT`, use a positive integer `quantity` within `policy.max_contracts` and `execution.maximum_additional_contracts`, `order_type: "MARKET"`, and absolute numeric `stop_loss` and `take_profit_1`. Omit `wake_triggers`.
- For `HOLD` and `NOTHING`, omit `quantity`, `order_type`, `stop_loss`, `take_profit_1`, amendment fields, and exit sizing fields. `wake_triggers` is optional local-only scheduling metadata; omit it unless you want an early wake before the next flat cadence.
- For `MOVE_STOP`, include absolute numeric `new_stop_price`. Omit entry fields and `wake_triggers`. Include `target_intent_id` when more than one tranche in `protection.tranches` still holds contracts. Submit only when `protection.protection_status` is `confirmed`.
- For `MOVE_TP`, include absolute numeric `new_take_profit` or `take_profit_1`. Omit entry fields and `wake_triggers`. Include `target_intent_id` when more than one active tranche remains. Submit only when `protection.protection_status` is `confirmed`.
- For `EXIT`, omit entry, amendment, and `wake_triggers` fields. For a full EXIT that closes the entire active position, omit both `quantity` and `exit_fraction`. Request a partial EXIT only when the packet explicitly advertises proven partial-reduction continuity; otherwise use full EXIT or HOLD. Include `target_intent_id` when reducing a specific tranche in a multi-tranche book.
- `change_condition` is advisory text for later accountability; price levels in it do not require mirrored `wake_triggers`.
- Do not emit limit orders, provider IDs, credentials, additional fields, multiple objects, comments, or trailing text.

## Multi-instrument flat scan

Serialization begins **only after** every eligible candidate has a complete `INSTRUMENT_COMPARISON_V1` line ledger in `decisive_evidence`.

When `market_universe.candidates` has more than one entry:

- Put the **full** line ledger in `decision_audit.decisive_evidence` exactly as supplied in `required_output_template.decision_audit.decisive_evidence`.
- Keep every comparison field to one compact evidence-dense sentence; keep the complete `INSTRUMENT_COMPARISON_V1` ledger under **8000** characters (TRIGGER_REVIEW_V1 under **6000**).
- Include `SELECTION_EV` in the tail with `direction=LONG|SHORT` (never `FLAT`/`NONE`/`NA`); ENTER_* requires `now_ev=POSITIVE`; flat `NOTHING` forbids `now_ev=POSITIVE` but still needs that side's counterfactual entry/stop/target numbers.
- Put continuity in `disconfirming_evidence`: `prior_hypothesis=<CONFIRMED|INVALIDATED|PARTIALLY_CONFIRMED|UNCHANGED>; ...` when `recent_frames` is non-empty.
- `SELECTION_INSTRUMENT` equals the ranking winner. While flat it may differ from `packet.instrument` when the winner is another eligible candidate; delivery fetches `/packet?contract_id=` for that instrument before POST `/intent`.
- Do not emit JSON, Markdown fences, or a second comparison format.

`NOTHING` is allowed only after all instrument blocks are complete.

Glitch performs final identity, freshness, geometry, risk, and execution validation.
