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
- Flat cognition outside the gateway `session.entry_window_open` window is skipped by default (`GLITCH_TOPSTEP_RESPECT_SESSION_GATE=true`); positioned cycles, operator directives, and wake triggers still invoke. Set `GLITCH_TOPSTEP_SESSION_GATE_OVERRIDE=true` for PRAC acceptance outside RTH.
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

## Profile updates (Windows)

Always record `source: github.com/GlitchTrader/glitch-topstep-hermes-profile` in the installed `distribution.yaml`. Never install or update from a local clone path — Hermes copies `.git` into the profile and future updates fail with `PermissionError`.

Canonical update command:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\hermes\profiles\glitch-topstep\scripts\safe-profile-update.ps1"
```

Contributors: after changing distribution-owned files, run `python scripts/regenerate_sha256sums.py` before merging. CI rejects drift.

## Release version checklist

When cutting a profile release paired with a gateway build:

1. Bump `distribution.yaml` `version`.
2. Update `scripts/distribution_manifest.py` `TESTED_GATEWAY_VERSION` (and `MIN_GATEWAY_VERSION` only when the floor moves).
3. Confirm `PROMPT_VERSION` matches the direct-cycle contract (`glitch-topstep-v*`).
4. Run the full unittest suite and `python scripts/regenerate_sha256sums.py`.
5. Verify `GET /health` on the target gateway reports a compatible `compatibility.gateway_version`.
6. Run `safe-profile-update.ps1` on a Windows operator host after merge.

`tests/test_compatibility.py` fails on drift between `parity.PROMPT_VERSION`, `distribution_manifest`, and `PROFILE_COMPATIBILITY`.

`setup.ps1` and `safe-profile-update.ps1` also run `ensure_hermes_distribution_patch.py`, which idempotently patches Hermes `profile_distribution.py` for Windows-safe profile updates (re-applied after Hermes agent upgrades).
