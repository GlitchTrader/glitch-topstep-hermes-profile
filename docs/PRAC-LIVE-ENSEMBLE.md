# Hermes ensemble runner

`scripts/prac_live_ensemble.py` is the explicit runner for one common gateway packet and six Hermes profiles:

`baseline-current`, `structure`, `adversarial-risk`, `smart-money`, `indicators`, `orderflow`.

The runner seals one envelope, invokes profiles with at most two slots, preserves every normalized evidence state, and calls the deterministic aggregator once. Only the resulting global decision can reach the gateway adapter. The profile has no ProjectX client or ProjectX credential path.

Modes are intentionally separate:

- `offline --packet <file>`: fixture-only; no gateway reads or writes.
- `shadow`: authenticated packet observation and cognition; delivery is structurally disabled.
- `prac_live --authorize`: the only mode permitted to call gateway `/intent`; gateway remains the final validator and must confirm receipt and protection.

Example invocation for the next operator-controlled preflight is:

```powershell
python scripts/prac_live_ensemble.py --mode prac_live --authorize --output docs/evidence/<session>/runner.json
```

This implementation stage did not run that command. It did not start PRAC, invoke the live gateway, create an intent, send an order, or reset an account.

The runner fails closed for incomplete state, missing quote, expired snapshot, closed-bar evidence missing, contract divergence, missing profiles, profile timeout/error, ambiguous receipts, missing stops, and a second active exposure. Reset eligibility requires flatten, reconciliation, no pending orders, persisted receipts, and persisted outcomes.
