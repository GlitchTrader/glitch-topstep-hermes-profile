# Diagnóstico `partial_evidence` — 2026-09-01

**Gerado:** 2026-09-02T01:01:25.082445Z
**Veredito:** `mixed_corpus_and_profile_divergence`

## Resumo

- Frames analisados: **24**
- Afeta baseline e structure igualmente: **False**
- Mismatch baseline↔structure completeness: **24** frames

## Histograma corpus (campos `partial` no packet)


## Causa raiz

indicators/ohlc/structure marcados partial pelo capacity_gate porque o packet contém barra 1m incompleta ou subset de paths no source_catalog — problema do corpus/captura, não do baseline isoladamente

## Recomendação

Não alterar baseline. Próximo PRAC soak: capturar em fechamento de barra 1m ou enriquecer packet com data_quality.state_complete=true quando aplicável.
