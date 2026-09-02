# Fase ativa — coleta PRAC (pós-r14)

**Efetiva:** 2026-09-02  
**Coordenação evaluation×cron:** **`LIVE_VALIDATED`** (2026-09-02) — não autoriza replay  
**Próxima coorte:** **v9** — PRAC diversa pendente · v8+r16 **encerrados** (`STOP_RERUNS`)  
**Fase anterior:** coorte v8 + replay r16 — **encerrada** 2026-09-02  
**Gate cognitivo:** **2/5** · `insufficient_sample`  
**Bloqueios mantidos:** agregador executável · paralelismo Hermes · shadow · promoção

---

## Leitura operacional

O sistema de avaliação está **robusto** para medir; insistir em reruns sobre o corpus atual é **desperdício**. O gargalo é exclusivamente **evidência cognitiva independente** com diversidade temporal, de instrumento e de cenário.

**Não é leitura correta:** um perfil “venceu” ou “falhou”. Com o corpus r14, ambos abstiveram na maioria; ainda não há amostra bilateral suficiente para comparar qualidade de tese.

---

## Sequência obrigatória (pós-lease)

```text
coordenação LIVE_VALIDATED           ✓
  → nova sessão PRAC diversa         ✓ PRAC-SOAK-2026-09-02-v8 (limitada)
  → export + ingest                  ✓ 3 frames_added
  → inventário + coorte v8           ✓ verify 3/3
  → revisão técnica coorte           ✓ READY_WITH_LIMITATIONS
  → autorização humana               ✓ Ari 2026-09-02 · `scenario-live-2026-09-02-r16-v8`
  → replay sequencial                ✓ r16 COMPLETE 6/6 · 0 invalid
  → novo gate (≥5/5)                 ✗ 2/5 inalterado — STOP_RERUNS v8
  → PRAC diversa v9                  pendente (operador)
```

**Somente se gate ≥5/5:**

```text
agregador determinístico offline
  → auditoria
  → shadow controlado
```

**Proibido:** pular para replay após export; promover testes dirigidos a espontâneo; definir `next_authorized_run_id` sem aprovação humana.

---

## Classificação de evidência

```text
testes/unitários       = source-tested
replay Hermes          = replay-proven
sessão PRAC            = PRAC-proven
produção armada        = armed-promoted
```

**Regra:** nenhum resultado source-tested, replay-proven ou PRAC-proven autoriza operação armed-promoted.

---

## Critérios de sessão (operador)

Manter durante toda a captura PRAC:

- credenciais aprovadas · ambiente PRAC isolado;
- conta flat antes e depois;
- `unprotected_open_quantity = 0`;
- `recovery_blocking = false` (`execution_recovery_blocking` no `/health`);
- `state_complete = true` (ou degradação registrada explicitamente);
- barras completas ou qualidade documentada;
- cadeia `packet → snapshot → intent → decisão → receipt` preservada;
- testes 6–11 = evidência operacional apenas.

**Interromper e preservar** se: mutação ambígua · exposição desprotegida · recovery bloqueado · integridade do state comprometida · divergência `packet_id`/`snapshot_hash` · falha no export.

Checklist detalhado: `glitch-topstep/docs/evidence/PRAC-NEXT-SESSION-CHECKLIST.md`

---

## Sequência pós-sessão (PRAC long — concluída 2026-09-02)

```text
export chain_complete          ✓
  → ingest                     ✓ (frames_added: 4)
  → auditoria consumo          ✓ (4/4 novo_elegivel)
  → coorte v7                  ✓ (verify 4/4)
  → revisão técnica            ✓ (`V7-TECHNICAL-REVIEW-AUTHORIZATION-CHECKLIST-2026-09-02.md`)
  → autorização humana         ✓ Ari 2026-09-02 · `next_authorized_run_id: scenario-live-2026-09-02-r15-v7`
  → replay sequencial          ✓ r15 COMPLETE (8/8)
  → novo gate                  ✓ **2/5** mantido (`insufficient_sample`)
```

Coorte v6 preservada e adiada para objetivo de gate (`V6-GATE-DECISION-2026-09-02.md`).

---

## Objetivos da próxima captura PRAC

| Prioridade | Objetivo |
|------------|----------|
| P0 | Ciclos espontâneos **contínuos** — todos, sem cherry-pick |
| P0 | `data_quality.state_complete: true` e barras 1m **fechadas** |
| P0 | Cadeia completa: `packet → snapshot → intent → decisão → receipt` |
| P1 | reconciliation + preflight (buckets com par histórico) |
| P1 | Diversidade de **horário** (midday, afternoon — não só overnight) |
| P2 | Outro **instrumento** se gateway/conta permitir |
| — | Testes 6–11: `prac_directed_execution` — **não** evidência cognitiva |

---

## Trabalho paralelo (somente preparação e análise)

| Item | Artefato | Ação |
|------|----------|------|
| Casos `no_edge` | `R14-NO-EDGE-AND-E8DF6B82-ANALYSIS-2026-09-02.md` | Revisar; não alterar baseline |
| `partial_evidence` | `NO-EDGE-PARTIAL-EVIDENCE-DIAGNOSIS-2026-09-02.md` | Rastrear `state_complete` na próxima captura |
| Divergência baseline ↔ structure | `METRICS-PREP-2026-09-02.md` | `direction_delta`, categorias por frame |
| Agregador + fixtures | spec v1 · 12/12 PASS | **Congelados** |
| Checklist operacional | `glitch-topstep/docs/evidence/PRAC-NEXT-SESSION-CHECKLIST.md` |
| Sequência canônica 1–9 | `glitch-topstep/docs/evidence/PRAC-SESSION-SEQUENCE.md` | Usar na sessão live |
| Pré-registro coorte v8 | `STRATIFIED-COHORT-V8-PREREGISTRATION-2026-09-02.md` | **Pendente** PRAC diversa |
| Revisão lease | `LEASE-COORDINATION-TECHNICAL-REVIEW-2026-09-02.md` | **APPROVED** coordenação |
| Auditoria PRAC long | `PRAC-LONG-FRAME-CONSUMPTION-AUDIT-2026-09-02.md` | 4/4 elegíveis |

**Não iniciar:** Hermes adicional fora da sessão PRAC; greedy offline; implementação do agregador.

---

## Referências

| Área | Path |
|------|------|
| Prep captura | `evaluation/reviews/PRAC-NEXT-CAPTURE-PREP-2026-09-02.md` |
| Runbook programador | `glitch-topstep/docs/evidence/PRAC-PROGRAMMER-RUNBOOK-2026-09-02.md` |
| Relatório r14 | `evaluation/reviews/R14-POST-EXECUTION-REPORT-2026-09-02.md` |
| Registry | `evaluation/runs/stratified-cohort-execution-registry.json` |
| Gate status | `evaluation/GATE_STATUS.md` |
| Runbook | `glitch-topstep/docs/evidence/PRAC-CAPTURE-RUNBOOK.md` |
