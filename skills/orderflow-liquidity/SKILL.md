---
name: orderflow-liquidity
description: Interpret tape and optional DOM windows from the packet without turning flow into entry gates.
---

# Order Flow and Liquidity

Use only `decision_packet.order_flow` and quote geometry. This skill never emits an intent or blocks `ENTER_*`.

1. Read rolling windows (15s, 60s, 300s) for trade count, delta, and last trade age when present.
2. Treat `order_flow.observation.depth.available=false` or inconsistent bid/ask as **unknown book**, not a veto.
3. Describe absorption, initiative, and imbalance as **evidence for thesis**, not permission.
4. Never infer hidden liquidity or off-book size.

Pass compact flow context to thesis and risk: tape bias, staleness, depth availability, contradictions.
