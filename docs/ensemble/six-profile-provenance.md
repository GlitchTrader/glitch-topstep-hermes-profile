# Hermes Ensemble — proveniência da suíte six-profile

Data: 2026-09-14

## Referência canônica

O profile canônico é `main`, commit
`041f60b9eb6a3591d9e9de2195ebe68bb192a044`. O plano
`2026-09-01-hermes-ensemble-implementation-plan.md` é externo e não está
versionado neste repositório.

O gateway é a única autoridade para identidade do instrumento, contrato,
admissão de risco, execução, proteção, ProjectX, receipts e recovery. O profile
não executa mutações diretas no ProjectX.

## Linha histórica da suíte

Esta seção compara versões; não descreve uma cadeia linear de ancestralidade.

- `5c788a6afecf90babaa80ec72407fdbc04e5f708` (`test(ensemble): six-profile fixtures that reach real selection`, PR #237) é ancestral de `main`. Contém `tests/test_ensemble_evaluation.py` e `tests/test_ensemble_parallel_aggregator.py`, além das fixtures por perfil e escopo. Ainda não contém `tests/test_prac_live_ensemble.py`.
- `dde2937808097ff3de75f5666dd2d9984c5b6b53` (`feat(profile): add fail-closed Hermes PRAC ensemble runner`) existe no branch `codex/profile-runner-integration-reaudit`, mas não é ancestral de `main`. Adiciona `scripts/prac_live_ensemble.py`.
- `90d2ef6ec5a316de4af05638f11fd00cd02c810c` (`fix(profile): preserve Hermes diagnostics and preload stability`) existe no branch `codex/profile-runner-integration-reaudit`, mas não é ancestral de `main`. É o commit histórico registrado para o par v17.2.
- `041f60b9eb6a3591d9e9de2195ebe68bb192a044` (`fix: preserve Hermes diagnostics and restore replay coverage`, PR #246) é `main` e contém o runner atualmente presente no caminho canônico.

## Cobertura atual

A suíte contém fixtures e casos para MNQ, MES e MCL/MCLE em avaliação,
identidade, envelopes, seleção e agregação. Isso é cobertura offline/replay.

Não há prova live MES/MCL. A ausência de evidência live não deve ser convertida
em `no_edge`, `NOTHING` ou em uma autorização de seleção. Timeouts, erros e
`missing_required_evidence` permanecem estados distintos.

## Diferenças e lacunas

- A versão de `5c788a6` cobre avaliação e agregação, mas não o runner PRAC.
- A linha `dde2937` introduz o runner fail-closed.
- `90d2ef6` e `041f60b` preservam diagnóstico, preload, wiring e replay adicionais.
- A suíte existente não comprova, por si só, todos os testes exigidos pelo plano externo: `version_incompatible`, resultado atrasado, identidade divergente, quantidade inválida, MES/MCL completo, contrato fora do envelope, timeout e profile ausente.
- Esses casos aparecem parcialmente distribuídos entre os testes de ensemble,
  delivery, compatibilidade, fault injection e fixtures, mas exigem uma matriz
  específica antes de qualquer implementação P0.

## Objetos Git recuperáveis

Foram identificados objetos não referenciados, preservados somente como fontes
históricas:

- `32c13276ae4d604e06d4b794376ec12876a5a8b7`: replay determinístico e paper simulator;
- `2b90cec5848940b019e27c285a24d77826ea3cb4`: remediação IA-260901 HP-01..HP-09;
- A referência `11cffb4e60ed193bd3ddeca83cd4e4fe952e023` é inválida e não resolve. Ela foi removida como objeto identificado; não foi substituída por suposição. Os commits distintos `633f7fbe3c140fa895fc61babe3679932c3152bb` e `6c58e5f2c66e439d7b58cd06c8aded95729ad962` são candidatos históricos relacionados ao agregador de gates offline, mas não foram declarados equivalentes à referência inválida.
- `0f530fd219054b403238488aa10aa3a5b90888d9`: captura coerente baseada em `delivery_complete`;
- `7451c994e45a6d4817fef0d01ebf7dc83a49bda0`: correção de pins do pacote six-profile.

Esses objetos não foram restaurados, não foram podados e não substituem `main`.

## Dependências e limites

- A seleção cognitiva permanece observacional e separada da production lane.
- O profile produz avaliação e intenção conforme o contrato pareado; o gateway
  valida identidade, quantidade, direção, entrada, stop, alvo, envelope, lease,
  risco e estado operacional.
- Nenhum teste ou script foi restaurado ou alterado por este registro.
- Não fazem parte deste documento bancos, WAL/SHM, locks, caches, runtime,
  credenciais, `auth.json`, `.env`, tokens ou artefatos temporários.
