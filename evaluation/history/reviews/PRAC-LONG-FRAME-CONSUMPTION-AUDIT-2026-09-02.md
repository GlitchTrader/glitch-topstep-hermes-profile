# Auditoria — frames PRAC-SOAK-2026-09-02-long

**Data:** 2026-09-02  
**Sessão:** `PRAC-SOAK-2026-09-02-long` · `chain_complete: true`  
**Artefato JSON:** `evaluation/runs/prac-frame-consumption-audit-2026-09-02-long.json`

---

## Captura (sem intervenção)

| Item | Valor |
|------|-------|
| Início | `2026-09-02T15:39:06.423Z` |
| Duração | ~18 min |
| Ciclos espontâneos NOTHING | **4** |
| Prompt / adapter / registry | **inalterados** |
| Entradas forçadas | **nenhuma** |

Evidência gateway: `glitch-topstep/docs/evidence/PRAC-SOAK-2026-09-02-long/`

---

## Pipeline pós-sessão

| Passo | Resultado |
|-------|-----------|
| Export | `chain_complete: true` · 4 linhas manifest |
| Ingest | `frames_added: 4` (path `state/minute-frames` OK) |
| Auditoria consumo | **4/4** `novo_elegivel` · **4/4** `capacity_gate_pass` |
| Seleção v7 | **4** envelopes · verify **4/4** sem `--skip-validation` |

---

## Classificação por frame

| packet_id (8) | frame_id | Classificação | capacity_gate | Coorte v7 |
|---------------|----------|---------------|---------------|-----------|
| `358cec55` | `20260902T154027Z-358cec55` | **novo_elegivel** | PASS | incluído |
| `db31fa40` | `20260902T154529Z-db31fa40` | **novo_elegivel** | PASS | incluído |
| `8c4e5912` | `20260902T155028Z-8c4e5912` | **novo_elegivel** | PASS | incluído |
| `4d39411f` | `20260902T155530Z-4d39411f` | **novo_elegivel** | PASS | incluído |

Todos: `spontaneous_cognitive` · origem `prac_soak_2026_09_02_long` · archive PRAC íntegro.

**Nota hashes:** `market_snapshot_hash` no evidence-chain é hash do **intent**; corpus enriched usa hash de **envelope** computado — verify v7 **4/4 PASS** com `manifest_trust: ok`.

---

## Coorte v7 (offline)

| Item | Valor |
|------|-------|
| Envelopes | **4** (afternoon · long origin) |
| Digest | `evaluation/runs/stratified-cohort-digest-v7-2026-09-02.json` |
| Digest SHA256 | `1020808345f1c2c7087cfe5eeedc1b6c33e1d8d1d2cd5d8adaa94d546205778f` |
| Verify | **4/4** sem `--skip-validation` |
| Seleção | `STRATIFIED-COHORT-V7-SELECTION-2026-09-02.md` |
| Critério ≥3 elegíveis | **ATINGIDO** |

**Não autoriza replay** — revisão técnica + autorização humana obrigatórias.

---

## v6 (preservada, adiada)

Coorte v6 permanece **válida** e pré-registrada, porém **não recomendada** para objetivo de gate (`max_gate_after_replay: 4/5`). Ver `V6-GATE-DECISION-2026-09-02.md`.

---

## Ressalva gate

`≥5/5` é **gate mínimo**, não prova de superioridade. Antes de agregador offline ainda exige:

- independência dos pares;
- estabilidade intra-perfil;
- ausência de viés de seleção;
- cobertura de instrumentos e regimes;
- correlação/diversidade entre perfis;
- custo e latência aceitáveis;
- revisão qualitativa das teses.

---

## Bloqueios inalterados

Agregador executável · paralelismo · shadow · promoção · `next_authorized_run_id: null`
