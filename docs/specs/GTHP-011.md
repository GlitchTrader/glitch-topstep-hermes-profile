# GTHP-011 — Optimize direct-cycle LLM prompt payload

**Status:** planned  
**Priority:** P1 cost/latency + cognition focus  
**Profile version target:** 0.1.14+ (`prompt_version` bump to `glitch-topstep-v5` when implemented)  
**Depends on:** GTHP-009, GTHP-010, RAIL-009 (current `build_prompt` / `packet_for_model` baseline)

## Problem

The direct-operator cron (`run-topstep-cycle.py` → `build_prompt` → `hermes chat`) sends a single stdin message that is redundant and verbose relative to the static Hermes context (SOUL + five skills + optional memory turns).

Measured drivers (tokens ≈ chars/4):

| Layer | Typical size | Notes |
|-------|--------------|-------|
| Hermes static (SOUL + 5 skills) | ~6.3k tokens | Loaded every cycle via `--skills` |
| `build_prompt` instruction prose | ~716 tokens | Repeats SOUL/skills doctrine |
| `decision_packet` | ~1.1k–4.4k chars | Includes embedded `required_output_template` |
| `recent_frames` ×5 | ~12k–19k chars | Richest flat hotspot; full semantic packet per frame |
| `recent_glitch_ledger` tail 6 | ~0–30k chars | Decisions include full intent + `decision_audit` + long `reason` |
| Duplicate `required_output_template` | ~600 chars ×2 | Packet + envelope |
| `active_trade_state` | variable | Repeats `reason` already in ledger |

**Totals (stdin only):**

| Scenario | stdin tokens ~ |
|----------|----------------|
| Flat, empty ledger | ~4.5k |
| Active session (6 decisions with audit) | ~10k |
| Peak (rich packet + full ledger + positioned) | ~12.6k |

**Combined input per cycle (active session):** ~16–20k tokens before output and memory retrieval.

## Invariant (must not break)

- Hermes still receives enough evidence to honor accountable `change_condition` and `wake_triggers` on flat `NOTHING`.
- Positioned cycles retain depth for MOVE_STOP / MOVE_TP / EXIT / scale-in when `execution.supported_actions` allows.
- Worker still validates `glitch.intent.v2` locally; gateway pairing unchanged unless `prompt_version` v5 is coordinated.
- Optional skips (`GLITCH_TOPSTEP_SKIP_UNCHANGED_EVIDENCE`, stale gateway) remain operator controls, not prompt shrink substitutes.

## Architecture today

```
cron → run-topstep-cycle.py → build_prompt()
  ├─ instruction prose (doctrine)
  └─ CURRENT_CYCLE= JSON envelope
       ├─ decision_packet (+ template inside)
       ├─ recent_frames[5] (frame_snapshot.v2)
       ├─ recent_glitch_ledger (tail 6 decisions/receipts/outcomes)
       ├─ active_trade_state
       ├─ required_output_template (duplicate)
       └─ operator_authority

hermes chat: SOUL + skills + --toolsets memory + --max-turns 4
```

Key code: `scripts/run-topstep-cycle.py` (`build_prompt`, `recent_context`), `scripts/packet_model.py`, `scripts/parity.py`.

## Optimization plan (phased)

### Phase 0 — Baseline metrics (no behavior change)

- Log per-cycle: `len(prompt)`, section byte breakdown, flat vs positioned, repair (`STRICT_OUTPUT_CORRECTION`) rate.
- Sample ~20 live cycles → `docs/evidence/prompt-optimization-baseline.md`.

### Phase 1 — Quick wins (~40–50% peak stdin reduction, low risk)

| ID | Before | After | Est. saving |
|----|--------|-------|-------------|
| 1.1 | `required_output_template` in packet **and** envelope | Single copy in envelope only; `packet_for_model(drop_template=True)` | ~600 chars/cycle |
| 1.2 | ~716-token instruction repeating SOUL/skills | ~150-token wire contract (schema, preserved fields, `wake_triggers`, no prose) | ~500 tokens/cycle |
| 1.3 | `decisions` tail 6 with full intent + `decision_audit` | `decision_summary.v1`: action, confidence, `change_condition`, `wake_triggers`, key prices, `reason` capped ~200 chars | ~20–25k chars active session |
| 1.4 | Full `receipts` / `outcomes` tail 6 | Summary: `intent_id`, status, fill/rejection codes | ~2–5k chars |

