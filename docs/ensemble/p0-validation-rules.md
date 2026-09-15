# Ensemble P0 validation slice

This evaluation-only slice makes the existing Hermes ensemble gates explicit and deterministic. The aggregator preserves every normalized candidate and objection for audit, while selecting only among candidates that share the sealed envelope identity and compatible contract identity.

- `version_incompatible`, expired envelopes, global timeout, and process failures remain `classified_failure`.
- Individual timeout, delayed output, invalid output, `missing_required_evidence`, and absent profiles remain attributable states; none is converted to `no_edge` or `NOTHING`.
- Exact instrument spelling, contract identity and generation, quantity, direction, entry, stop, and target are validated before grouping; a missing announced contract field is incompatible.
- Critical `adversarial-risk` objections eliminate a candidate only when an approved objective rule matches. Other objections remain audit-visible and non-eliminating.
- Candidate ordering is normalized by profile and invocation identifiers. The profile remains evaluation-only; the gateway remains the sole validator and executor.
