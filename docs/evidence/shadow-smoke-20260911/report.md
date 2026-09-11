# Shadow smoke report — 2026-09-11

Status: `blocked` for cognitive output validation; delivery remained disabled.

- Profile commit: `5849e2309f01cd526eb11835954599793444d175`
- Gateway paired commit: `928ed96dafb435ca9c8f7bdc590fd4d7711eaa7d`
- Prompt version: `glitch-topstep-v17.2`
- Envelope hash: `61b94ab398990dd58d2193c1de6628f9b527e77dd1c2001885f904dac2cfe952`
- Snapshot hash: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- `orders_sent`: `0` on all three runs
- Delivery: `not_delivered`, `delivery_disabled_by_mode`
- Skill hashes:
  - `topstep-smart-money`: `B45C43AD5091486AF4DFDD6CACB5E551F215FBBFCD571452F617B378C8E645D8`
  - `topstep-indicators`: `2D2A3B0841E200135C369AAA0CFA9CA7E1B4ABF09DC2342169DB3F7A08B2028C`

The same immutable envelope was replayed three times. All three runs resolved
the same envelope hash and all six profile invocations were classified as
`provider_error:hermes_failed`; no raw model answer was produced. Therefore
specialized output, intra-profile stability, and candidate/no-edge behavior
remain unproven. The failure is preserved as evidence rather than converted to
`NOTHING`.

The first attempt used a market-universe fixture and stopped before invocation
with `packet_incomplete`; the corrected decision-packet fixture is committed
at `tests/fixtures/shadow_smoke_packet_v17.2.json`.

Recommendation remains:

`capability_present_but_unproven` + `shadow-only` + `needs-human-review`

No overnight, canary, armed paper, sizing change, or real order was started.
