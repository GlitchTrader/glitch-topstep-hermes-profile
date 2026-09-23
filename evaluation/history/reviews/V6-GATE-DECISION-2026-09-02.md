# Decisão — coorte v6 vs gate cognitivo

**Data:** 2026-09-02  
**Decisor:** Ari (recomendação aceita)  
**Gate atual:** `2/5` pares `thesis_quality` bilaterais

---

## Correção de ingest (confirmada)

`frames_added: 0` no primeiro ingest foi **path errado** (`minute-frames` sem `state/`), não duplicação nem consumo prévio. Re-ingest: **3 frames** adicionados. Ver `PRAC-DIVERSITY-FRAME-CONSUMPTION-AUDIT-2026-09-02.md`.

---

## Matemática do gate pós-v6

| Item | Valor |
|------|-------|
| Gate atual | **2/5** |
| Envelopes v6 elegíveis | **2** (`fedf09de`, `56090490`) |
| Excluído por capacidade | **1** (`8ff26413`) |
| Máximo teórico pós-replay v6 | **4/5** |
| Objetivo gate | **≥5/5** |

**Conclusão:** v6 é tecnicamente válida (verify 2/2), mas **insuficiente** para desbloquear o gate.

---

## Decisão

| Ação | Status |
|------|--------|
| Replay v6 para atingir `5/5` | **NÃO AUTORIZAR** |
| Replay v6 opcional (validação multi-instrumento / comportamento) | Adiado — não prioritário |
| `next_authorized_run_id` | **`null`** |
| Nova sessão PRAC longa antes de replay | **PRIORITÁRIO** |

v6 permanece **pré-registrada offline** como evidência e baseline de seleção; não consumir autorização de replay só para inflar invocações.

---

## Sequência eficiente (v7)

```text
ingest path corrigido (feito)
  → auditoria registrada (feito)
  → v6 pré-registrada (feito, sem replay gate)
  → nova sessão PRAC mais longa
  → ≥3 espontâneos elegíveis (capacity PASS)
  → export chain_complete
  → ingest (state\minute-frames)
  → coorte v7 offline
  → revisão técnica
  → autorização humana
  → replay sequencial
  → novo gate
```

### Prioridades na próxima sessão PRAC

- ciclos espontâneos (não só testes 6–11);
- ≥3 envelopes com `capacity_gate_pass`;
- MNQ, MES, MCL quando disponíveis;
- barras 1m fechadas · `state_complete`;
- horários distintos;
- export `chain_complete: true` **antes** de depender do cron para corpus.

---

## Paralelo seguro (sem replay)

- suporte seleção v6/v7;
- path ingest auditado (`run-prac-corpus-ingest.ps1` → `state/minute-frames`);
- métricas por instrumento nos 2 frames elegíveis v6;
- agregador: spec/fixtures congelados apenas.

---

## Bloqueios inalterados

Agregador executável · paralelismo Hermes · shadow · promoção
