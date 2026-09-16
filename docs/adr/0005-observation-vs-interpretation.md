# 0005 — Observação e interpretação separadas

## Status

Aceito como decisão arquitetural; implementação conforme o roadmap.

## Context

Valores presentes em exportações, transformações técnicas, relatos e hipóteses têm naturezas diferentes.

## Decision

Representar OBSERVED, DERIVED, REPORTED e HYPOTHESIS nas afirmações. Preservar suporte e natureza por campo quando necessário; derivações registram método/versão/entradas, relatos atribuição, hipóteses justificativa e incerteza.

## Consequences

Mais contexto será necessário nos contratos e relatórios. As categorias não constituem escala automática de verdade. Nunca substituir ausência por inferência silenciosa ou promover uma hipótese a fato. Somente o modelo conceitual é definido agora.
