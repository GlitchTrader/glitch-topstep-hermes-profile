# Investigação SHA256SUMS — 2026-09-02

**Teste falho:** `tests.test_sha256sums.Sha256sumsTests.test_manifest_matches_files`

---

## Arquivo divergente

`tests/fixtures/frozen_corpus/enriched/manifest.json`

| Campo | Valor |
|-------|-------|
| Hash pinado (SHA256SUMS local pré-fix) | `AAB45A528B9130309B84E43F2F24E85743CBA16F0A951F99EA5882840416E34B` |
| Hash actual (disco) | `5FCE538FFC29E37E85D0969C6869D4B5116E5B2DA11AFAFA35820F13BCED9448` |
| Hash pós-regenerate | `5FCE538F…` (coerente) |

---

## Motivo

1. `build-enriched-corpus.py` regenerou o manifest em **2026-09-02T18:34:06Z** após ingest PRAC v9 (66 frames, 51 excluded).
2. `SHA256SUMS` tinha sido parcialmente atualizado **antes** dessa segunda regeneração — pin intermediário desatualizado.
3. O arquivo estava **untracked** no git; entrada no SHA256SUMS foi adicionada localmente sem commit sincronizado.

---

## Decisão

| Pergunta | Resposta |
|----------|----------|
| Mudança esperada? | **Sim** — corpus enriquecido com frames v9 é fluxo legítimo de ingest |
| Mudança indevida? | **Não** — conteúdo consistente com `enriched/minute-frames/` |
| Artefato audit-only? | **Não** — faz parte da distribuição pinada em `tests/` (fixtures frozen corpus) |
| Mascarar teste? | **Não** — regenerar checksum |

---

## Resolução

```powershell
python scripts\regenerate_sha256sums.py   # 557 entries
python -m unittest tests.test_sha256sums -v
python -m unittest discover -s tests -p "test_*.py" -v
```

**Resultado:** **534 OK** (1 skipped) · `git diff --check` limpo · regenerate 2026-09-02 pós-manifest v9.

## Estado atual (2026-09-02 pós-Fase 5)

```text
534 tests OK (1 skipped)
SHA256SUMS: 557 entries · coerente
Fase: MEASUREMENT_STRATEGY_REVIEW
```
