# Checklist operacional — sessão PRAC v9

**Data:** 2026-09-02  
**Fase:** `PRAC_COLLECTION` · pós-r16 · `STOP_RERUNS` v8  
**Coorte alvo:** v9 (offline pré-registrada)  
**Escopo:** captura operacional PRAC-proven · **sem** replay Hermes neste documento

**Referências:** `STRATIFIED-COHORT-V9-PREREGISTRATION-2026-09-02.md` · `glitch-topstep/docs/evidence/PRAC-NEXT-SESSION-CHECKLIST.md` · `V8-MULTI-INSTRUMENT-OBSERVATION-REVIEW-2026-09-02.md`

---

## Bloqueios (não negociável)

```text
next_authorized_run_id     null (até assinatura humana pós-coorte v9)
repetir v7 / v8            PROIBIDO
agregador executável       BLOCKED
paralelismo Hermes         BLOCKED
shadow / paper / canary    BLOCKED
promoção                   BLOCKED
```

**Durante a sessão — proibido alterar:**

- prompt / versão de prompt
- adapter ou contrato paired
- registry de autorização de replay
- regras de decisão do perfil ou gateway

---

## Classificação de evidência

```text
testes/unitários       = source-tested
replay Hermes          = replay-proven
sessão PRAC            = PRAC-proven
produção armada        = armed-promoted
```

Nenhum resultado PRAC-proven autoriza promoção ou replay sem trilha offline completa.

---

## Critérios de diversidade v9 (conceitual)

| Critério | Regra |
|----------|-------|
| Instrumentos | **≥2 instrumentos disponíveis** na evidência ou **observados naturalmente** no packet/universe — **não forçar decisões** |
| Decisão efetiva | Registrar **qual instrumento foi efetivamente decidido** em cada ciclo (pode ser `NOTHING` / abstinência) |
| Observado vs decidido | Distinguir `instruments_observed` (universe/packet) de `instrument_decided` (intent/decisão) |
| Exclusão offline | Frames **sem capacidade comparável** (`capacity_gate_pass: false`) ficam fora da coorte |
| Horários | Preferir **faixas distintas** na mesma sessão (evitar janela única curta) |
| Cenários | Preferir **≥2** `scenario_tag` ou buckets de sessão distintos quando ocorrerem naturalmente |
| Barras | 1m **completas** · `state_complete: true` quando possível |
| Espontâneos | Mínimo **≥3** frames espontâneos **elegíveis** pós-ingest para montar coorte |
| Entradas | **Proibido forçar entradas** ou dirigir ciclos para inflar coorte |

---

## Janela e captura

| Item | Orientação |
|------|------------|
| Janela mínima recomendada | **≥30 min** contínuos; preferencial **45–90 min** se operacionalmente seguro |
| Modo | Captura **contínua** — não cherry-pick de momentos |
| Primeiro ciclo | Registrar **UTC** do primeiro ciclo espontâneo (`first_spontaneous_cycle_utc`) |
| Journal | Preservar journal completo; não truncar `decisions.jsonl` / `receipts.jsonl` antes do export |
| Falhas | Preservar qualquer falha parcial — não limpar state para “recomeçar limpo” |

---

## Antes de abrir a sessão

### 1. Inicializar sessão (gateway)

```powershell
cd C:\Users\arifr\Projects\glitch-topstep
. .\scripts\init-prac-session.ps1 -SessionId "PRAC-SOAK-AAAA-MM-DD-v9"
$env:PRAC_SESSION_ID
$env:PRAC_EVIDENCE_DIR
```

