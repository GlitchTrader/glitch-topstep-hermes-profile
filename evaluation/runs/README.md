# Active evaluation run fixtures

Regression fixtures still referenced by tests / audits remain here:

- `scenario-live-2026-09-01-r7-contract.json` (+ companion `r7-contract-*` invocation artifacts)
- `scenario-live-2026-09-01-r8-contract.json` (+ companion `r8-contract-*` artifacts)
- `scenario-live-2026-09-01-r9-v2.json` (+ companion `r9-v2-*` artifacts)
- `frozen-cohort-manifest-2026-09-14-adversarial-risk.json`

`audit-profile-registry.py` also falls back to `evaluation/history/runs/` when resolving invocation basenames.

All other dated run artifacts are under `evaluation/history/runs/`.
Do not commit test-generated `parallel_slots/` or `test-*.json` here — use a temp dir.
