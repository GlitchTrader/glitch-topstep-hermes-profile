# GTHP-AUDIT-04 — Hermes workflow decomposition baseline

**Date:** 2026-08-20  
**Issue:** [#124](https://github.com/GlitchTrader/glitch-topstep-hermes-profile/issues/124)

| Module | Role |
|--------|------|
| `scripts/workflows/delivery_recovery.py` | Delivery result classification |
| `scripts/workflows/intent_outbox.py` | Outbox pending/prune/discard |
| `scripts/workflows/gateway_session.py` | Delivery wire + POST /intent |
| `scripts/workflows/decision_journal.py` | Indexed decisions writer |
| `scripts/workflows/cognition_prompt.py` | Cycle context assembly |

`parity.py` re-exports workflow APIs for backward compatibility. Regression: `tests/test_workflow_modules.py`.
