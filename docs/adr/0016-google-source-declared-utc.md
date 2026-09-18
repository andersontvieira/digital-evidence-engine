# ADR 0016 — UTC declarado no contrato Google 1.1.0

Status: aceita por autorização explícita na continuação da Milestone 3A.

## Contexto

Google 1.0.0 preserva como raw_only a variante textual `YYYY-MM-DD HH:MM:SS Z`.
O literal Z declara UTC, mas o espaço antes dele não pertence ao contrato genérico
da ADR 0015. O registro histórico dessa decisão e suas derivações permanecem válidos.

## Decisão

Publicar somente google.event_normalizer 1.1.0, mantendo os contratos 1.0.0 e
adicionando essa variante exata. Exigir dígitos ASCII, ano de quatro dígitos,
campos restantes de dois dígitos, espaços literais, Z maiúsculo e nenhum texto
extra. Validar calendário, hora, minuto e segundo com biblioteca padrão.
Resultado: normalized / explicit_utc, com precisão fixa de microssegundos e Z.
Não há parser fuzzy, heurística ou dependência nova.

A regra é específica do Google 1.1.0 e só opera após seleção dos contratos
SubscriberInfo/ChangeHistory. Não se declara suporte ISO genérico por semelhança
visual. Meta/Apple e Google 1.0.0 continuam usando as regras temporais anteriores.
O comportamento histórico Google 1.0.0 permanece executável e testado por instância
explícita; o registry produtivo seleciona somente Google 1.1.0.

Schema permanece v3; não há migração. Parsers, ParsedRecords, seus raw, payloads,
annotations e proveniência não mudam. Nenhum UPDATE/DELETE/rewrite de eventos
históricos é realizado. Identidade já inclui versão: 1.0.0 e 1.1.0 coexistem como
derivações da mesma observação, não acontecimentos independentes adicionais.

## Validação e consequências

Fazer backup consistente v3 antes da nova execução; preservar também o backup v2.
Comparar fingerprints de todas as linhas anteriores. Testes sintéticos cobrem
formato exato, datas/horas inválidas, variantes próximas, isolamento das outras
plataformas, compatibilidade anterior, coexistência e idempotência.

A validação externa seleciona explicitamente o conjunto de versões atuais:
Meta 1.0.0, Google 1.1.0 e Apple 1.0.0. A contagem física inclui as derivações
históricas. Não criar tabela/view persistente para seleção de versões; políticas
de search/timeline permanecem futuras. Formatos fora dos contratos continuam
raw_only, com raw preservado. Não inferir timezone, identidade ou autoria.
