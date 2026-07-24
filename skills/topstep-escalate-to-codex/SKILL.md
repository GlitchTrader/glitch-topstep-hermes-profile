---
name: topstep-escalate-to-codex
description: Turn a Topstep supervisor system finding into a bounded, approval-gated build request.
---

# Escalate to Codex

Use only from Hermes chat when analysis shows a source-controlled change is needed in the
`glitch-topstep` profile or the local Node gateway.

1. Record the finding in `state/supervisor/build-requests.jsonl` or the hourly review `system_findings`.
2. Append one `glitch.topstep.supervisor.build_request.v1` record with status `proposed`.
3. State the exact files/scope, acceptance criteria, evidence, and rollback.
4. Wait for explicit user approval before changing status to `approved`.

An approved request is available to a separately invoked builder. It does not schedule Codex,
run trading cycles, poll market data, or imply approval from a recommendation. Hermes trading
remains independent while a request is pending or being built.
