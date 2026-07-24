# Glitch Topstep Hermes Profile v0.1.1

Dedicated Hermes cognition, skills, learning workers, and operator controls for [`GlitchTrader/glitch-topstep`](https://github.com/GlitchTrader/glitch-topstep).

```text
ProjectX / TopstepX
        │
        ▼
Glitch Topstep local gateway
  truthful state · hard account facts · execution · receipts
        │ authenticated sanitized packet
        ▼
Hermes profile: glitch-topstep
  observation · judgment · decision · review · learning
        │ strict glitch.intent.v2
        ▼
Glitch Topstep local gateway
  factual verification · translation · reconciliation · protection
```

## Authority

```text
Hermes decides.
Glitch Topstep verifies factual execution safety, translates, reconciles, journals, and protects.
ProjectX owns venue truth.
Topstep owns final account-rule authority.
```

The profile never contains or receives ProjectX credentials, JWTs, numeric account IDs, or numeric contract IDs. It communicates only with the authenticated loopback gateway.

Market observations, data-quality warnings, account headroom, capacity, stage, payout state, and policy fields are evidence for Hermes. They are not deterministic trading decisions. The gateway may reject an executable intent only when it cannot prove factual correctness or an authoritative hard venue/account boundary would be violated.

## Status

Experimental Topstep-first implementation. Fresh installations create operator and learning jobs in a paused state. The profile makes no profitability, payout, unattended-operation, funded-account, or live-readiness claim.

Implemented:

- isolated Luna/Codex decision sessions, with explicit model/provider configuration and no silent downgrade;
- every-minute flat and positioned cognition by default, configurable as scheduling only;
- available-frame continuity with no five-frame or `state_complete` cognition prerequisite;
- strict `glitch.intent.v2` identity, schema, finite-number, and geometry validation;
- durable outbox, decisions, receipts, attempt records, and operator directives;
- nonblocking operator and learning launchers so model latency does not occupy native cron;
- `/trade`, `/pause_trading`, `/flatten_all`, `/topstep_status`, `/long`, `/short`, and bias controls;
- Sol debrief, hourly review, five-hour planning, and daily learning workers;
- canonical outcome-only durable learning;
- proposed-by-default cognitive overlays with an explicit activation switch;
- checksum-verified installation and supervised Hermes gateway.

Current gateway limitations remain authoritative: one configured account and contract, one entry tranche, no verified `MOVE_STOP`/`MOVE_TP`, manual account-policy evidence, no durable provider bracket ownership, and no complete payout lifecycle.

## Requirements

- A personal Windows device with the local `glitch-topstep` Node service installed and running.
- Hermes `0.18.2` or newer.
- OpenAI Codex OAuth authorized for the `glitch-topstep` profile, unless the operator explicitly configures another supported model/provider.
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

`/trade` enables scheduled Hermes cognition only. The Node gateway independently remains `disabled`, `shadow`, or `armed` according to explicit human configuration.

## Controls

- `/topstep_status` — gateway health, mode, account visibility, and Hermes job state.
- `/trade` — resume the minute operator and 15-minute learning launcher.
- `/pause_trading` — pause both jobs without altering provider-side protection.
- `/flatten_all` — pause cognition and submit one risk-reducing `EXIT` through the gateway contract.
- `/long`, `/short` — queue one operator-directed experiment for the next cycle; the gateway still verifies factual execution.
- `/bias_long`, `/bias_short`, `/bias_neutral` — soft one-cycle advisory.

## Updating

```powershell
hermes profile update glitch-topstep
powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\hermes\profiles\glitch-topstep\setup.ps1"
```

Authentication, `.env`, sessions, memory, state, ledgers, and existing enabled/paused job state are preserved. Distribution-owned files are replaced and checksum-verified.

## Documentation

- [`docs/AUTHORITY.md`](docs/AUTHORITY.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- [`docs/OUTCOME-CONTRACT.md`](docs/OUTCOME-CONTRACT.md)
- [`docs/HANDOFF.md`](docs/HANDOFF.md)
