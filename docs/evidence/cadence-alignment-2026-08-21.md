# Cadence policy alignment — 2026-08-21

**Authority:** `paired-contract.json` → `distributed_contract.cadence` (5 min flat / 1 min positioned). No paired-contract version bump.

## Problem

Worker default `GLITCH_TOPSTEP_FLAT_DECISION_INTERVAL_MINUTES` was `1` while contract, `operator.json`, `.env.EXAMPLE`, and `run-wake-trigger-monitor.py` already documented `5`. Docs (`ARCHITECTURE.md`, `AUTHORITY.md`, `GTHP-009.md`) still said flat LLM every minute.

## Fix

- `scripts/run-topstep-cycle.py`: default flat interval `5` (env override unchanged).
- Docs aligned: worker wakes every minute; flat LLM at 0/5/10/…; positioned LLM every minute; wake/manual anticipate only.
- Tests cover default 5, env `=1`, off-cadence skip, wake/directive anticipation, frame capture without LLM, pending outbox not blocked by cadence.

## Cost impact (upper bound, flat RTH)

| Mode | Before (worker default 1) | After (contract default 5) |
|------|---------------------------|----------------------------|
| Flat LLM calls/hr | 60 max | 12 max |
| Positioned LLM calls/hr | 60 | 60 |
| Learning supervisor | conditional on new outcomes | unchanged |

Frame capture remains 60/hr regardless; only LLM invocation cadence changes.