**Target after Phase 1:** stdin ~10k → ~5–6k (active session).

### Phase 2 — Adaptive frames (~30% additional flat reduction)

| ID | Before | After |
|----|--------|-------|
| 2.1 | 5 full frames always | Flat default 2 frames; positioned 5 (`GLITCH_TOPSTEP_DECISION_FRAME_COUNT` / `_POSITIONED`) |
| 2.2 | `frame_for_model` copies 15 top-level packet keys | `compact` / `delta` mode: last, regime, order_flow windows, data_quality, position, protection |
| 2.3 | Same frame policy when `DATA_DEGRADED` | 1 frame + explicit degraded flag |

Proposed schema: `glitch.topstep.frame_snapshot.v3` with `mode: full | compact | delta`.

Env: `GLITCH_TOPSTEP_FRAME_MODE=compact`.

**Target after Phase 2:** flat stdin ~4.5k → ~2.5k.

### Phase 3 — Hermes static context (~35% static reduction)

| ID | Before | After |
|----|--------|-------|
| 3.1 | 5 skills every direct cycle | Drop `topstep-self-learning` from direct cron (keep on learning worker) |
| 3.2 | SOUL + skills repeat regime/geometry | SOUL = principles; skills = procedure; dedupe overlapping paragraphs |
| 3.3 | `--max-turns 4` + memory on flat | Flat: `max-turns 1`, no memory; positioned: `max-turns 2` + memory |

**Target:** static context ~6.3k → ~4k tokens; fewer hidden round-trips.

### Phase 4 — Smart ledger + trade state (validate in shadow)

| ID | Before | After |
|----|--------|-------|
| 4.1 | `active_trade_state` carries full `reason` | IDs, action, stop/target, active `change_condition` only |
| 4.2 | Fixed tail 6 | Flat tail 2 + accountable anchor; positioned tail 4 |
| 4.3 | Decisions and receipts separate | `continuity_anchor`: last declared `change_condition` + `wake_triggers` |

**Risk:** loss of entry narrative. **Mitigation:** always include one entry anchor when positioned.

## Consolidated targets

| Dimension | Today (v4, active) | After Phases 1–3 | Reduction |
|-----------|-------------------|------------------|-----------|
| stdin tokens | ~10k | ~3.5–4.5k | 55–65% |
| Hermes static | ~6.3k | ~4k | ~35% |
| Hermes turns | up to 4 | 1 flat / 2 positioned | 50–75% |
| **Total input/cycle** | **~16–20k** | **~7–8.5k** | **~50–60%** |

Secondary gains: less doctrine dilution, fewer schema repair loops, faster cycles when not skipped.

## Safeguards

- Regression tests on real `decisions.jsonl` tails (change_condition accountability).
- Golden prompt snapshots for flat / degraded / positioned packets.
- Shadow 48h: action distribution, confidence, repair rate must not worsen >10%.
- Bump `prompt_version` to `glitch-topstep-v5` when envelope shape changes; coordinate gateway if required.

## Suggested roadmap

| Week | Deliverable | Version |
|------|-------------|---------|
| 1 | Phase 0 + Phase 1.1–1.2 | v4.1 internal |
| 2 | Phase 1.3–1.4 ledger summary | v5 |
| 3 | Phase 2 adaptive frames | v5 |
| 4 | Phase 3 skills/turns + shadow | v5 |
| 5 | Phase 4 if shadow green | v5 stable |

## Evidence (when done)

- `scripts/run-topstep-cycle.py`
- `scripts/packet_model.py`
- `tests/test_direct_cycle.py`
- `docs/evidence/prompt-optimization-baseline.md`
- regenerated `SHA256SUMS`
