# Hermes skill wiring and prompt v17.2

Date: 2026-09-11

The canonical profile now contains the complete eight-commit Hermes runner
series and fail-closed wiring for `topstep-smart-money` and
`topstep-indicators`. The runner forces `HERMES_HOME` to the canonical profile,
verifies byte-identical skill files, invokes Hermes preload, checks the exact
loaded skill set and validates specialty markers before a declared-skill
invocation proceeds.

Because skills are now part of the effective prompt, the paired prompt version
is `glitch-topstep-v17.2`. Existing v17.1 replay artifacts remain immutable
historical evidence and must not be reused for new results.

This change remains evaluation-only and shadow-only. It does not change sizing,
execution authority, risk gates, protection, or overnight status. Independent
reaudit is required before any promotion.
