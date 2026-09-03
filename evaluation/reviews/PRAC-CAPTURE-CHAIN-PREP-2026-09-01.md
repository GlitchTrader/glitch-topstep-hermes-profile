# Preparação cadeia PRAC — 2026-09-01

**Status:** formato pronto para capturas futuras (validação read-only em exemplos `*-raw.json`).

## Cadeia alvo

```text
packet_id → snapshot_hash → decisão → intent → receipt
```

| Elo | Campos mínimos | Validação offline |
|-----|----------------|-------------------|
| **packet** | `schema_version=glitch.direct.decision_packet.v2`, `packet_id`, `contract` | `validate-prac-capture-chain.py` |
| **snapshot_hash** | SHA-256 do subset canônico do packet (`ensemble_envelope.snapshot_hash`) | `build-enriched-corpus.py` / manifest enriched |
| **decisão** | `state`, `direction`, `thesis` (raw profile ou journal) | join via `audit-corpus-decision-join.py` |
| **intent** | `intent_id`, `instrument`, `side`, `qty` | gateway outbox (produção — não mutar na coleta) |
| **receipt** | `receipt_id`, `status`, `filled_qty` | gateway receipts (produção — não mutar na coleta) |

## Checklist captura futura

1. Capturar `*-raw.json` com packet v2 embutido (não só health/metrics).
2. Registrar `source_file_hash` e `packet_path` no manifest enriched.
3. Selecionar frames **antes** de invocar Hermes (manifest estratificado).
4. Não reordenar coorte com base em `thesis_quality` observado.
5. Manter prompts/adapter/registry congelados durante medição.
6. Vincular decisão→intent→receipt só em sessão PRAC credenciada (gateway local).

## Imparcialidade vs PRAC

- **Seleção offline:** estratificação por `scenario_tag`, `origin`, sessão — sem olhar resultado do perfil.
- **PRAC adiciona:** elo causal intent/receipt para validar outcomes; não substitui seleção imparcial.
- Frames PRAC `prac_directed_test` e `entry.attempts[*]` enriquecem contextos com decisão adjacente, mas entram na coorte por critérios estruturais, não por concordância esperada.

## Script

```powershell
python scripts/validate-prac-capture-chain.py
```

## Referências

- Evidência: `glitch-topstep/docs/evidence/PRAC-SOAK-2026-08-31/`
- Corpus enriched: `tests/fixtures/frozen_corpus/enriched/manifest.json`
- Coorte estratificada: `evaluation/runs/stratified-cohort-manifest-2026-09-01.json`
- Plano r14: `evaluation/SAMPLING-PLAN-R14-2026-09-01.md`
- Inventário fontes: `evaluation/reviews/PRAC-SOURCE-INVENTORY-R14-2026-09-01.md`
