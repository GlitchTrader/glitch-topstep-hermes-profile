---
name: topstep-build-intent
description: Convert one Glitch Topstep decision into the exact strict `glitch.intent.v2` object accepted by the local gateway.
---

# Build Intent

Return exactly one JSON object and no Markdown or prose.

- Preserve the supplied account alias, instrument, operator profile `glitch-topstep`, and snapshot hash exactly.
- Required core fields: `schema_version`, UUID `intent_id`, `created_utc`, `instrument`, `account`, `operator_profile`, `action`, `confidence`, `snapshot_hash`, `model_version`, `prompt_version`, `reason`, and `decision_audit`.
- `decision_audit` contains exactly: `bull_case`, `bear_case`, `flat_case`, `aggressive_case`, `conservative_case`, `decisive_evidence`, `disconfirming_evidence`, `change_condition`, and `final_choice`. `final_choice` equals `action`.
- Choose `action` only from `execution.supported_actions` in the current packet.
- For `ENTER_LONG` and `ENTER_SHORT`, use a positive integer `quantity` within `policy.max_contracts` and `execution.maximum_additional_contracts`, `order_type: "MARKET"`, and absolute numeric `stop_loss` and `take_profit_1`.
- For `HOLD` and `NOTHING`, omit `quantity`, `order_type`, `stop_loss`, `take_profit_1`, amendment fields, and exit sizing fields.
- For `MOVE_STOP`, include absolute numeric `new_stop_price`. Omit entry fields. Include `target_intent_id` when more than one tranche in `protection.tranches` still holds contracts.
- For `MOVE_TP`, include absolute numeric `new_take_profit` or `take_profit_1`. Omit entry fields. Include `target_intent_id` when more than one active tranche remains.
- For `EXIT`, omit entry and amendment fields. Omit `quantity` and `exit_fraction` for a full flat. For partial reduction, include exactly one of `quantity` or `exit_fraction`. Include `target_intent_id` when reducing a specific tranche in a multi-tranche book.
- Do not emit limit orders, provider IDs, credentials, additional fields, multiple objects, comments, or trailing text.

Glitch performs final identity, freshness, geometry, risk, and execution validation.
