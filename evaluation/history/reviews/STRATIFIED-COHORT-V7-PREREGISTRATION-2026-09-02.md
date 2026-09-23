# Pré-registro coorte estratificada v7 — pendente nova sessão PRAC longa

**Status:** `pending_prac_session_long`  
**Criado:** 2026-09-02 (pós-decisão v6 gate)  
**Objetivo gate:** fechar gap **2/5 → ≥5/5** (v6 sozinha cap em **4/5**)

---

## Critério de sucesso da sessão PRAC longa

A sessão **só** avança para coorte v7 se produzir:

| Critério | Obrigatório |
|----------|-------------|
| Novos frames espontâneos | **≥3** |
| `capacity_gate_pass` | completo em cada um |
| Cadeia + hashes | íntegros (`chain_complete`, sem mismatch) |
| Diversidade | instrumento e/ou horário reais (MNQ/MES/MCL quando disponível) |
| Componentes congelados | **sem** alteração (prompt, adapter, registry, regras) |

**Se <3 elegíveis:** não inflar coorte artificialmente. Registrar limitação em auditoria e repetir coleta **somente com justificativa explícita**.

---

## Pré-condições

- [ ] Sessão PRAC **longa** com captura espontânea contínua
- [ ] **≥3** frames espontâneos com `capacity_gate_pass`
- [ ] Export `chain_complete: true`
- [ ] Ingest com path `state\minute-frames` (validar `frames_added` > 0)
- [ ] Diversidade: horário · MNQ/MES/MCL se disponível

---

## Política de seleção (rascunho)

| Regra | Valor |
|-------|-------|
| Base | `recency_first_spontaneous` |
| Exclusões | v2–v6 consumidos · `prac_directed_execution` |
| Mínimo envelopes | **3** elegíveis (meta gate) |
| Origem alvo | nova sessão PRAC (não reutilizar só diversity) |

---

## Campos a preencher pós-ingest

| Campo | Valor |
|-------|-------|
| `prac_session_id` | _TBD_ |
| `prac_ingest` | _TBD_ |
| `frames_added` | _TBD_ (deve ser > 0) |
| `eligible_spontaneous_count` | _TBD_ (≥3) |
| `envelope_count` | _TBD_ |
| `digest_sha256` | _TBD_ |

---

## Não fazer antes de v7

- Autorizar replay v6 **só** para gate (máx 4/5)
- Montar coorte com <3 elegíveis “para completar quota”
- Segunda sessão curta sem meta de ≥3 elegíveis

---

## Pós-sessão (ordem obrigatória)

```text
export válido (chain_complete)
  → ingest corrigido (state\minute-frames · frames_added > 0)
  → inventário de consumo (audit-prac-frame-consumption.py)
  → coorte v7 (somente se ≥3 elegíveis)
  → verify/digest
  → revisão técnica
  → autorização humana
  → replay sequencial
  → novo gate
```

## Avanço arquitetural pós-gate

```text
gate ≥5/5  → revisão qualitativa formal → agregador determinístico offline → auditoria → shadow controlado
gate <5/5  → nova coleta PRAC (sem reruns de baixo retorno)
```

**Ressalva:** `≥5/5` é **gate mínimo**, não prova de superioridade de perfil. Antes do agregador offline, confirmar:

- independência dos pares;
- estabilidade intra-perfil;
- ausência de viés de seleção;
- cobertura de instrumentos e regimes;
- correlação/diversidade entre perfis;
- custo e latência aceitáveis;
- revisão qualitativa das teses.

Até gate ≥5/5: agregador executável · paralelismo · shadow · promoção **bloqueados**.

---

## Referências

- Decisão v6: `V6-GATE-DECISION-2026-09-02.md`
- Auditoria diversity: `PRAC-DIVERSITY-FRAME-CONSUMPTION-AUDIT-2026-09-02.md`
- Sequência PRAC: `glitch-topstep/docs/evidence/PRAC-SESSION-SEQUENCE.md`