Substituir `AAAA-MM-DD` pela data real. **Dot-source** (`. .\`) — não `-File`.

### 2. Pré-voo

- [ ] `validate-prac-capture-chain.py --example` exit **0**
- [ ] Smoke export: `validate-prac-evidence-chain.py` em fixture minimal-complete exit **0**
- [ ] Credenciais PRAC aprovadas; profile **`glitch-topstep`** isolado (sem eval/replay)
- [ ] `HERMES_HOME` confirmado

### 3. Gateway e health

- [ ] Gateway iniciado (`start.ps1` ou equivalente)
- [ ] `GET /health` → conta **flat**
- [ ] `unprotected_open_quantity` = **0**
- [ ] `execution_recovery_blocking` = **false**
- [ ] `data_quality.state_complete` = **true** (ou degradação **registrada** antes de ciclo espontâneo)
- [ ] Cron de produção **ativo** (coordenação lease já `LIVE_VALIDATED` — não pausar sem motivo)

### 4. Registro de início

| Campo | Valor (preencher) |
|-------|-------------------|
| `session_id` | |
| `origin` (esperado) | `prac_soak_<tag>_v9` |
| `first_spontaneous_cycle_utc` | |
| Operador | |
| Gateway URL | `http://127.0.0.1:8790` |

---

## Durante a sessão (checklist contínuo)

- [ ] Captura contínua — sem pausas longas não documentadas
- [ ] **Não forçar entradas** nem alterar instrumento manualmente para “cumprir meta”
- [ ] A cada ciclo espontâneo relevante, anotar:
  - `instruments_observed` (universe/packet)
  - `instrument_decided` (decisão efetiva do perfil)
  - `scenario_tag` / bucket de sessão
  - `state_complete` no momento do packet
- [ ] Testes 6–11 (`prac_directed_execution`): apenas evidência **operacional** — não contam para gate cognitivo
- [ ] Confirmar cadeia: `packet_id` → `snapshot_hash` → `intent_id` → decisão → receipt

---

## Condições de parada (preservar tudo)

Interromper captura **imediatamente** se:

- `ambiguous_mutations` > 0 ou mutação ambígua equivalente
- `unprotected_open_quantity` > 0
- `execution_recovery_blocking: true`
- Integridade do state comprometida (journal truncado, prune, epoch reset não planejado)
- Divergência `packet_id` ↔ `snapshot_hash`
- Falha de export ou `chain_complete: false` no fechamento

**Ação:** preservar `state/`, logs e artefatos brutos; exportar o possível; **não** ingerir nem montar coorte até revisão.

---

## Ao fechar a sessão

### Export

- [ ] `SinceUtc` = UTC real do **primeiro ciclo espontâneo** (não estimativa)
- [ ] Export com `chain_complete: true`
- [ ] `validate-prac-evidence-chain.py` no diretório de evidência exit **0**
- [ ] Conta **flat** pós-sessão; health revalidado

### Pós-export (profile — offline)

```text
ingest
→ auditoria de consumo (novo_elegivel / already_consumed)
→ inventário v9
→ build v9 --latest-origin <origin_real>
→ digest
→ verify-stratified-cohort (sem --skip-validation)
→ revisão técnica
```

**Regra de montagem:** coorte v9 **somente** se **≥3** frames espontâneos **novos** e com **capacidade comparável**. Caso contrário: **não inflar** seleção — documentar lacuna e abrir nova PRAC com justificativa.

```powershell
cd C:\Users\arifr\Projects\glitch-topstep-hermes-profile

python scripts\run-prac-corpus-ingest.ps1 -SessionId "<PRAC_SESSION_ID>"
python scripts\audit-prac-frame-consumption.py -SessionId "<PRAC_SESSION_ID>"
python scripts\inventory-unused-cohort-frames.py --cohort-version v9
python scripts\build-stratified-cohort.py --cohort-version v9 --latest-origin <origin>
python scripts\digest-stratified-cohort.py evaluation\runs\stratified-cohort-manifest-v9-2026-09-02.json
python scripts\verify-stratified-cohort.py evaluation\runs\stratified-cohort-manifest-v9-2026-09-02.json
```

---

## Referências cruzadas (pós-sessão)

- `evaluation/reviews/V9-PRAC-SESSION-REPORT-2026-09-02.md` — template relatório pós-export

## Depois da coorte v9 (somente pós-assinatura humana)

```text
registry recebe r17 (autorização explícita)
→ replay sequencial
→ QC
→ proveniência
→ custo/latência
→ novo gate
```

Se gate permanecer `<5/5`: **não repetir v9** — nova PRAC com justificativa pela lacuna observada.

---

## Estado do plano

Fundação e coordenação runtime validadas (~**50%** do plano global). Próximo avanço: **qualidade da evidência** via PRAC v9 diversa — sem agregador, paralelismo ou promoção.
