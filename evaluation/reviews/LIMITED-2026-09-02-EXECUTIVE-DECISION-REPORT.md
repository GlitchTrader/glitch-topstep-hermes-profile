# Relatório executivo de decisão — pós `PRAC-LIMITED-2026-09-02`

**Data:** 2026-09-02  
**Status:** `FINAL` · encerramento analítico + monitor de saúde  
**Gate direcional v1:** **2/5** (inalterado)  
**`next_authorized_run_id`:** **`null`**

---

## Cadeia de evidência

```text
evidência acumulada r7–r17 (53 frames replay · 2/5 pares v1)
→ captura limitada PRAC-LIMITED (8 frames · 0 pares novos)
→ 31 amostras de health (soak concluído)
→ classificação produto health↔frames (8 frames)
→ oportunidades válidas: 0
→ abstinências válidas: 0
→ outcomes disponíveis: 0 (pipeline restrito a valid_abstention)
→ conclusão de viabilidade: congelar coleta direcional
```

---

## Resumo

A única PRAC limitada autorizada pela política de medição v1 foi executada, exportada, ingerida e auditada. O monitor de saúde registrou **31 amostras** em paralelo. A correlação health↔frames classifica **8/8** frames como `operationally_blocked` (`daily_capture_locked`). **Nenhum** frame é avaliável como abstinência válida. **Zero** novos pares direcionais.

**Recomendação:** **congelar coleta direcional** — sem nova PRAC, sem replay r18, sem promoção de perfil. Próxima iniciativa só com **mudança de medição aprovada** ou fonte histórica de oportunidades direcionais reais.

---

## Perguntas de produto (respostas objetivas)

| Pergunta | Resposta |
|----------|----------|
| Evidência suficiente para escolher um perfil? | **Não** — 2/5 pares v1; sessão limitada 100% bloqueada por lock |
| Ensemble direcional mensurável com o fluxo atual? | **Não** — `ensemble_inviable_with_current_data` |
| Abstinência avaliável sem viés operacional? | **Não** — lock domina; 0 `valid_abstention` na sessão limitada |
| Produto: continuar / redimensionar / congelar? | **Congelar coleta direcional**; manter trilha abstinência apenas como diagnóstico offline |

---

## Métricas acumuladas

| Métrica | Valor |
|---------|-------|
| Frames replay histórico (r7–r17) | 53 |
| Frames sessão limitada | 8 |
| **Total frames corpus** | **61** |
| Pares direcionais v1 (histórico) | **2** |
| Novos pares (limitada) | **0** |
| Amostras health (soak) | **31** |
| Frames `operationally_blocked` (limitada) | **8** |
| Frames `valid_abstention` (limitada) | **0** |
| Frames `valid_opportunity` (limitada) | **0** |
| Outcomes abstinência (valid_abstention only) | **0/0** |

Fontes: `measurement-adequacy-update-post-limited-2026-09-02.json`, `health-frame-correlation-PRAC-LIMITED-2026-09-02.json`, `abstention-outcomes-corrected-PRAC-LIMITED-2026-09-02.json`.

---

## Correlação health ↔ frames (8 frames)

Classificação produto por frame (`health-frame-correlation-PRAC-LIMITED-2026-09-02.json`):

| frame_id | decisão (UTC) | produto | `daily_capture_locked` | `state_complete` false na decisão | `state_complete` false na janela ±120s | barra completa | abstinência avaliável |
|----------|---------------|---------|------------------------|-----------------------------------|----------------------------------------|----------------|----------------------|
| `20260902T193005Z-b5fd08f8` | 19:31:43Z | `operationally_blocked` | sim | não | não | não (lag/partial) | não |
| `20260902T193505Z-3dd35e83` | 19:36:25Z | `operationally_blocked` | sim | não | não | não | não |
| `20260902T194002Z-0d305fc5` | 19:41:24Z | `operationally_blocked` | sim | não | sim | não (partial) | não |
| `20260902T194505Z-d7d1b4fb` | 19:46:25Z | `operationally_blocked` | sim | sim (degradado) | não | não (partial) | não |
| `20260902T195006Z-b7219c00` | 19:51:20Z | `operationally_blocked` | sim | sim (degradado) | não | não (partial) | não |
| `20260902T195507Z-b071ff79` | 19:56:14Z | `operationally_blocked` | sim | não | não | não (partial) | não |
| `20260902T200007Z-7800e8c3` | 20:02:27Z | `operationally_blocked` | sim | sim (degradado) | sim | não (partial) | não |
| `20260902T200505Z-ce29fef7` | 20:06:28Z | `operationally_blocked` | sim | não | sim | não (partial) | não |

