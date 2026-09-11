# Security report — Hermes PRAC runner

## Boundaries

- Hermes supplies cognition only.
- The gateway is the only execution authority.
- The profile imports only the local gateway token for the authorized gateway adapter; ProjectX credentials are removed from the Hermes child environment and no ProjectX module is imported.
- Offline and shadow delivery return `orders_sent=0` without calling `/intent`.
- `prac_live` requires the explicit `--authorize` flag.

## Safety gates

The packet must be complete, state-complete, quote-valid, unexpired, bound to one exact contract, and carry explicit 1-minute bar-close evidence. Every profile receives the same sealed envelope hash. Aggregation produces one decision, never one order per profile. Entry delivery requires a stop and is bounded to one active exposure. Ambiguous receipts and unconfirmed protection stop the runner.

## Evidence and secrets

Only sanitized status and allowlisted receipt fields belong in evidence. Raw credentials, `.env` contents, ProjectX values, Hermes provider output, and bearer values are not written by the runner. The offline evidence is in `docs/evidence/runner-offline-20260910/`.

## Residual operator gate

The next stage is live preflight only. No PRAC session, shadow, paper, canary, promotion, reset, or order was initiated by this implementation.
