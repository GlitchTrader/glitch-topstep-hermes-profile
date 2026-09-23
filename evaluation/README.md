# Evaluation lane

Machine-readable contracts and schemas used by the live evaluation / shadow / ensemble path stay at this root.

## Active (do not archive casually)

- Contracts: `capability-matrix.json`, `registry.json`, `ensemble_config.json`, `aggregator_rules.v1.json`, `packet_envelope_mapping.v1.json`, `evaluation_output_contract.v1.json`, `evaluation_cost_rates.v1.json`, `prac-live-ensemble-config.v1.json`, `shadow-live-*.json`, `gate-manifest.v1.json`, `deferred-data-quality-soak-lane.v1.json`, `sample_quality_gate.v1.json`
- Kits: `profiles/`, `schemas/`, `fixtures/`, `release/`
- Live regression fixtures in `runs/` (only the files listed in `runs/README.md`)
- Undated SPEC / runbook markdown that still describes current doctrine

## Historical

Dated one-shot runs, reviews, scenario version sprawl, Trail-A wave configs, and incident docs live under [`history/`](history/README.md).

Archived evaluation-wave scripts (H15): `scripts/archive/evaluation-waves/`.
