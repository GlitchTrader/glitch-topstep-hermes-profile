# Nota de revisão — gate bilateral vs perfis conservadores

**Data:** 2026-09-02  
**Contexto:** r14/r15/r16 · gate **2/5** · `insufficient_sample`

---

## Observação

O gate atual conta **pares bilaterais** onde baseline e structure divergem em classificação cognitiva comparável (`comparable_pair`). Em sessões com:

- `daily_capture_locked` / NOTHING live;
- diversidade fraca;
- perfis intencionalmente conservadores;

…a taxa de `no_edge` simétrico tende a **100%** (r15: 8/8, r16: 6/6). Isso é **compatível** com o desenho do gate, mas **não** distingue “perfis equivalentes e corretos” de “amostra insuficiente para tese direcional”.

---

## Adequação (provisória)

| Aspecto | Avaliação |
|---------|-----------|
| Gate bilateral para **bloquear promoção** sem evidência | **Adequado** |
| Gate bilateral como única métrica de “progresso” | **Limitado** para perfis conservadores |
| `≥5/5` como mínimo formal | **Mantido** — mas exige diversidade real na coleta |
| Substituir gate agora | **Não** — mudança de política exige revisão formal separada |

---

## Implicação para v9

A próxima PRAC deve priorizar condições onde **divergência bilateral é possível** sem forçar entradas:

- instrumentos com decisão real (não só observação no universo);
- horários e cenários distintos;
- janela longa o suficiente para ≥3 espontâneos elegíveis;
- barras 1m completas (`capacity_gate_pass`).

Métricas complementares (offline, não gate): taxa `no_edge` por instrumento/horário/completude — ver inventário pós-ingest v9.

**Agregador:** permanece spec/fixtures; não executar.
