# Operations

## Startup order

1. Start the local `glitch-topstep` Node gateway in `shadow` mode.
2. Verify `GET /health` locally.
3. Install and configure this profile.
4. Run `/topstep_status`.
5. Run `/trade` to begin scheduled cognition.
6. Inspect decision and receipt ledgers before considering any gateway mode change.

## Safe defaults

- Profile jobs: paused on first setup.
- Gateway execution mode: controlled only in the gateway repository.
- Cognitive overlays: proposed, not activated.
- Scheduled model toolsets: memory only.
- Flat cognition: one call per minute by default; operators may reduce flat cadence explicitly.
- Positioned cognition: one call per minute; manage with `HOLD`, `MOVE_STOP`, `MOVE_TP`, partial or full `EXIT`, and scale-in only when advertised in `execution.supported_actions`.

## Incident controls

`/pause_trading` stops new model calls but does not cancel provider orders or remove protection.

`/flatten_all` performs three actions:

1. pause both Hermes jobs;
2. fetch the current authenticated packet;
3. submit a deterministic human-authored EXIT through the same strict intent endpoint.

If the gateway is unavailable, jobs remain paused and the command reports that it could not prove flatten submission. Use the provider UI as the final human control.

## Logs and state

The profile-local `state/` directory is intentionally excluded from distribution updates. Back it up before migration, but never copy it into another account without reviewing account aliases and gateway configuration.

`/topstep_status` reports the detached operator worker's actual `running`, `ok`, or `failed` state from `state/supervisor/direct-worker-status.json`. The cron launcher can finish successfully before that worker does, so use the worker state when diagnosing decision delivery.

Do not commit `.env`, sessions, memory, state, or logs.
