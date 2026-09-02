# Fase 5 — Revisão de adequação de amostra

**Data:** 2026-09-02  
**Escopo:** r7, r10, r11, r12-v2, r13-v3, r14, r15, r16, r17 · pós-fechamento r17  
**Gate oficial:** **não alterado** neste documento (`2/5` · `insufficient_sample`)

---

## Veredito

### **Opção B — revisão da estratégia de medição**

A evidência acumulada (7 replays consecutivos sem novo par bilateral desde r10; abstinência simétrica em r15/r16/r17; 100% MNQ; pares válidos apenas no corpus inicial dirigido) indica que **a captura atual não produz oportunidades bilaterais observáveis** e que os perfis **abstêm de forma consistente** em condições PRAC recentes. Uma PRAC mais longa **sem** mudança de política de medição tem baixa probabilidade de fechar o gate — e violaria o critério de encerramento se repetir `0` pares.

**Opção A** (nova coleta limitada) **não** é recomendada como próximo passo automático. Permanece como contingência **somente** com override humano explícito e critérios v10 pré-registrados (ver anexos).

---

## Bloco 1 — auditorias (somente leitura)

### 1. Consolidação r7→r17

**Artefato:** `evaluation/runs/phase-5-run-consolidation-audit-2026-09-02.json`  
**Comparação multi-run:** `evaluation/runs/evaluation-runs-comparison-phase5-2026-09-02.json`

| Run | Inv | Frames | Pares bilaterais | `no_edge` baseline | `no_edge` structure | Divergências categoria | Custo USD | p50 ms |
|-----|-----|--------|------------------|--------------------|-----------------------|------------------------|-----------|--------|
| r7 | 6 | 3 | **1** | 0 | 1 | 2 | 0.008 | 6 187 |
| r10 | 14 | 7 | **1** | 4 | 5 | 2 | 0.160 | 12 680 |
| r11 | 12 | 6 | 0 | 6 | 5 | 1 | 0.135 | 13 578 |
| r12-v2 | 18 | 9 | 0 | 7 | 6 | 3 | 0.203 | 11 038 |
| r13-v3 | 16 | 8 | 0 | 5 | 7 | 3 | 0.181 | 12 359 |
| r14 | 18 | 9 | 0 | 9 | 8 | 1 | 0.203 | 11 679 |
| r15 | 8 | 4 | 0 | 4 | 4 | 0 | 0.091 | 12 523 |
| r16 | 6 | 3 | 0 | 3 | 3 | 0 | 0.067 | 11 976 |
| r17 | 8 | 4 | 0 | 4 | 4 | 0 | 0.089 | 11 508 |
| **Σ** | **106** | **53** | **2** | **42** | **43** | **12** | **~1.00** | **11 812** |

**Pares bilaterais válidos (único numerador do gate):**

| Run | frame_id | baseline | structure | `thesis_delta` |
|-----|----------|----------|-----------|----------------|
| r7 | `20260831T173427Z-4ac91997` | thesis_quality | thesis_quality | true |
| r10 | `20260901T143431Z-534fefd5` | thesis_quality | thesis_quality | true |

**`candidate` / `missing_required_evidence`:** 5 `candidate` baseline (r7+r13); 2 structure; **0** `missing_required_evidence` em todo o corpus consolidado.

**Instrumento:** MNQ **106/106** invocações.

**Completude:** runs recentes (r15–r17) com `indicators/ohlc/structure: partial`; `capacity_gate_comparable: true` — gate OK, mas não gera tese bilateral sob lock NOTHING.

**Janelas PRAC recentes:** r15 `15Z` · r16 `17Z` · r17 `18Z` — faixas estreitas, tag única (`operator_minute_frame` em r17).

---

### 2. Validação artefatos canônicos r17

**Artefato:** `evaluation/runs/phase-5-r17-canonical-validation-2026-09-02.json` · **all_ok: true**

| Check | Status |
|-------|--------|
| QC checklist preenchido | PASS |
| Proveniência / digest pin | PASS |
| Registry `stop_reruns` v9 | PASS |
| `next_authorized_run_id` | **null** |
| Gate pós-r17 | **2/5** |

---

### 3. Adequação do gate (sem alteração oficial)

**Artefato:** `evaluation/runs/phase-5-gate-adequacy-audit-2026-09-02.json`

| Pergunta | Resposta |
|----------|----------|
| `thesis_quality` bilateral observável com taxa atual de `no_edge`? | **Não** (~81% no_edge; 0 pares novos em 7 runs) |
| Frames espontâneos por par válido? | **~26.5** histórico; **∞** efetivo pós-r10 (0 pares / 39 frames) |
| Captura atual oferece oportunidades suficientes? | **Não** para gate bilateral sob condições PRAC v7–v9 |
| `no_edge` exige trilha diagnóstica própria? | **Sim** (offline, não gate de promoção) |

---

### 4. Testes

