# Revisão técnica de autorização — coorte estratificada v4

**Data:** 2026-09-02 (offline)  
**Escopo:** integridade pré-registro v4 — **não autoriza r14** nem altera `next_authorized_run_id`  
**Artefatos:** manifest `stratified-cohort-manifest-v4-2026-09-01.json` · digest `7b858bd3482eb15fd42982fb4a0e585b4501a928736fb9365eea88a692dfc209` · ingest `prac-corpus-ingest-PRAC-SOAK-2026-09-01.json`

## Veredito

| Dimensão | Status |
|----------|--------|
| Integridade técnica da coorte v4 (digest, verify, independência) | **READY** |
| Gate cognitivo agregado (pares comparáveis espontâneos) | **INSUFFICIENT_SAMPLE** (2/5 mantido) |
| Autorização de execução r14 | **BLOCKED** — `r14_authorization: pending_explicit_human_approval` |

**Veredito composto para esta revisão:** `INSUFFICIENT_SAMPLE` — coorte v4 está tecnicamente pré-registrada e verificável, mas a amostra efetiva para qualidade cognitiva permanece abaixo do mínimo (5 pares independentes). **Não autorizar r14** nesta rodada.

---

## 1. Digest, hashes e timestamps

| Verificação | Resultado |
|-------------|-----------|
| `digest-stratified-cohort.py` (re-run 2026-09-02) | SHA256 `7b858bd3…` — **idêntico** ao digest registrado |
| `verify-stratified-cohort.py` (sem `--skip-validation`) | **PASS 5/5** |
| `unique_snapshot_hashes` | **5/5** — sem colisão |
| `envelope_hash` por fila | Presente em todos os envelopes |
| Timestamps dos frames espontâneos | `2026-09-02T01:43:20Z`, `2026-09-02T01:50:20Z` (janela PRAC `since_utc: 2026-09-02T01:25:00Z`) |
| `chain_complete` no ingest | **true** (cadeia operacional apenas) |

**Nota:** três envelopes (prac_directed_test legado, restart, timeout) exibem `manifest_trust: degraded_metadata` por `manifest_snapshot_hash_stale` no enriched — o hash **computado** do packet coincide com o manifest v4; não bloqueia verify offline.

---

## 2. Classificação de envelopes (proveniência)

| # | scenario_id | scenario_tag | `chain_classification` (corpus) | Bucket de revisão |
|---|-------------|--------------|--------------------------------|-------------------|
| 1 | SCN-STRAT-OPERATOR-MINUTE-FRAME-59375017 | operator_minute_frame | `spontaneous_cognitive` | **spontaneous_cognitive** |
| 2 | SCN-STRAT-OPERATOR-MINUTE-FRAME-4bd5490f | operator_minute_frame | `spontaneous_cognitive` | **spontaneous_cognitive** |
| 3 | SCN-STRAT-PRAC-DIRECTED-TEST-6e53152d | prac_directed_test | legado (ingest: directed) | **prac_directed_execution** |
| 4 | SCN-STRAT-RESTART-7278cb75 | restart | `prac_directed_execution` | **prac_directed_execution** |
| 5 | SCN-STRAT-TIMEOUT-46ba8be0 | timeout | `prac_directed_execution` | **prac_directed_execution** |

### Buckets ausentes na fila v4

| Bucket | Contagem v4 | Nota |
|--------|-------------|------|
| `NOTHING` | 0 na fila | Linhas NOTHING espontâneas no ingest mantêm fixtures `no_edge` offline; não entram na coorte estratificada |
| `no_edge` | 0 como tese espontânea | Esperado em fixtures de perfis não-baseline para frames dirigidos |
| `not_comparable` | 0 pré-registrados | Pode surgir **após** replay (ex.: `data_quality_insufficient`); não conta como candidato espontâneo |

---

## 3. Contribuição para qualidade cognitiva

| Categoria | Envelopes | Conta para tese espontânea? | Conta para gate 5 pares? |
|-----------|-----------|------------------------------|---------------------------|
| `spontaneous_cognitive` | **2** | **Sim** (potencial bilateral pós-replay) | Potencial **máx. +2** se ambos gerarem `thesis_quality` bilateral |
| `prac_directed_execution` | **3** | **Não** | **Não** — prova contrato/recovery/execução dirigida |
| Total fila | 5 | **2 elegíveis** para qualidade cognitiva espontânea | Agregado histórico **2/5** inalterado até replay autorizado |

**Confirmação:** testes dirigidos (restart test-06, timeout test-08, prac_directed_test legado) **não** são candidatos espontâneos. Teste 07 (`intent-delivery`) foi ingerido ao corpus mas **excluído** da fila v4 por snapshot duplicado com teste 06 no greedy.

---

## 4. Independência

- `independence_group` distinto por envelope (`ig-bda092…` … `ig-c6f429…`)
- `snapshot_hash_dedupe`: 5 hashes únicos
- `session_origin_distribution`: 4× `prac_soak_2026_09_01`, 1× `prac_soak_2026-08-31` (legado)
- `scenario_tag_distribution`: 2× operator, 1× prac_directed, 1× restart, 1× timeout
- Exclusões: 26 `frame_id` de v2/v3 e runs r7–r13 — sem overlap com fila

---

## 5. Lacunas de seleção (informativo)

Greedy não preencheu `reconciliation` nem `preflight` — inventário v4 tinha 13 elegíveis mas apenas 5 selecionados (meta 8–10 não atingida por capacidade de diversidade sem reutilizar snapshots).

---

## 6. Decisão

| Ação | Permitida? |
|------|------------|
| Manter v4 como `pre_registered_offline` | **Sim** |
| Executar `scenario-live-2026-09-01-r14` | **Não** — bloqueado |
| Atualizar `next_authorized_run_id` | **Não** — permanece `null` |
| Promoção / agregador / shadow | **Não** |

**Próximo passo humano:** revisar `R14-AUTHORIZATION-CHECKLIST-2026-09-01.md` e confirmar explicitamente antes de qualquer replay live.
