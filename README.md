# Glitch Topstep Hermes Profile v0.1.0

Persistent Hermes cognition, deterministic workers, skills, and control commands for [`GlitchTrader/glitch-topstep`](https://github.com/GlitchTrader/glitch-topstep).

```text
ProjectX / TopstepX
        │
        ▼
Glitch Topstep local gateway
  state · policy · stop-aware risk · execution · receipts
        │ authenticated packet
        ▼
Hermes profile: glitch-topstep
  observation · thesis · decision · review · learning
        │ strict glitch.intent.v2
        ▼
Glitch Topstep local gateway
```

## Authority

```text
Hermes proposes.
Glitch Topstep validates, sizes, executes, reconciles, journals, and protects.
ProjectX owns venue truth.
Topstep owns final rule enforcement.
```

The profile never contains or receives ProjectX credentials, JWTs, numeric account IDs, or numeric contract IDs. It communicates only with the authenticated loopback gateway.

## Status

Experimental scaffold. Fresh installations create the operator and learning jobs in a paused state. The profile makes no profitability, payout, unattended-operation, PA, or live-readiness claim.

Implemented:

- isolated Luna decision sessions every five minutes while flat and every minute while positioned;
- bounded five-frame continuity maintained outside the model;
- exact `glitch.intent.v2` validation and one-time output repair;
- durable outbox, decisions, receipts, attempt records, and operator directives;
- deterministic `/trade`, `/pause_trading`, `/flatten_all`, `/topstep_status`, `/long`, `/short`, and bias commands;
- Sol debrief, hourly review, five-hour planning, and daily learning workers;
- canonical outcome-only learning;
- proposed-by-default cognitive overlays with an explicit activation switch and evidence threshold;
- checksum-verified installation and supervised Hermes gateway.

Current gateway limitations remain authoritative: one account, one contract, one entry tranche, no verified `MOVE_STOP`/`MOVE_TP`, manually supplied policy state, and no complete payout/copier lifecycle.

## Requirements

- Windows with the local `glitch-topstep` Node service installed and running.
- Hermes `0.18.2` or newer.
- OpenAI Codex OAuth authorized for the `glitch-topstep` profile.
- The same `GLITCH_TOPSTEP_LOCAL_TOKEN` configured in both repositories.

## Install

```powershell
hermes profile install github.com/GlitchTrader/glitch-topstep-hermes-profile --alias
hermes -p glitch-topstep auth add openai-codex --type oauth
notepad "$env:LOCALAPPDATA\hermes\profiles\glitch-topstep\.env"
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\hermes\profiles\glitch-topstep\setup.ps1"
```

Set at minimum:

```text
GLITCH_TOPSTEP_LOCAL_TOKEN=<same local token used by the gateway>
```

Then:

```text
/topstep_status
/trade
```

`/trade` enables Hermes cognition only. The Node gateway independently remains `disabled`, `shadow`, or `armed` according to its own configuration.

## Controls

- `/topstep_status` — gateway mode, account visibility, and Hermes job state.
- `/trade` — resume the minute operator and 15-minute learning launcher.
- `/pause_trading` — pause both jobs without altering provider-side protection.
- `/flatten_all` — pause cognition and submit one deterministic risk-reducing `EXIT` through the strict gateway contract.
- `/long`, `/short` — queue one protected operator-directed experiment for the next eligible flat packet.
- `/bias_long`, `/bias_short`, `/bias_neutral` — soft one-cycle advisory.

## Updating

```powershell
hermes profile update glitch-topstep
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\hermes\profiles\glitch-topstep\setup.ps1"
```

Authentication, `.env`, sessions, memory, state, ledgers, and existing enabled/paused job state are not part of the checksum manifest and are preserved.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- [`docs/OUTCOME-CONTRACT.md`](docs/OUTCOME-CONTRACT.md)
- [`docs/HANDOFF.md`](docs/HANDOFF.md)
