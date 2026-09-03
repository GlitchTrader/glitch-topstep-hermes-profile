# Pendência técnica — coordenação evaluation × cron

**Status:** `LIVE_VALIDATED` + revisão técnica **APPROVED** (2026-09-02)  
**Replay:** bloqueado por **amostra** (gate 2/5) e **coorte v8** — não por runtime  
**Não bloqueia:** captura PRAC · ingest · coorte offline

---

## Estado

```text
evaluation×cron        LIVE_VALIDATED
revisão técnica       APPROVED (coordenação)
preflight             verde (2026-09-02T16:50:30Z)
gate cognitivo        2/5
next replay           coorte v8 + autorização humana
```

**Artefatos:** `LEASE-COORDINATION-TECHNICAL-REVIEW-2026-09-02.md` · `preflight-coordination-review-2026-09-02.json`

---

## O que a validação do lease **não** autoriza

- Replay cognitivo (exige coorte nova pré-registrada)
- Paralelismo Hermes
- Agregador executável
- Shadow / paper / canary

---

## Próxima sequência (amostra cognitiva)

```text
nova PRAC diversa
  → ingest + inventário
  → coorte v8 (não v6/v7)
  → revisão + autorização
  → replay sequencial
  → QC + novo gate
```

Pré-registro: `STRATIFIED-COHORT-V8-PREREGISTRATION-2026-09-02.md`
