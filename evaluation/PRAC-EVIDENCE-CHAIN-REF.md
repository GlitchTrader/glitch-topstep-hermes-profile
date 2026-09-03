# Referência — cadeia de evidência PRAC (v1)

**Schema canónico (profile):** [`schemas/prac_evidence_chain.v1.json`](./schemas/prac_evidence_chain.v1.json)

**Formato operacional e runbook (gateway):**

| Documento | Repositório | Path |
|-----------|-------------|------|
| Formato do pacote de evidência | `glitch-topstep` | [`docs/evidence/PRAC-EVIDENCE-CHAIN-FORMAT.md`](https://github.com/GlitchTrader/glitch-topstep/blob/main/docs/evidence/PRAC-EVIDENCE-CHAIN-FORMAT.md) |
| Runbook de captura (abrir → durante → fechar) | `glitch-topstep` | [`docs/evidence/PRAC-CAPTURE-RUNBOOK.md`](https://github.com/GlitchTrader/glitch-topstep/blob/main/docs/evidence/PRAC-CAPTURE-RUNBOOK.md) |

**Scripts (gateway, não duplicar no profile):**

- `scripts/export-prac-evidence-chain.py` — exporta `decisions.jsonl`, `receipts.jsonl` e `evidence-chain-manifest.json` a partir de `state/`.
- `scripts/validate-prac-evidence-chain.py` — valida o diretório de evidência contra o schema v1.

**Fixture de referência:** `glitch-topstep/tests/fixtures/prac_evidence_chain/minimal-complete/`

O profile define o contrato (`prac_evidence_chain.v1.json`); o gateway implementa export, validação e documentação de captura. Não mutar ProjectX a partir do profile — gateway only.
