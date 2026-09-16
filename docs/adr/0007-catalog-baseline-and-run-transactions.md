# 0007 — Identidade, baseline e transações de catálogo

## Status

Aceito e implementado na Milestone 1.

## Context

O catálogo precisa de IDs portáveis, reingestão idempotente e auditoria de falhas,
sem apagar proveniência ou aceitar alterações de originais silenciosamente.
Não existe banco da Milestone 0 para migrar. Manifestos precisam ser reproduzíveis.

## Decision

Usar UUIDv4 para entidades e identidade de ocorrência por caso/path relativo.
EvidenceFile descreve originais; ArchiveMember descreve arquivos dentro de ZIPs.
SourceRecord referencia exatamente uma dessas origens. A ingestão cria referências
whole-file identificadas como inventário, sem fabricar registros de plataforma.

Persistir run RUNNING antes do trabalho. Usar BEGIN IMMEDIATE para catalogar todos
os novos registros de uma execução atomicamente. Alteração/ausência de originais
catalogados aborta a ingestão; baseline e registros anteriores ficam preservados.
Registrar FAILED em transação separada, com rollback dos novos registros.

Criar schema v1 em transação, identificado por PRAGMA user_version, com foreign_keys
em cada conexão. Recusar schemas desconhecidos/não versionados; dispensar Alembic
enquanto não houver evolução de schema. Mudanças seguintes exigem migration testada.

Manifestos ordenados usam generated_at=inventory_updated_at: o horário da última
mudança do catálogo, e não o instante de cada serialização.

## Consequences

Reingestão intacta mantém IDs e manifesto, mas adiciona um run. UUIDs/horários tornam
aquisições independentes distintas; determinismo vale no mesmo catálogo e versão.
Arquivos modificados exigem uma política futura explícita ou nova aquisição.
Falhas normais limpam somente staging próprio. Crash pode deixar RUNNING e staging
órfão, pois filesystem e SQLite não compartilham transação. Não há limpeza automática
de execuções anteriores. Datas operacionais são UTC; não são datas do conteúdo.
