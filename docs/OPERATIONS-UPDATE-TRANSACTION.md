# Transactional profile update

`scripts/profile_update_transaction.py` is the fail-closed update boundary for
the installed `glitch-topstep` profile. It validates the package and paired
contract before swapping any distributed file, records normalized SHA-256
hashes, and stores the immediate rollback archive and receipts directly under
the existing `state/` directory. No new runtime tree is required.

The transaction allowlist comes from `distribution_owned` in
`distribution.yaml`. `.env`, `auth.json`, `config.yaml`, databases, WAL/SHM,
locks, logs, runtime, cache, sessions, memories, and the NT profile `glitch`
are always protected. An existing update lock is never removed or overridden.

An interruption during the `applying` phase is detected by `recover` on the
next start and restored from the previous distributed archive. `verify` is
read-only. The regression suite exercises incompatible packages, hash drift,
interruption, repeated rollback, Windows-safe paths, user state preservation,
and rejection of the NT profile. Demonstrated rollback is fixture-only; no
real Hermes installation was updated by this change.
