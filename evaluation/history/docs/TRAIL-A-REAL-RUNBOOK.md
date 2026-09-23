# Trilha A — primeira execução Hermes real controlada

**Status:** preparado · **aguardando autorização humana** · sem Hermes invoke automático.

## Escopo fixo

```text
1 envelope (20260901T134026Z-bb50bbe9)
→ baseline-current + structure + adversarial-risk
→ max_parallel_slots=2
→ evaluation lane isolada
→ agregador offline
→ sem gateway / outbox / intents / receipts / shadow / promoção
```

Config pinada: `evaluation/trail-a-real-run-config.v1.json`  
Cenário: `evaluation/trail-a-real-scenarios.v1.json`

## Fase 0 — testes offline (obrigatório)

```powershell
cd C:\Users\arifr\Projects\glitch-topstep-hermes-profile

python scripts\run-trail-a-acceptance.py
python -m unittest discover -s tests -p "test_*.py" -v
cd ..\glitch-topstep
npm run check
```

## Fase 1 — preflight (sem Hermes)

```powershell
cd C:\Users\arifr\Projects\glitch-topstep-hermes-profile

# OAuth evaluation (uma vez, se necessário)
hermes -p glitch-topstep-evaluation auth add openai-codex --type oauth

python scripts\run-trail-a-real-preflight.py `
  --run-id trail-a-real-2026-09-02 `
  --output evaluation\runs\trail-a-real-preflight-report.json
```

**Critério:** `verdict: PASS` e `ready_for_human_authorization: true`.

**Não iniciar gateway novo.** Esta execução não depende de trading ativo.

## Fase 2 — PARAR para autorização humana

Somente após preflight PASS, autorizar explicitamente o run real.

## Fase 3 — execução Hermes real (após autorização)

```powershell
python scripts\run-trail-a-parallel-live-evaluation.py `
  --run-id trail-a-real-2026-09-02 `
  --authorize `
  --output evaluation\runs\trail-a-real-2026-09-02.json
```

**Abortar se:** write operacional · hash divergente · custo desconhecido · lease não liberado · output inválido.

## Fase 4 — pós-execução

```powershell
python scripts\audit-trail-a-real-artifacts.py evaluation\runs\trail-a-real-2026-09-02.json
```

## Gate pós-run

```text
parallel_evaluation_real = pass/fail
aggregator_offline_real = pass/fail
production_parallelism = blocked
shadow = blocked
promotion = blocked
```
