# GTHP-028 — Neutral template placeholders and cycle delta audit

**Priority:** P1 (cognition)  
**Status:** planned  
**Depends on:** GTHP-025

## Problem

External review of `glitch-topstep-v8` confirms prompt doctrine improved (~8/10) but three gaps remain:

1. **Template shape:** removing `action`/`confidence` avoids NOTHING anchoring but may increase `intent_schema_invalid` when the model omits required core fields. Need neutral placeholders, not defaults.
2. **Behavioral inertia:** rebuild instructions alone do not force an explicit delta-vs-prior-frame audit or hypothesis lifecycle classification; `change_condition` text can still repeat across cycles.
3. **Residual confirmation language:** “honor prior change_condition” still reads like a prerequisite gate despite advisory doctrine.

## Scope

### Profile prompt / SOUL / skills

- [ ] `required_output_template`: include `action` and `confidence` as neutral placeholders (`<CHOOSE_FROM_supported_actions>`, `<0.0-1.0>`), never pre-filled `NOTHING`.
- [ ] `decision_audit.decisive_evidence`: require material changes since the immediately prior frame when `recent_frames` is non-empty.
- [ ] Classify prior hypothesis in audit text: `CONFIRMED | INVALIDATED | PARTIALLY_CONFIRMED | UNCHANGED`.
- [ ] Discourage repeating the same `change_condition` for more than two consecutive cycles inside the same structure.
- [ ] Replace “honor prior change_condition” with observational-only language; current-cycle setup may justify entry even when prior trigger was not satisfied.
- [ ] Clarify flat vs positioned actions: never `HOLD` while flat; never `NOTHING` while positioned.
- [ ] Reinforce `EXIT` / `target_intent_id` rules for multi-tranche books.

### Operations

- [ ] `safe-profile-update.ps1`: remove stale `direct-cycle.lock` when owner PID is dead (Windows update reliability). **Shipped in 0.1.28**; cognition items remain open.

## Non-goals

- Trade quotas or anti-abstention pressure.
- Worker gates on `decision_scores` or hypothesis labels.
- Gateway packet fixes (remain in issue #73).

## Acceptance

- Schema validity on flat NOTHING/HOLD/ENTER samples in unittest prompt fixtures.
- Manual replay shows fewer verbatim repeated `change_condition` strings across 5+ flat cycles in similar structure.
- Windows `safe-profile-update.ps1` succeeds when cron was running and owner PID was killed.

## Related

- #73 P1 packet data quality
- #74 P2 structural evidence
- #75 P3 calibration metrics
