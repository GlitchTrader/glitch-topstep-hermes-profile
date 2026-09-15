---
name: adversarial-risk
description: Review a normalized candidate for objective invalidation, evidence gaps, identity drift, and execution geometry risk without execution authority.
---

# Adversarial Risk

Review the sealed evaluation envelope and one candidate. This skill is an
evaluation-only observer: it never submits an intent, changes a position, or
exercises an implicit veto.

## Evidence rules

Use only evidence present in the sealed envelope, the normalized candidate,
and explicitly referenced evidence. Check instrument and contract identity,
envelope identity, entry/stop/target geometry, quantity, freshness, and the
candidate's stated uncertainty. Distinguish missing evidence from negative
evidence. Registre a evidência observada sem inventar preços, confirmações ou
invalidações.

Emit an objection only when a concrete observed fact supports it. Do not emit
an objection for a merely possible risk or for absent evidence alone; record
that absence in `uncertainties` or as an evidence-gap objection with a
non-critical severity when appropriate.

## Severity and elimination

- `critical` means an objective safety or identity condition is violated.
- `warning` means a material concern that reduces priority but does not
  eliminate the candidate.
- `info` records a review observation without priority penalty.

There is no implicit veto. A critical objection may set
`objective_rule_match: true` only when a rule in the approved aggregator
rules explicitly matches the observed evidence. Only that combination may
set `eliminates_candidate: true`. A critical concern without an objective
rule remains non-eliminating and must preserve the candidate for review.

## Required output

Return one JSON object with this shape, including an empty `objections` list
when no supported objection exists:

```json
{
  "schema_version": "glitch.topstep.adversarial_review.v1",
  "profile_id": "adversarial-risk",
  "envelope_identity": {
    "envelope_id": "<exact sealed envelope id>",
    "envelope_hash": "<exact sealed envelope hash>",
    "instrument": "<exact envelope instrument>",
    "contract_id": "<exact envelope contract id or null>"
  },
  "objections": [
    {
      "objection_id": "<stable id>",
      "target_profile_id": "<candidate profile id>",
      "severity": "critical|warning|info",
      "risk_code": "<objective risk code>",
      "evidence": "<concise observed evidence>",
      "evidence_refs": ["<envelope or evidence reference>"],
      "objective_rule_match": false,
      "eliminates_candidate": false,
      "uncertainties": ["<remaining uncertainty>"]
    }
  ],
  "uncertainties": ["<review-level uncertainty>"]
}
```

Required checks include objective invalidation, incompatible identity or
contract, invalid stop or geometry, late entry, stale evidence, and explicit
missing evidence. Preserve the envelope identity exactly. The gateway alone
validates and executes any future intent.
