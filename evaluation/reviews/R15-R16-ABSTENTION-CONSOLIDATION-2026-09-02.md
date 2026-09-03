# Consolidação r15/r16 — evidência de abstinência

**Data:** 2026-09-02  
**Escopo:** replays v7 (r15) e v8 (r16) · **não** evidência de superioridade de perfil

---

## Resumo

| Run | Coorte | Invocações | `no_edge` | `comparable_pair` | Gate |
|-----|--------|------------|-----------|-------------------|------|
| r15 | v7 · 4 env | 8/8 | **8/8 (100%)** | 0/4 | 2/5 |
| r16 | v8 · 3 env | 6/6 | **6/6 (100%)** | 0/3 | 2/5 |

**Leitura:** ambos os perfis (`baseline-current`, `structure`) **abstiveram** de forma comparável em contextos MNQ com decisão live NOTHING / daily-capture lock. Isso é evidência de **comportamento conservador consistente**, não de que um perfil supera o outro.

---

## `no_edge` por dimensão observável

| Dimensão | r15 | r16 |
|----------|-----|-----|
| Instrumento (decisão) | MNQ (100%) | MNQ (100%) |
| Faixa horária (frame_id) | hora 15 UTC | hora 17 UTC |
| `normalized_comparability` | comparable 8/8 | comparable 6/6 |
| `capacity_gate_comparable` | true 8/8 | true 6/6 |
| Bilateral divergente | **0** | **0** |

Observação multi-instrumento no packet (MNQ/MES/MCL) **não** produziu decisões multi-instrumento — ver `V8-MULTI-INSTRUMENT-OBSERVATION-REVIEW-2026-09-02.md`.

---

## O que isto prova vs. não prova

| Prova | Não prova |
|-------|-----------|
| Infra mede e isola corretamente | Superioridade baseline vs structure |
| Perfis conservadores abstêm sob lock/captura | Diversidade de cenário |
| Gate bilateral permanece insuficiente | Que mais reruns no mesmo corpus ajudem |

---

## Política

```text
STOP_RERUNS v7 — fechado (r15)
STOP_RERUNS v8 — fechado (r16)
Próximo: PRAC diversa → coorte v9
Agregador: spec/fixtures apenas
```
