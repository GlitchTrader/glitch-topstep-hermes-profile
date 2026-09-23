# Revisão técnica de autorização — coorte estratificada v5

**Data:** 2026-09-02 (offline)  
**Escopo:** integridade pré-registro v5 — **não autoriza r14** nem altera `next_authorized_run_id`  
**Artefatos:** manifest `stratified-cohort-manifest-v5-2026-09-02.json` · digest `72a86059c4eb2ded146d25423195b2d674fe89ccb0ec3dd4af4be45dc62c6d04` · ingest `prac-corpus-ingest-PRAC-SOAK-2026-09-02.json`

## Veredito

| Dimensão | Status |
|----------|--------|
| Integridade técnica da coorte v5 (digest, verify, independência) | **READY** |
| Gate cognitivo agregado (pares comparáveis espontâneos) | **INSUFFICIENT_SAMPLE** (2/5 mantido) |
| Autorização de execução r14 | **BLOCKED** — `r14_authorization: pending_explicit_human_approval` |

**Veredito composto para esta revisão:** `INSUFFICIENT_SAMPLE` — coorte v5 está tecnicamente pré-registrada e verificável, mas a amostra efetiva para qualidade cognitiva permanece abaixo do mínimo (5 pares independentes). **Não autorizar r14** nesta rodada.

---

## 0. `manifest_row_count: 3` vs testes 6–11

| Artefato | Contagem | Interpretação |
|----------|----------|---------------|
| Testes dirigidos 6–11 | **6/6 PASS** | Evidência operacional (`prac_directed_execution`); JSONs preservados em `docs/evidence/PRAC-SOAK-2026-09-02/` |
| `evidence-chain-manifest.json` (export) | **3 linhas** | Somente decisões/receipts **espontâneas** na janela `since_utc: 2026-09-02T11:27:43.244Z` |
| `session-finalize.json` | `chain_complete: true`, `validation.valid: true` | Cadeia operacional íntegra — **não** implica 3 novas observações cognitivas comparáveis |

Os seis testes foram executados e documentados. O export filtra intents dirigidas fora do manifest cognitivo. As três linhas são três cadeias NOTHING espontâneas com `directed_test_id: null` — prova de join decision↔receipt, não incremento automático do gate 5 pares.

---

## 1. Digest, hashes e timestamps

| Verificação | Resultado |
|-------------|-----------|
| `digest-stratified-cohort.py` (re-run 2026-09-02) | SHA256 `72a86059…` — **idêntico** ao digest registrado |
| `verify-stratified-cohort.py` (sem `--skip-validation`) | **PASS 7/7** |
| `unique_snapshot_hashes` | **7/7** — sem colisão |
| `envelope_hash` por fila | Presente em todos os envelopes |
| Janela PRAC ingest | `since_utc: 2026-09-02T11:27:43.244Z` |
| `chain_complete` no ingest | **true** (cadeia operacional apenas) |

**Nota:** dois envelopes `prac_directed_test` legados exibem `manifest_trust: degraded_metadata` por `manifest_snapshot_hash_stale` — hash **computado** coincide com o manifest v5; não bloqueia verify offline.

---

## 2. Classificação das 3 linhas do manifest exportado

| # | packet_id | action | `directed_test_id` | `join_status` | Classificação revisão |
|---|-----------|--------|-------------------|---------------|----------------------|
| 1 | `cb1139d6-…` | NOTHING | `null` | NOTHING | **spontaneous_cognitive** (`operator_minute_frame`) |
| 2 | `1a8dbc33-…` | NOTHING | `null` | NOTHING | **spontaneous_cognitive** (`operator_minute_frame`) |
| 3 | `b7730ea3-…` | NOTHING | `null` | NOTHING | **spontaneous_cognitive** (`operator_minute_frame`) |

Todas as três linhas estão corretamente classificadas como espontâneas (sem `directed_test_id`). No enriched corpus correspondem a `chain_classification: spontaneous_cognitive` com `join_status: NOTHING`.