**Confirmações:**

- **`state_complete=false` na decisão:** 3 frames (`d7d1b4fb`, `b7219c00`, `7800e8c3`).
- **`state_complete=false` na janela health ±120s:** 3 frames (`0d305fc5`, `7800e8c3`, `ce29fef7`).
- **`daily_capture_locked`:** 8/8 — nenhum frame escapa do bloqueio operacional.
- **Barra completa:** **0/8** — todos com lag/partial 1m (classificação estrita do audit).
- **Abstinência avaliável:** **0/8** — `NOTHING` sob lock não é abstinência válida.

Monitor de saúde: 7 amostras com `state_complete=false` no total (índices 5, 15, 17, 18, 19, 22, 28); correlação temporal confirma sobreposição com 3 decisões degradadas + 3 janelas health.

---

## Abstinência — conclusão corrigida

- Trilha: `abstention_outcome_diagnostic` · `diagnostic_only` · `promotion_use_allowed=false`.
- Pipeline reprocessado **somente** sobre `valid_abstention` → **0 associações**.
- Frames `operationally_blocked` **excluídos** — não rotulados como abstinência correta.
- Proxy posterior histórico (r7–r17, 30 `valid_abstention` corrigidos) permanece informativo, mas **não** fecha viés operacional da sessão limitada.

**Replay r18:** **não autorizado** — não altera lock nem produz pares; outcomes da sessão limitada são vazios por classificação, não por falta de proxy.

---

## Proveniência e gate

| Check | PASS |
|-------|------|
| `chain_complete=true` | ✓ |
| `frames_added=8` | ✓ |
| `verify=8/8` | ✓ |
| health soak 31 amostras | ✓ |
| `next_authorized_run_id=null` | ✓ |
| `STOP_RERUNS` ativo | ✓ |
| r18 não autorizado | ✓ |
| agregador / paralelismo / shadow / promoção bloqueados | ✓ |
| gate v1 = 2/5 preservado | ✓ |

---

## Decisão

```text
classificação corrigida (v2 + health↔frames)
→ outcome final (0 valid_abstention)
→ relatório executivo (este documento)
→ GATE_STATUS atualizado
→ coleta direcional congelada
```

**Não implementar** agregador executor até decisão positiva sobre viabilidade do ensemble e evidência para selecionar entre candidatos.

---

## Ações bloqueadas (sem nova autorização humana)

```text
nova PRAC · replay r18 · agregador · paralelismo · shadow · paper · canary · promoção
alteração gate v1 2/5 · cherry-pick de frames
```

---

## Artefatos de fechamento

| Trilha | Artefato |
|--------|----------|
| Qualidade | `evaluation/runs/limited-capture-frame-quality-audit-2026-09-02.json` |
| Health↔frames | `evaluation/runs/health-frame-correlation-PRAC-LIMITED-2026-09-02.json` |
| Abstinência corrigida | `evaluation/runs/abstention-outcomes-corrected-PRAC-LIMITED-2026-09-02.json` |
| Gate corrigido v2 | `evaluation/runs/directional-gate-corrected-view-v2-2026-09-02.json` |
| Veredito operacional | `evaluation/runs/operational-verdict-2026-09-02.json` |
| Health raw | `glitch-topstep/docs/evidence/PRAC-LIMITED-2026-09-02/health-samples.jsonl` |
| Runner | `scripts/run-product-decision.py` |

---

## Próximo passo humano

1. **Assinar** congelamento da coleta direcional.
2. **Manter** `next_authorized_run_id=null` até nova política explícita de medição.
3. Se o produto continuar: aprovar **mudança de medição** (abstinência com outcomes desbloqueados por design, ou corpus histórico direcional real) — **não** repetir captura PRAC no regime atual.
