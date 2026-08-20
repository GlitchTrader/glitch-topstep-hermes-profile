# GTHP-AUDIT-04 — Paired regression matrix (Hermes profile)

**Date:** 2026-08-20  
**Issue:** [#126](https://github.com/GlitchTrader/glitch-topstep-hermes-profile/issues/126)  
**Gateway companion:** TS-AUDIT-11 (#166)

| Audit item | Profile test file | Status |
|------------|-------------------|--------|
| GTHP-AUDIT-01 decision index | `tests/test_state_store.py` | green on main |
| GTHP-AUDIT-02 JSONL tail | `tests/test_jsonl_tail.py` | branch `feat/audit-02-03-persistence` |
| GTHP-AUDIT-03 outbox reconcile | `tests/test_direct_cycle.py` | branch `feat/audit-02-03-persistence` |
| GTHP-DATA-01 cognition | `tests/test_packet_model.py` | branch `feat/data-alignment-cognition-phase-c` |

CI entrypoint: `python -m unittest discover -s tests`.
