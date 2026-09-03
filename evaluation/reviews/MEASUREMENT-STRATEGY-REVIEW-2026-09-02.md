# Revisão da estratégia de medição — sequencial pós-trilhas

**Data:** 2026-09-02  
**Pré-requisitos:** suíte verde · trilhas A–D · veredito Fase 5 aceito (Opção B)

---

## Estado validado

```text
fase ativa                 = MEASUREMENT_STRATEGY_REVIEW
gate oficial               = 2/5 · insufficient_sample (inalterado)
STOP_RERUNS                = ativo (v2–v9)
next_authorized_run_id     = null
suíte                      = 534 OK (1 skipped)
SHA256SUMS                 = coerente (557 entries)
```

---

## Bloco 1 — suíte (resolvido)

Ver `SHA256SUMS-DRIFT-INVESTIGATION-2026-09-02.md`.

- Divergência: `tests/fixtures/frozen_corpus/enriched/manifest.json`
- Causa: regeneração pós-ingest v9 sem `regenerate_sha256sums` final
- Ação: `regenerate_sha256sums.py` — **sem** mascarar teste

---

## Bloco 2 — trilhas paralelas

| Trilha | Artefato | Conclusão |
|--------|----------|-----------|
| **A Abstinência** | `evaluation/ABSTENTION-DIAGNOSTIC-SPEC.md` | spec diagnóstica; gate `quality_gate_abstention` proposto |
| **B Oportunidade** | `evaluation/runs/phase-5-opportunity-audit-2026-09-02.json` | 53 frames: 31 abstinência bilateral; **2** pares válidos (dirigidos); 0 espontâneos→bilateral |
| **C Adequação amostral** | `evaluation/MEASUREMENT-STRATEGY-PROPOSAL-2026-09-02.md` | gates separados; máx 1 coleta pós-aprovação |
| **D Proveniência** | `evaluation/runs/phase-5-provenance-segmentation-audit-2026-09-02.json` | directed/spontaneous segregável; 3 drift r7 preservados; risco interpretativo no numerador agregado |

### Funnel oportunidade (frame-level)

| Bucket | Count |
|--------|-------|
| `valid_abstention_bilateral` | 31 |
| `directed_envelope` | 7 |
| `insufficient_capacity` | 6 |
| `unilateral_candidate` | 3 |
| `directional_signal_no_bilateral_pair` | 3 |
| `valid_abstention_or_divergence` | 2 |
| `bilateral_thesis_quality_possible` | 1 |

**Leitura:** oportunidade direcional concentra-se em envelopes **dirigidos** (r7/r10). Espontâneos recentes (r15–r17) produzem abstinência alinhada, não pares.

---

## Bloco 3 — decisão técnica

### Aceito

- **Opção B** como fase ativa.
- **Dois gates futuros** (limiares TBD, aprovação humana):
  - `quality_gate_directional` — existente;
  - `quality_gate_abstention` — novo, diagnóstico primeiro.
- **v10 permanece contingência** — não iniciar PRAC até política aprovada.

### Pendente aprovação humana

| Item | Documento |
|------|-----------|
| Política de medição | `MEASUREMENT-STRATEGY-PROPOSAL-2026-09-02.md` |
| Spec abstinência | `ABSTENTION-DIAGNOSTIC-SPEC.md` |
| Limiares `quality_gate_abstention` | não definidos |
| Autorização coleta v10 | **negada** até assinatura |

### Sequência pós-aprovação

```text
aprovação humana nova política
→ formalizar abstention_quality_gate.v1.json (se aprovado)
→ atualizar GATE_STATUS + registry + plano
→ decidir se única coleta v10 é autorizada
→ só então PRAC / coorte / replay
```

---

## Objetivo do projeto (reafirmado)

Tornar a avaliação capaz de distinguir:

```text
perfil conservador  ≠  perfil sem oportunidade observável
```

antes de decidir qual perfil funciona melhor.

---

## Bloqueios mantidos

```text
PRAC v10 · replay novo · replay v9
agregador executável · paralelismo Hermes
shadow · paper · canary · promoção
```
