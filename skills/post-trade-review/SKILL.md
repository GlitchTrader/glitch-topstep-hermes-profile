---
name: post-trade-review
description: Structured debrief from canonical trade outcomes and decision episodes without auto-trading from review scores.
---

# Post-Trade Review

Use canonical `glitch.topstep.trade_outcome.v1` rows and decision episodes. Outcomes outrank memory.

1. Separate execution fidelity (fills, protection, rejection) from directional outcome.
2. Never promote armed mode or size changes from debrief scores alone.
3. Propose cognitive overlays only through the existing candidate pipeline with evidence thresholds.
4. Reference `outcome_execution` geometry when present; do not invent fills.

This skill supports GTHP-012 learning loops; it does not submit intents.
