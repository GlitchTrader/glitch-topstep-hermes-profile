# Architecture

## Runtime boundary

The profile is the cognition package, not the venue adapter.

```text
Glitch Topstep Node service
  GET /health
  GET /state
  GET /packet
  POST /intent
       │ bearer-authenticated localhost
       ▼
Deterministic Python worker
  capture bounded frame history
  decide whether a model call is due
  invoke isolated Hermes session
  normalize and validate exact identity
  persist outbox before delivery
       │
       ▼
Hermes model
  memory retrieval only
  no terminal, browser, MCP, file, or provider toolsets
       │ strict intent
       ▼
Deterministic worker → local gateway → ProjectX
```

The Node service owns all ProjectX authentication. The profile sees only a sanitized account alias, contract description, market state, policy state, and valid quantities.

## Decision cadence

The native cron job runs every minute but calls Luna only when:

- a configured account is positioned;
- a flat account reaches a five-minute boundary and is entry-eligible; or
- a non-expired operator directive exists.

Flat decisions require five captured minute frames. Positioned decisions use the available recent frame path and permit only HOLD or EXIT until amendment ownership is implemented in the gateway.

## Decision persistence

For every gateway packet:

```text
attempts/<packet>.json   model-call lifecycle
outbox/<packet>.json     validated intent persisted before delivery
receipts/<packet>.json   gateway response
decisions.jsonl          append-only cognition record
receipts.jsonl           append-only delivery record
events.jsonl             failures and corrections
```

A packet cannot trigger a second model call after an attempt record exists. An existing outbox may be delivered again only while the gateway still accepts its exact snapshot identity.

## Learning

The 15-minute cron job launches a separately locked process and returns immediately. The worker calls Sol only when canonical evidence makes a loop due:

- debrief new canonical outcomes;
- hourly review when new episodes exist;
- five-hour plan when new reviews exist;
- daily journal after the session when episodes exist.

Learning consumes only `glitch.topstep.trade_outcome.v1`. Position disappearance, account-balance changes, and local guesses are not accepted as completed-trade truth.

Cognitive changes are written as candidates. Automatic activation is disabled by default and, when enabled, requires the configured number of known episode IDs.
