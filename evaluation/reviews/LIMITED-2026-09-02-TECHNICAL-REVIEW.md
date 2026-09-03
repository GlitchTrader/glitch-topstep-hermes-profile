# Revisão técnica — coorte `limited-2026-09-02` (FECHADA)

**Status:** `CLOSED` · `analytical_closure_complete`  
**Gerado:** 2026-09-02T20:15:00Z  
**Sessão:** `PRAC-LIMITED-2026-09-02`  
**Classificação:** **`READY_WITH_LIMITATIONS`**  
**Gate direcional v1:** **2/5** (preservado · não alterado)  
**Replay proposto:** `scenario-live-2026-09-02-r18-limited` — **não autorizado**

---

## Veredito fechado

A coleta limitada única autorizada pela política v1 **cumpre integridade operacional e offline** (cadeia, ingest, coorte, verify). **Não** produz novos pares direcionais. A abstinência é **estrutural** (`daily_capture_locked` em 7/8 decisões) e **não** deve ser lida como qualidade cognitiva.

**Limitação de evidência explícita:** 8/8 envelopes passam `capacity_gate` offline, mas **8/8** carregam limitação de captura (3 gateway degradado no instante da decisão · 5 completude de barra com lag/partial). Isso **não** está oculto sob `capacity_gate_pass`.

---

## Proveniência confirmada

| Critério | Resultado |
|----------|-----------|
| `chain_complete` | **true** |
| `frames_added` | **8** |
| `novo_elegivel` | **8** |
| `already_consumed` | **0** |
| `verify` | **8/8** sem skip |
| Digest | `7a5c6ab5e92cc7d425bf2711ecf9be48ad25a43abb43bee9be2f4fab57a6fa31` |
| Ingest path | `state\minute-frames` |
| `production_paths_untouched` | **true** |
| `next_authorized_run_id` | **`null`** |

---

## Auditoria por frame (Paralelo A)

Fonte: `evaluation/runs/limited-capture-frame-quality-audit-2026-09-02.json`

| frame_id | pkt `state_complete` | gateway no ciclo | barra | snapshot manifest | observados | decidido | capacity offline | limitação evidência |
|----------|---------------------|------------------|-------|-------------------|------------|----------|------------------|---------------------|
| `20260902T193005Z-b5fd08f8` | true | ok | lag/partial 1m | match | MNQ,MES,MCL | MNQ | PASS | bar_completeness |
| `20260902T193505Z-3dd35e83` | true | ok | lag/partial 1m | match | MNQ,MES,MCL | MNQ | PASS | bar_completeness |
| `20260902T194002Z-0d305fc5` | true | ok | lag/partial 1m | match | MNQ,MES,MCL | MNQ | PASS | bar_completeness |
| `20260902T194505Z-d7d1b4fb` | true | **degraded** | lag/partial 1m | match | MNQ,MES,MCL | MNQ | PASS | **gateway_degraded** |
| `20260902T195006Z-b7219c00` | true | **degraded** | lag/partial 1m | match | MNQ,MES,MCL | MNQ | PASS | **gateway_degraded** |
| `20260902T195507Z-b071ff79` | true | ok | lag/partial 1m | match | MNQ,MES,MCL | MNQ | PASS | bar_completeness |
| `20260902T200007Z-7800e8c3` | true | **degraded** | lag/partial 1m | match | MNQ,MES,MCL | MNQ | PASS | **gateway_degraded** |
| `20260902T200505Z-ce29fef7` | true | ok | lag/partial 1m | match | MNQ,MES,MCL | MNQ | PASS | bar_completeness |

**Notas:**

- `packet_market_snapshot_hash` ≠ hash canónico do envelope em todos os frames (esperado no subset canónico); **manifest hash match 8/8**.
- Produção: **8/8 `NOTHING`** · lock citado **7/8**.
- Observação multi-instrumento (MNQ,MES,MCL) **não** se traduz em decisão fora de MNQ.

---

## Abstinência e outcomes (Paralelo B)

Fonte: `evaluation/runs/abstention-outcome-associations-PRAC-LIMITED-2026-09-02.json`

```text
classification: diagnostic_only
promotion_use_allowed: false
horizon: 15 min
associations: 8
posterior_data_available: 7/8
```

Pipeline aplicado por frame: `no_edge` → dados posteriores → horizonte → MFE/MAE → first touch → excursão adversa → contrafactual.

**Sem** rotular acerto/incorreção — `contrafactual_edge_ticks` é proxy diagnóstico apenas.

| frame_id | posterior | first_touch | contrafactual_dir | edge_ticks |
|----------|-----------|-------------|-------------------|------------|
| `…ce29fef7` | indisponível (último ciclo) | — | — | — |
| `…7800e8c3` | sim | up | long | 16.0 |
| `…b071ff79` | sim | down | short | 82.0 |
| `…b7219c00` | sim | up | long | 27.0 |
| `…d7d1b4fb` | sim | down | short | 79.0 |
| `…0d305fc5` | sim | up | long | 173.0 |
| `…3dd35e83` | sim | up | long | 20.5 |
| `…b5fd08f8` | sim | up | long | 1.5 |

---

## Gate estratificado pós-limitada (Paralelo C)

Fonte: `evaluation/runs/directional-gate-stratified-view-post-limited-2026-09-02.json`

**Histórico v2 (imutável):** 2 pares · 33 `no_edge_bilateral` · 8 unilateral · 6 capacity.

**Sessão limitada (isolada):**

| Estrato | Contagem |
|---------|----------|
| spontaneous | 8 |
| no_edge_bilateral (produção) | 0 |
| data_degradation (limitação evidência) | 8 |
| directional_pairs novos | **0** |

---

## Coorte

| Artefato | Path |
|----------|------|
| Manifest | `evaluation/runs/stratified-cohort-manifest-limited-2026-09-02.json` |
| Digest | `evaluation/runs/stratified-cohort-digest-limited-2026-09-02.json` |
| Scenarios | `evaluation/stratified_scenarios.limited-2026-09-02.json` |

---

## Decisão de replay

| Campo | Valor |
|-------|-------|
| Replay r18 autorizado | **não** |
| `next_authorized_run_id` | **`null`** |
| Relatório executivo | `evaluation/reviews/LIMITED-2026-09-02-EXECUTIVE-DECISION-REPORT.md` |

**Recomendação alinhada à política v1:** encerrar coleta direcional (Opção 2). Replay r18 **não** necessário para outcomes de abstinência — proxy posterior cobre 7/8 frames sem reexecutar perfis.

---

## Bloqueios mantidos

```text
agregador executável · paralelismo Hermes · shadow · paper · canary · promoção
nova PRAC automática · alteração gate v1 2/5
```
