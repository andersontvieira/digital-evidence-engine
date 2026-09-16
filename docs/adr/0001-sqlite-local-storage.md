# 0001 — SQLite como armazenamento local

## Status

Aceito como decisão arquitetural; implementação conforme o roadmap.

## Context

O motor precisa de persistência consultável, transacional e local, sem servidor ou cloud.

## Decision

Usar SQLite via SQLAlchemy 2.x a partir da Evidence Foundation. O banco ficará em /case/database, fora do Git. Criar baseline de schema versionada e habilitar chaves estrangeiras; alterações exigem migration e justificativa.

## Consequences

Distribuição e backup locais são simples. Concorrência de escrita é limitada; SQLite não oferece criptografia transparente por padrão. Definir transações, backup consistente e migrations na Milestone 1. Nenhum banco é criado na Milestone 0.