### Testes 6–11 (evidência operacional, não manifest)

| test_id | arquivo | classificação ingest / operador | Candidato cognitivo? |
|---------|---------|--------------------------------|----------------------|
| 6 | `test-06-restart-bracket.json` | `prac_directed_execution` | **Não** — frame restart na coorte v5 (#7) |
| 7 | `test-07-intent-delivery.json` | `prac_directed_execution` | **Não** — prova entrega de intent |
| 8 | `test-08-timeout-mutation.json` | `prac_directed_execution` | **Não** — frame timeout no corpus, fora da fila v5 |
| 9 | `test-09-flatten-working-orders.json` | `prac_directed_execution` (operador) | **Não** — sem frame de corpus |
| 10 | `test-10-daily-capture.json` | `prac_directed_execution` (operador) | **Não** — sem frame de corpus |
| 11 | `test-11-breakeven.json` | `prac_directed_execution` (operador) | **Não** — sem frame de corpus |

---

## 3. Fila v5 — proveniência por envelope

| # | scenario_id | scenario_tag | `chain_classification` | Bucket revisão |
|---|-------------|--------------|------------------------|----------------|
| 1–4 | SCN-STRAT-OPERATOR-MINUTE-FRAME-* | operator_minute_frame | `spontaneous_cognitive` | **spontaneous_cognitive** (sessão 09-01 overnight) |
| 5–6 | SCN-STRAT-PRAC-DIRECTED-TEST-* | prac_directed_test | legado / directed | **prac_directed_execution** |
| 7 | SCN-STRAT-RESTART-c30de894 | restart | `prac_directed_execution` | **prac_directed_execution** (teste 06) |

### Frames espontâneos da sessão 09-02 fora da fila v5

As três linhas do manifest (`cb1139d6`, `1a8dbc33`, `b7730ea3`) foram ingeridas ao corpus mas **não** entraram na fila v5: quota `operator_minute_frame` (4) preenchida por frames overnight da sessão 09-01; `1a8dbc33` adicionalmente falhou capacity gate no inventário v5. Isso não invalida a cadeia — é lacuna de seleção greedy, não defeito operacional.

---

## 4. Contribuição para qualidade cognitiva

| Categoria | Envelopes na fila v5 | Conta para tese espontânea? | Conta para gate 5 pares? |
|-----------|---------------------|------------------------------|---------------------------|
| `spontaneous_cognitive` | **4** (operator 09-01) | Potencial pós-replay | Agregado histórico **2/5** até replay autorizado |
| `prac_directed_execution` | **3** | **Não** | **Não** |
| Total fila | 7 | 4 elegíveis técnicos; 0 novos pares bilaterais sem replay | **INSUFFICIENT_SAMPLE** |

**Confirmação:** intents e frames de testes 6–11 **não** promovem tese espontânea. O gate cognitivo agregado permanece **2/5**.

---

## 5. Independência

- `independence_group` distinto por envelope (7 grupos)
- `snapshot_hash_dedupe`: 7 hashes únicos
- Exclusões: 31 `frame_id` de v2/v3/v4 e runs r7–r13 — sem overlap com fila

---

## 6. Lacunas de seleção (informativo)

Greedy não preencheu `reconciliation`, `preflight` nem `timeout` — inventário v5 tinha 11 elegíveis, meta 10, selecionados 7. Buckets `reconciliation`/`preflight` ausentes no corpus pós-exclusões ou sem capacity gate.

---

## 7. Decisão

| Ação | Permitida? |
|------|------------|
| Manter v5 como `pre_registered_offline` | **Sim** |
| Executar `scenario-live-2026-09-01-r14` | **Não** — bloqueado |
| Atualizar `next_authorized_run_id` | **Não** — permanece `null` |
| Promoção / agregador / shadow | **Não** |

**Próximo passo humano:** revisar `R14-AUTHORIZATION-CHECKLIST-2026-09-01.md` e confirmar explicitamente antes de qualquer replay live. Autorização de replay continua decisão separada desta revisão offline.
