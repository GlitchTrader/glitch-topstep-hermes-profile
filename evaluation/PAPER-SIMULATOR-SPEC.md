# Paper simulator spec (offline)

**Schema:** `glitch.topstep.paper_simulation.v1`  
**Classification:** `paper_only=true` · `promotion_use_allowed=false`

## Inputs (recorded artifacts only)

| Artifact | Source |
|----------|--------|
| Sealed envelope / snapshot | Trail-a shadow JSON, sealed evaluation envelope |
| Six profile normalized outputs | Fixtures, cognitive replay artifacts |
| Aggregator selection | Precomputed or derived via `ensemble_aggregator` |
| Outcome chronology | `forward_observation`, minute-frame bars, `path_chronology` |

## Paper status enum

| Status | Meaning |
|--------|---------|
| `paper_expired` | Envelope TTL elapsed at simulation time |
| `paper_rejected` | Classified failure, incomplete geometry, or missing chronology |
| `paper_no_selection` | Aggregator abstained or conflicted |
| `paper_selected` | Selection resolved but path ambiguous or horizon-only |
| `paper_outcome` | Stop or target first-touch resolved with counterfactual P&L |

## Prohibitions (enforced in code)

No imports of gateway, ProjectX, outbox, intent, or production receipt paths. File paths and in-memory dicts only — no live network.

## Script

```powershell
python scripts/paper_simulator.py --envelope <path> --profiles <path> --frame <path> --output <path>
```

Tests: `python -m unittest tests.test_paper_simulator -v`
