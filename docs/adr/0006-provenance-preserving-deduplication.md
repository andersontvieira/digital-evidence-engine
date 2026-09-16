# 0006 — Deduplicação preservando proveniência

## Status

Aceito como decisão arquitetural; implementação conforme o roadmap.

## Context

O mesmo conteúdo ou evento pode aparecer em exportações distintas, com suporte complementar ou divergente.

## Decision

Separar identidade de conteúdo, ocorrência de fonte e evento lógico. Manter todos os SourceRecords e vínculos N:N de suporte ao consolidar eventos; registrar critério e versão da deduplicação. Preservar referências até originais e SHA-256.

## Consequences

Deduplicação não será exclusão destrutiva de registros de origem. Divergências e aquisições distintas continuam consultáveis, mesmo com hash igual. Similaridade incerta gera candidato a correlação. Schema e algoritmos serão implementados em milestones posteriores.
