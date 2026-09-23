# Revisão técnica de autorização — coorte estratificada v5.1

**Data:** 2026-09-02 (offline)  
**Escopo:** revisão pós-correção da seleção v5 — **não autoriza r14**  
**Artefatos:** manifest `stratified-cohort-manifest-v5.1-2026-09-02.json` · digest `11a45e8f5810ce1376ee45e286a6cd7ff1cad86967a649a93606e5feb0e4c941` · supersedes v5 (digest v5 nunca usado em replay)

## Veredito

| Dimensão | Status |
|----------|--------|
| Integridade técnica v5.1 (digest, verify, independência) | **READY** |
| Eficiência cognitiva vs v5 | **IMPROVED** — 2/2 espontâneos elegíveis da sessão 09-02 na fila (v5: 0/2) |
| Gate cognitivo agregado (pares bilaterais espontâneos) | **INSUFFICIENT_SAMPLE** (2/5 histórico mantido até replay) |
| Autorização r14 | **BLOCKED** — decisão humana separada |

**Veredito composto:** coorte v5.1 é a fila canônica para eventual replay; gate agregado permanece **INSUFFICIENT_SAMPLE**. Replay só após autorização explícita. Se pós-replay ainda não houver candidatos bilaterais, priorizar **nova sessão PRAC** (mais espontâneos, barras completas, diversidade) em vez de repetir seleção offline indefinidamente.

---

## 1. Correção vs v5

| Aspecto | v5 | v5.1 |
|---------|----|------|
| Política | `greedy_quota` (tag rank fixo) | `recency_first_spontaneous` |
| Espontâneos `prac_soak_2026_09_02` na fila | 0 | **2** (`cb1139d6`, `b7730ea3`) |
| `prac_directed_test` legado | 2 | **0** |
| Restart operacional (teste 06) | 1 | **1** |
| Envelopes | 7 | **9** |
| Verify | PASS 7/7 | **PASS 9/9** |

**Causa raiz v5:** `PRIORITY_TAGS` rankeava `operator_minute_frame` antes da recência; quota de 4 preenchida por frames overnight 09-01 antes dos espontâneos da sessão PRAC 09-02.

**Terceira linha manifest (`1a8dbc33`):** permanece fora da fila — `capacity_gate_pass: false` no inventário (não é defeito de seleção).

---

## 2. Digest e verify

| Verificação | Resultado |
|-------------|-----------|
| `digest-stratified-cohort.py` | SHA256 `11a45e8f…` |
| `verify-stratified-cohort.py` (sem skip) | **PASS 9/9** |
| `unique_snapshot_hashes` | **9/9** |

---

## 3. Classificação da fila

| # | frame_id | `chain_classification` | Conta para tese espontânea? |
|---|----------|------------------------|------------------------------|
| 1–2 | `…b7730ea3`, `…cb1139d6` | spontaneous_cognitive | **Sim** (sessão 09-02, manifest NOTHING) |
| 3–8 | overnight 09-01 | spontaneous_cognitive | **Sim** (legado, diversidade temporal) |
| 9 | `…c30de894` restart | prac_directed_execution | **Não** — evidência operacional teste 06 |

Testes 7–11 e timeout (teste 08, gate fail) permanecem fora da fila cognitiva — correto.

---

## 4. Contribuição cognitiva esperada pós-replay

| Categoria | Envelopes | Potencial gate |
|-----------|-----------|----------------|
| spontaneous_cognitive | **8** | até +8 observações; pares bilaterais dependem de `thesis_quality` pós-replay |
| prac_directed_execution | **1** | **0** para gate |
| Agregado pré-replay | — | **2/5** (histórico) |

**Expectativa realista:** 8 envelopes NOTHING espontâneos podem gerar mais `no_edge`/held — não garantem pares bilaterais. Se r14 não mover o gate, **não repetir seleção offline**; capturar nova sessão PRAC.

---

## 5. Decisão

| Ação | Permitida? |
|------|------------|
| Usar v5.1 como coorte canônica pré-replay | **Sim** |
| v5 | **superseded** (digest preservado, nunca executado) |
| r14 | **Não** sem autorização explícita |
| `next_authorized_run_id` | **null** |

**Sequência autorizada quando aprovado:** v5.1 → replay sequencial → QC/proveniência → novo gate.