```text
534 testes executados · 533 PASS · 1 FAIL (pré-existente)
FAIL: test_sha256sums.Sha256sumsTests.test_manifest_matches_files
      mismatch: tests/fixtures/frozen_corpus/enriched/manifest.json
```

Não relacionado a r17 nem a este pacote de decisão. Corrigir SHA256SUMS em trilha separada.

---

## Bloco 2 — decisão técnica (Opção B)

### Por que não Opção A agora

| Critério Opção A | Situação atual |
|------------------|----------------|
| Janela maior | v9 foi curta (~22 min), mas r14 teve 9 envelopes e **0** pares |
| Dois períodos distintos | r15/r16/r17 já cobriram horas distintas — mesmo resultado |
| Instrumentos naturais | MNQ only em 106/106; multi-instrumento no packet não vira decisão |
| Barras completas | capacity PASS; abstinência persiste |
| ≥3 espontâneos elegíveis | v9 atingiu 4 — **0** pares |
| Sem cherry-pick | política respeitada; resultado ainda nulo |

**Conclusão:** mais volume na **mesma** estratégia de medição não justifica nova cadeia PRAC→replay sem revisão de política.

### Entregáveis Opção B (preparados, gate inalterado)

| Item | Proposta |
|------|----------|
| Métrica de qualidade de abstinência | taxa de alinhamento bilateral `no_edge`/`no_edge` vs divergência categoria |
| Cobertura `no_edge` | por perfil, instrumento, tag, completude, janela UTC |
| Disponibilidade de evidência | matriz `completeness` × `capacity_gate` × decisão live |
| Prudência vs ausência de oportunidade | classificador offline: lock NOTHING / partial evidence / homogeneidade de tag |
| Novo critério de amostra | submeter a aprovação humana **antes** de coleta v10 ou replay |

**Proibido nesta fase:** converter `no_edge` em `thesis_quality`; alterar prompts/adapter/registry.

### Sequência após veredito (Opção B)

```text
fechar fase de coleta atual (STOP_RERUNS v2–v9 formalizado)
→ aprovar nova política de medição (humano)
→ atualizar plano e gate (revisão formal separada)
→ só então iniciar nova coleta/replay
```

### Critério de encerramento (reforço)

Se, após override humano para uma coleta limitada v10, houver **novamente 0 pares novos**:

```text
PARAR cadeia PRAC → rerun
→ exigir decisão formal sobre métrica de abstinência
   OU sobre forma de gerar evidência espontânea válida
```

---

## Anexos preparados (contingência Opção A — não autorizados)

| Documento | Uso |
|-----------|-----|
| `evaluation/reviews/V10-PRAC-SESSION-OPERATOR-CHECKLIST-2026-09-02.md` | checklist operacional **se** humano reverter para coleta |
| `evaluation/reviews/V10-PRAC-SESSION-REPORT-TEMPLATE-2026-09-02.md` | relatório pós-sessão v10 |
| `evaluation/reviews/STRATIFIED-COHORT-V10-PREREGISTRATION-2026-09-02.md` | ingest/inventário/seleção offline |

**Status v10:** pré-registro offline apenas · **sem sessão iniciada** · **sem replay autorizado**

---

## Bloqueios mantidos

```text
agregador executável
paralelismo Hermes
shadow / paper / canary
promoção
repetir v9
```

---

## Addendum pós-`PRAC-LIMITED-2026-09-02` (2026-09-02)

**Status:** coleta limitada única **encerrada** · fechamento analítico completo.

| Métrica pós-limitada | Valor |
|----------------------|-------|
| Frames adicionais | +8 (total corpus ~61) |
| Novos pares direcionais | **0** |
| Abstinências produção | 8 (`NOTHING`) |
| `daily_capture_locked` citado | 7/8 |
| Limitação evidência captura | 8/8 (3 gateway degradado · 5 barra lag/partial) |
| Outcomes abstinência (proxy 15m) | 7/8 sem replay |
| Gate v1 | **2/5** (inalterado) |

**Veredito reconfirmado:** Opção B — **encerrar coleta direcional**. Replay r18 **não** recomendado para abstinência (outcomes já calculados).

Artefatos: `evaluation/runs/measurement-adequacy-update-post-limited-2026-09-02.json` · `evaluation/reviews/LIMITED-2026-09-02-EXECUTIVE-DECISION-REPORT.md`

---

## Referências

- `evaluation/runs/phase-5-run-consolidation-audit-2026-09-02.json`
- `evaluation/runs/phase-5-gate-adequacy-audit-2026-09-02.json`
- `evaluation/runs/phase-5-r17-canonical-validation-2026-09-02.json`
- `evaluation/reviews/R17-ABSTENTION-ANALYSIS-2026-09-02.md`
- `evaluation/reviews/BILATERAL-GATE-REVIEW-NOTE-2026-09-02.md`
- `evaluation/GATE_STATUS.md`
