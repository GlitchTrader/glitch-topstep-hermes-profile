# Offline runner evidence — 2026-09-10

- Runner: `scripts/prac_live_ensemble.py`
- Modes implemented: `offline`, `shadow`, `prac_live`
- Profiles: six required Hermes profiles
- Parallel slots: maximum 2
- Offline integration: PASS; two frozen frames processed by the existing parallel ensemble package.
- Orders/intents: 0
- Resets: 0
- Gateway calls: 0
- Live Hermes: not started
- PRAC: not started

The integration artifact is [parallel-run.json](parallel-run.json). It contains the six-profile manifest and offline selections. The full unittest command executed 708 tests; 691 passed and 11 were skipped, while 6 pre-existing environment tests errored when they attempted to access the locked global Hermes evaluation directory under `%LOCALAPPDATA%`. The new runner tests passed independently.

Classification: `runner_implemented_ready_for_live_preflight` for code handoff, with the existing global Hermes-directory permission issue recorded as an environment limitation rather than a runner safety failure.
