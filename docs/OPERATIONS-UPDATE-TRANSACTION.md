# Transactional profile update

`scripts/profile_update_transaction.py` is the fail-closed update boundary for
the installed `glitch-topstep` profile. It validates the package and paired
contract before swapping any distributed file, records normalized SHA-256
hashes, and stores the immediate rollback archive and receipts directly under
the existing `state/` directory. No new runtime tree is required.

The transaction allowlist comes from `distribution_owned` in
`distribution.yaml`. `.env`, `auth.json`, `config.yaml`, databases, WAL/SHM,
locks, logs, runtime, cache, sessions, memories, and the NT profile `glitch`
are always protected. Protection is case-insensitive and takes precedence over
`distribution_owned`, including for `config.yaml`, database sidecars, and
locks. Package paths are confined to the resolved Topstep root; traversal and
VCS checkout packages are rejected.

An existing update lock is never removed or overridden unconditionally. It
contains the PID, process-start identity, transaction ID, and owner. Recovery
removes it only when the known owner is confirmed and the recorded process is
dead or the PID has been reused with a different start identity. A live,
unverifiable, or differently owned lock blocks closed; PID alone is never
sufficient.

Every update, rollback, recovery, and command-line entry point performs the
read-only process inventory check. The protected NT `glitch` profile is
ignored only when its profile identity is explicit; an active Topstep process
or an ambiguous Hermes owner blocks the operation.

An interruption during the `applying` phase is detected by `recover` on the
next start and restored from the previous distributed archive. `verify` is
read-only. The regression suite exercises incompatible packages, hash drift,
interruption, repeated rollback, Windows-safe paths, user state preservation,
and rejection of the NT profile. Demonstrated rollback is fixture-only; no
real Hermes installation was updated by this change.
