# Lease coordination live validation — 2026-09-02

**Run ID:** `lease-smoke-2026-09-02`  
**Profile:** `%LOCALAPPDATA%/hermes/profiles/glitch-topstep`  
**Cron:** ativo (sem pausa manual)

## Resultado

| Fase | Resultado |
|------|-----------|
| Sync scripts + hashes | **PASS** — `state/lease-coordination-sync.json` |
| Smoke (lease → defer → release → resume) | **PASS** — `evaluation/runs/lease-smoke-2026-09-02.json` |
| Fault: abort | **PASS** |
| Fault: timeout | **PASS** |
| Fault: crash (orphan lease) | **PASS** |
| Fault: recovery | **PASS** |
| Artefatos operacionais | **inalterados** durante smoke |
| Defer durante janela cron natural | **observado** (`cron_defer_observed_during_window: true`) |

## Prova mínima (não foi replay cognitivo)

```text
evaluation ocupa lease
  → direct_cycle / learning / wake_monitor adiam (exit 0)
  → cron natural durante hold também adia
  → nenhum artefato operacional muda
  → evaluation libera lease
  → defer probe pós-release = false (cron pode retomar)
```

## Comandos

```powershell
# sync (hot-patch; não pausa cron)
powershell -ExecutionPolicy Bypass -File scripts/sync-evaluation-lease-scripts.ps1

# verificar hashes
powershell -ExecutionPolicy Bypass -File scripts/sync-evaluation-lease-scripts.ps1 -VerifyOnly

# smoke + fault
python scripts/run-evaluation-lease-smoke-test.py --run-id lease-smoke-2026-09-02 --mode all `
  --output evaluation/runs/lease-smoke-2026-09-02.json
```

## Pendente antes de replay cognitivo

- Revisão técnica formal
- Autorização humana explícita
- Preflight verde no `run_id` do replay (não só smoke)

**Pausa manual r15:** permanece workaround documentado apenas.
