# Cobertura por sessão — corpus pós-ingest PRAC-SOAK-2026-09-02

**Ingest:** `prac-corpus-ingest-PRAC-SOAK-2026-09-02.json`  
**Coorte canônica:** v5.1

## Por origin (corpus enriched, complete)

| Origin | Total frames | spontaneous_cognitive | prac_directed_execution | Na fila v5.1 |
|--------|-------------|----------------------|-------------------------|--------------|
| `prac_soak_2026_09_02` | 5 | 3 | 2 (restart, timeout) | **3** (2 espontâneos + 1 restart) |
| `prac_soak_2026_09_01` | 10+ | 8 operator | — | **6** espontâneos overnight |
| `prac_soak_2026-08-31` | legado | — | directed | **0** |

## Manifest export vs corpus

| Artefato | Linhas / frames | Nota |
|----------|-----------------|------|
| `evidence-chain-manifest.json` | 3 NOTHING espontâneas | Join completo na janela PRAC |
| Corpus espontâneo 09-02 | 3 | `1a8dbc33` falha capacity gate → **2** na fila v5.1 |
| Testes 6–11 | 6 PASS | Evidência operacional; não na fila cognitiva |

## Lacunas

- `timeout` (teste 08): `capacity_gate_pass: false` — fora de qualquer coorte até gate passar.
- `reconciliation` / `preflight`: já consumidos em coortes v2–v4 — indisponíveis.
- Instrumentos: apenas MNQ no corpus atual.

## Implicação para próxima sessão PRAC

Priorizar captura com: mais minutos espontâneos em horário regular (não só overnight), barras completas onde gate falha, e eventual segundo instrumento quando política permitir.
