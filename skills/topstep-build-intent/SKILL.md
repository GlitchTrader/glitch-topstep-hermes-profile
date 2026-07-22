---
name: topstep-build-intent
description: Convert one Glitch Topstep decision into the exact strict `glitch.intent.v2` object accepted by the local gateway.
---

# Build Intent

Return exactly one JSON object and no Markdown or prose.

- Preserve the supplied account alias, instrument, operator profile `glitch-topstep`, and snapshot hash exactly.
- Required core fields: `schema_version`, UUID `intent_id`, `created_utc`, `instrument`, `account`, `operator_profile`, `action`, `confidence`, `snapshot_hash`, `model_version`, `prompt_version`, `reason`, and `decision_audit`.
- `decision_audit` contains exactly: `bull_case`, `bear_case`, `flat_case`, `aggressive_case`, `conservative_case`, `decisive_evidence`, `disconfirming_evidence`, `change_condition`, and `final_choice`. `final_choice` equals `action`.
- For `ENTER_LONG` and `ENTER_SHORT`, select `quantity` only from `valid_entry_quantities`, use `order_type: "MARKET"`, and include absolute numeric `stop_loss` and `take_profit_1`.
- For `HOLD`, `EXIT`, and `NOTHING`, omit `quantity`, `order_type`, `stop_loss`, and `take_profit_1`.
- Do not emit `MOVE_STOP`, `MOVE_TP`, limit orders, provider IDs, credentials, additional fields, multiple objects, comments, or trailing text.

Glitch performs final identity, freshness, geometry, risk, and execution validation.
