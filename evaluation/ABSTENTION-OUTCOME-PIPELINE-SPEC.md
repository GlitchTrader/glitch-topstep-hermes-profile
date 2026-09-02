# Pipeline — outcome da abstinência (diagnóstico)

**Status:** `IMPLEMENTED_OFFLINE`  
**Script:** `scripts/build-abstention-outcome-associations.py`  
**Classificação:** `diagnostic_only` · `promotion_use_allowed=false`

---

## Objetivo

Quando existirem dados de mercado posterior no corpus, associar cada invocação `no_edge` a métricas de excursão — **sem** rotular “acerto” até definição de outcome aprovada.

---

## Campos por associação

| Campo | Descrição |
|-------|-----------|
| `horizon_minutes` | janela posterior (default 15) |
| `posterior_frame_count` | frames no horizonte |
| `mfe_long` / `mae_long` | excursão favorável/adversa long |
| `mfe_short` / `mae_short` | excursão favorável/adversa short |
| `first_touch` | `up` \| `down` \| null (primeiro tick além do referência) |
| `adverse_excursion_max` | pior excursão adversa (qualquer direção) |
| `contrafactual_direction` | long \| short (melhor edge bruto no horizonte) |
| `contrafactual_edge_ticks` | magnitude em ticks — **não** é label de qualidade |
| `evidence_completeness_tier` | complete \| partial \| insufficient no momento da abstinência |

---

## Uso proibido

- Promoção de perfil
- Converter `no_edge` em `thesis_quality`
- Afirmar “abstinência correta/incorreta” sem outcome definition aprovada

---

## Comando

```powershell
python scripts/build-abstention-outcome-associations.py --output evaluation/runs/abstention-outcome-associations-2026-09-02-v1.json
```

Saída default: `evaluation/runs/abstention-outcome-associations-2026-09-02-v1.json`

---

## Dependências futuras

- Feed de outcomes enriquecidos (gateway) para substituir excursão proxy por outcome real
- Definição humana de “outcome aprovado” antes de qualquer gate de abstinência promocional
