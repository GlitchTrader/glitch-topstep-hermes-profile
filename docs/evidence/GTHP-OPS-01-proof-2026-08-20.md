# GTHP-OPS-01 — learner preemption and status (2026-08-20)

Proof for profile issue #106 (MVP operational slice; #98/#100 remain open).

## Implemented

| Requirement | Evidence |
|-------------|----------|
| `running` status at start | `run-topstep-learning.py` writes `learning-worker-status.json` before work |
| Trading priority | Defers with `status=deferred` when `direct-cycle.lock` exists |
| Status in `/topstep_status` | `plugins/topstep-control/__init__.py` → `_learning_worker_status()` |
| Preempted on lock fail | Existing `preempted` path preserved |

## Tests

- `tests/test_learning.py::test_main_defers_when_direct_cycle_lock_is_active`
- `tests/test_control_plugin.py::test_learning_worker_status_is_exposed`

## Residual

Full indexed bounded retry state (#98) and worker decomposition (#100) tracked separately.
