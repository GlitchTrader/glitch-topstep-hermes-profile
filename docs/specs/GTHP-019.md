# GTHP-019 — Persistent wake triggers and durable changeWhen monitor

**Status:** open  
**Priority:** P1  
**Issue:** [#62](https://github.com/GlitchTrader/glitch-topstep-hermes-profile/issues/62)  
**Profile version target:** 0.1.21+  
**Depends on:** GTHP-009, GTHP-018  
**Gateway dependency:** `glitch-topstep:TS-R4-07` (fresh evidence for trigger evaluation)

## Problem

Fixed cron cadence misses fast regime changes. Glitch V2 `changeWhen` / wake triggers let Hermes run when evidence crosses thresholds. Profile references `active-wake-triggers.json` but durable evaluation between ticks is thin.

## Invariant

| Layer | Rule |
|-------|------|
| **Triggers** | Schedule **invocation** only; Hermes still decides action. |
| **Storage** | `supervisor/active-wake-triggers.json` survives restarts; schema versioned. |
| **Dedup** | Fired triggers respect cooldown window; events auditable. |
| **Quiescence** | GTHP-018 skip still applies when flat + quiescent unless trigger explicitly overrides (documented). |

## Acceptance

- Documented trigger schema (price, tape, DOM, session phase when TS-R4-07 lands).
- Monitor evaluates triggers against latest gateway packet/evidence.
- `wake_reason` recorded in `events.jsonl` on trigger-fired cycle.
- Tests for dedup, persistence, and positioned always-wake behavior.

## Stop line

No pre-baked ENTER/EXIT; no hidden strategy in trigger definitions.

## Related

- GTHP-018, GTHP-020
- `glitch-topstep:TS-R4-07`
- V2 `GLITCH_V2_MODIFICATIONS.md` wake / changeWhen sections
