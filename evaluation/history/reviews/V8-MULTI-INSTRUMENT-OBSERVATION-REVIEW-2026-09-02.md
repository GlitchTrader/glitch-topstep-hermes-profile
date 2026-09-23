# Revisão observação multi-instrumento vs decisão — coorte v8

**Data:** 2026-09-02  
**Sessão:** `PRAC-SOAK-2026-09-02-v8`  
**Objetivo:** confirmar que observação multi-instrumento no packet **não** é confundida com decisões multi-instrumento.

---

## Conclusão

**PASS com ressalva documental.** Os 3 frames carregam `market_universe.candidates` com **MNQ, MES, MCL** (observação comparável do universo), mas cada ciclo de decisão permanece em **escopo single-position MNQ** com `action: NOTHING`. Não há evidência de decisão multi-instrumento nem exposição simultânea.

---

## Por frame

| frame_id | `packet.instrument` | `selected_instrument` | `universe.candidates` | `simultaneous_exposure` | chain `action` |
|----------|-------------------|----------------------|------------------------|-------------------------|----------------|
| `20260902T171541Z-4fdd308c` | MNQ | MNQ | MNQ, MES, MCL | `false` | NOTHING |
| `20260902T172046Z-86a52bbc` | MNQ | MNQ | MNQ, MES, MCL | `false` | NOTHING |
| `20260902T172547Z-c62a7390` | MNQ | MNQ | MNQ, MES, MCL | `false` | NOTHING |

---

## Distinção operacional

| Camada | O que contém | Interpretação para gate |
|--------|--------------|-------------------------|
| `market_universe.candidates[]` | Barras/features por instrumento elegível | **Observação** — suporte a ranking/scanner; não implica trade em MES/MCL |
| `account_selection` | `mode: single_active_position`, `selected_instrument: MNQ` | **Decisão** limitada a um instrumento ativo |
| `decision_scope` / chain manifest | Um `packet_id` → um intent MNQ | **Uma decisão por ciclo** |
| Receipts exportados | Flat · NOTHING | Sem mutação venue |

**Risco de confusão:** contar MNQ+MES+MCL como “diversidade de instrumento” na coorte v8. **Rejeitado** — diversidade de instrumento na coorte permanece **fraca** (decisões 3/3 MNQ).

---

## Implicação para replay

- Replay mede resposta cognitiva aos **mesmos 3 packets MNQ**.
- Pares bilaterais, se existirem, refletem divergência baseline↔structure no mesmo contexto MNQ/NOTHING — **não** diversidade multi-instrumento.
- Se pós-replay `comparable_pair_count = 0`: retornar à coleta PRAC com diversidade real (instrumento, horário, cenário).
