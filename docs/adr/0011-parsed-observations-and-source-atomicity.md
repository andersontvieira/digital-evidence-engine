# 0011 — Observações de parsing e atomicidade por fonte

## Status

Aceito e implementado na Milestone 2A.

## Context

Precisamos extrair três artefatos Meta mantendo valores, localizadores e proveniência,
sem antecipar normalização ou correlação. Uma falha numa fonte não deve produzir
meio conjunto de observações válidas nem impedir processar fontes independentes.

## Decision

Usar contratos pequenos Parser/ParserContext/ParserResult/ExtractedRecord. Parsers
puros declaram ID/versão e exigem path mais schema. Suportar somente os três contratos
explicitados no README, incluindo campos diretos e string_map_data quando presente.
Não inferir variantes históricas não demonstradas. JSON estrito recusa chaves
duplicadas e números não finitos; decoding UTF-8/BOM não repara valores textuais.

Adicionar ParsedRecord e ParserRun no schema v2. Catálogos novos recebem v2; v1
exige dee evidence migrate, aditivo/transacional. Não introduzir Alembic, não alterar
tabelas anteriores, não migrar silenciosamente. O manifesto de evidências continua v1.

Criar um SourceRecord preciso por ParsedRecord, referenciando diretamente a origem
da Foundation. Sua ingestion_run_id aponta para a aquisição da fonte; parser_run_id
em ParsedRecord identifica o processamento. ParserRun aponta ao SourceRecord de
inventário para registrar resultado mesmo quando não há observações válidas.

Locators usam $ e tokens JSON Pointer escapados: $/messages/17, por exemplo. A
conversa é uma observação em $ sem a lista de mensagens, que não é repetida nos
payloads. Validar resolução do locator, ausência de duplicatas e fidelidade do payload
ao objeto de origem antes de comprometer registros.

Transação BEGIN IMMEDIATE por fonte/parser e savepoint para todas as observações
e SourceRecords novos. Falha reverte o conjunto, grava apenas diagnóstico FAILED
e continua outras fontes. Fonte incompatível recebe UNSUPPORTED com warning.
Sucesso e resultados são atômicos no SQLite. Sem arquivos derivados de parsing.
Falha no commit final exige consulta do resultado durável antes de registrar erro:
uma tentativa já persistida é preservada, com erro operacional para revisão manual.
Se a transação foi desfeita, registrar COMMIT_FAILED quando o banco permitir.
Pré-verificação read-only antecede abertura gravável normal de catálogo existente;
assim um hot journal v1 não é recuperado antes da recusa de schema.

Unicidade de sucesso por fonte de inventário/parser_id/parser_version via índice
parcial; unicidade de registros por run/locator. Conferir hashes antes de reutilizar
sucesso. Preservar tentativas falhas e versões diferentes. Não usar fingerprint para
deduplicação: fonte + versão + locator já dão identidade técnica, enquanto hashes
da Foundation fixam o conteúdo. Exports diferentes permanecem observações distintas.

Manter timestamp_raw como valor JSON sem normalização. Dados ausentes permanecem
ausentes; múltiplos timestamps não são escolhidos por heurística. Classificação de IP
usa somente ipaddress. Model code literal do user agent é anotação com locator,
sem marketing name. Nenhuma transferência de IP, modelo ou identidade entre fontes.

## Consequences

PARSE não normaliza nem correlaciona. Novas variantes precisam de fixtures sintéticos,
contrato e revisão deliberada de parser_version. Limites fixos são 32 MiB de JSON,
profundidade 64 e 100000 registros/fonte. JSON não é streaming; limites não equivalem
a quota global de memória. Originais/derivados e catálogo devem permanecer confiáveis.

Warnings ficam no banco com códigos e locators, não valores completos no console.
Payloads e locators podem conter informação sensível do caso e ficam fora do Git.
Crash antes do commit reverte a fonte; falha global de armazenamento pode impedir
persistir diagnóstico, e fontes anteriormente concluídas continuam comprometidas.
Não há recovery/reparse sofisticado. Banco v2 não é compatível com runtime M1/v1;
backup consistente deve preceder a migração explícita.
