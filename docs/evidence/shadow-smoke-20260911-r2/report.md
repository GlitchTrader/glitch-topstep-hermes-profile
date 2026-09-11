# Shadow smoke v17.2 — post-fix replay

Timestamp: `2026-09-11T15:06Z` (UTC, recorded in run artifacts)

Status: `blocked` for cognitive output validation; delivery remained disabled.

- Gateway commit: `6446984` (paired runtime ancestor `928ed96`)
- Profile commit: `90d2ef6ec5a316de4af05638f11fd00cd02c810c`
- Prompt version: `glitch-topstep-v17.2`
- Paired-contract SHA256: `83992E681F3EA0784667F36DAE509E1F04E96318CC61FED5B0E58F5B22D8897A`
- Effective `HERMES_HOME`: canonical profile checkout containing this report's parent repository
- Envelope hash: `61b94ab398990dd58d2193c1de6628f9b527e77dd1c2001885f904dac2cfe952`
- Runs: `run-1.json`, `run-2.json`, `run-3.json`
- Orders sent: `0` in every run
- Delivery: `not_delivered`, `delivery_disabled_by_mode`

The same immutable envelope produced the same envelope hash in all three
replays. Preload completed before invocation and the parallel preload test
passed. Hermes then exited with a sanitized provider diagnostic in every
profile invocation (`returncode=1`, no stored credentials). The preserved
diagnostic includes safe command, stage, classification, duration, stdout and
stderr; no credential or token was recorded.

No model answer was produced. Specialized output, cognitive stability, and
live MES/MCL capability therefore remain unproven. The failure was preserved
as `provider_error:hermes_provider:hermes_process_nonzero`, not converted to
`NOTHING`.

## Decision

`blocked` + `needs-human-review` + `shadow-only`

No overnight, canary, armed paper, sizing change, gateway promotion, or live
order was started.
