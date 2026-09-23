# Revisão qualitativa de divergências — r7–r13 (2026-09-01)

**Escopo:** diagnóstico apenas — **não** conta para gate de amostra nem promoção.  
**Pares bilaterais canônicos:** **2/5** (r7 `SCN-PRAC-DIRECTED-02`, r10 `SCN-PRAC-RECONCILIATION`)

## Tipos observados

| Tipo | Exemplo | Conta como par? | Leitura |
|------|---------|-----------------|---------|
| Bilateral `thesis_quality` | r7 directed-02 | **Sim** (se independente) | Divergência de tese mensurável |
| `no_edge` ↔ `no_edge` | r9, r11, r13 (maioria) | Não | Abstinência alinhada |
| `thesis_quality` ↔ `no_edge` | r13 `8b20659b`, `a71c2714` | Não | Baseline `candidate`, structure abstém |
| `not_comparable` ↔ `thesis_quality` | r13 `ddd5ffb5` | Não | Baseline `data_quality_insufficient` |
| `no_edge` ↔ `held` | r10/r11 reconciliation | Não | Exposição existente vs abstinência |
| Intra-profile instability | r10 vs r11 mesmo snapshot | Não (repetibilidade) | `intra_profile_instability` documentado |

## r13 — divergências unilaterais (não superioridade)

| Frame | Baseline | Structure | Nota |
|-------|----------|-----------|------|
| `8b20659b` | candidate | no_edge | structure não confirma tese baseline |
| `a71c2714` | candidate | no_edge | idem |
| `ddd5ffb5` | data_quality_insufficient | held | categorias incompatíveis para par |

**Veredito:** resultado diagnóstico válido. **Não** interpretar como evidência de superioridade de nenhum perfil.

## Estabilidade observada

- Structure mais estável em `no_edge` sob `partial_evidence` (corpus estrutural)
- Baseline ocasionalmente emite `candidate` onde structure abstém — hipótese: política de entrada mais permissiva, não gap de evidência obrigatória (`missing_required: []` em r13)

## Uso permitido

- Informar desenho de coorte r14 (priorizar tags com potencial bilateral)
- Informar captura PRAC (evidência completa, fechamento de barra)
- Revisão estática do agregador (fixtures existentes)

## Uso proibido

- Promoção de perfil
- Alteração de baseline/prompt durante medição
- Inflar contador de pares com divergências unilaterais
