# Auditoria de proveniência — artefatos canônicos

**Data:** 2026-09-02 (offline)  
**Scanners:** `audit-artifact-provenance.py` · `run-frozen-measurement-audit.py`  
**Escopo:** 104 invocações em `evaluation/runs/` · coorte histórica r7–r13

---

## Resumo

| Métrica | Valor |
|---------|-------|
| Artefatos escaneados | **104** |
| Hash integrity OK | **104/104** |
| Version alignment OK | **104/104** |
| Envelope identity OK | **104/104** |
| Pipeline repeatability PASS | **104/104** |
| **Novo drift** | **0** |
| Drift histórico conhecido (r7) | **3** (preservados) |
| Temporal leakage suspeito | **0** |
| Arquivos operacionais alterados (gateway src/release) | **0** nesta rodada de revisão |

---

## Drift histórico r7 (audit-only — não recontar)

| Artefato | Classificação |
|----------|---------------|
| `…-r7-contract-baseline-current-…-041dc508.json` | `historical_normalization_version` |
| `…-r7-contract-baseline-current-…-bb50bbe9.json` | idem |
| `…-r7-contract-structure-…-041dc508.json` | idem |

**Regra:** drift r7 **não** é nova evidência; sidecars `*-provenance.json` documentam sem mutar corpos.

---

## r12-v1 vs r12-v2

| Run | skip_validation | promotion_eligible | Classificação |
|-----|---------------|-------------------|---------------|
| `scenario-live-2026-09-01-r12-stratified` | **true** | false | **histórico / audit-only** |
| `scenario-live-2026-09-01-r12-stratified-v2` | false | false | **canônico** |

Registry `non_canonical_executions` confirma r12-v1 fora da promoção.

---

## Contexto de normalização congelado

```text
adapter_version:          2026-09-01-v1
prompt_versions:          glitch-topstep-v17.1
registry_version:         2026-09-01-v2
aggregator_rules_version: 2026-09-01-v2
normalization_version:    2026-09-01-post-candidate-flat-rule
```

Runs r10–r13: `historical_drift_count: 0`, `matches_current_adapter_count` = total.

---

## Duplicatas cross-run

- 14 grupos `cross_run_snapshot_groups` — maioria `expected_corpus_replay: true` (r9/r10/r11 frozen queue)
- r12-v1 intra-run duplicates: esperado (9 envelopes × 2 perfis, replays de validação)
- **v4:** 5 snapshot hashes únicos — sem duplicata na fila

---

## Frozen measurement audit

`run-frozen-measurement-audit.py` → `ok: false` (worker verify-frozen-cohort pré-existente; SHA256SUMS drift em testes — **não** introduzido nesta rodada).

**Ação:** manter como informativo; proveniência de invocações **104/104** intacta.

---

## v4 ingest proveniência

| Artefato | SHA256 (arquivo) |
|----------|------------------|
| session-finalize.json | `8e331d34…` |
| evidence-chain-manifest.json | `253312a9…` |
| decisions.jsonl | `c483bf7a…` |
| receipts.jsonl | `6b62461b…` |

Arquivo: `evaluation/runs/prac-corpus-ingest-PRAC-SOAK-2026-09-01.json`

---

## Artefatos gerados

- `evaluation/runs/artifact-provenance-audit-2026-09-02.json`
- `evaluation/runs/cohort-provenance-audit-2026-09-02.json`
- `evaluation/runs/frozen-measurement-audit-2026-09-02.json`

**Veredito:** **0 drift novo** · r7/r12-v1 permanecem históricos · operacional intocado.
