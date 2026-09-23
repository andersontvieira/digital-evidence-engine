# ADR 0035 — Consolidated Report Media-Link Integration

Status: Accepted.

## Contexto e design gate

A 8A1 compõe incident_window_in_snapshot, incident_candidates_in_snapshot,
temporal_candidates_in_snapshot e overlap_in_snapshot na mesma Connection de
read_catalog. record_origin também recebe essa conexão. Mídia case-wide continua
com seus catálogos separados. A 8A4 dispõe de wrapper query_source_links que
abre seu próprio read_catalog; seu algoritmo pode ser extraído sem alteração.

Decisão: source_links_in_snapshot recebe CasePaths, Connection e filtros UTC
já validados. Wrapper público preservado. A janela 8A1 chama essa primitive na
mesma transação das outras consultas, sem subprocess ou serialização CLI.
Não há necessidade de parser, schema, persistência ou dependência adicional.

## Versionamento e compatibilidade

Novas saídas: report.data_snapshot / 1.1.0 e report.consolidated / 1.1.0.
source_media.provenance_link permanece 1.0.0. Conjuntos homogêneos históricos
1.0.0 continuam produzindo report 1.0.0, com templates e comportamento anteriores.
Fixture inteiramente sintética capturada antes da mudança preserva Markdown
legado byte-identical. Mistura de versões é erro REPORT_MIXED_SNAPSHOT_VERSIONS;
versão desconhecida é rejeitada. Não há conversão silenciosa de inputs antigos.
ADRs 0031–0034 permanecem históricos.

## Projeção e composição 8A1

Somente analysis_window não nula executa a nova consulta. Usa exatamente
start/end/platform/event_kind da janela, sem raio, evento vizinho ou candidates.
analysis_window.source_media_links contém policy, scope, consistency, summary
e items. Limite interno 1000, independente dos outros componentes: prefixo
determinístico, matched_total e status_counts do universo completo, returned e
truncated explícitos. Todos os matches continuam verificados antes do limite.

Items preservam evento técnico, referência OBSERVED sem reference_value,
resolução DERIVED e limitações. Resolução positiva conserva IDs de container e
membro, tamanho/SHA, bytes_verified e resumo opcional do ExactMediaContent
(SHA/tamanho/kind/formato/occurrence_count). IDs/hashes servem somente a provenance
e identificação técnica interna. Não copia occurrences inteiras nem paths.
provenance_index.parsed_records inclui os eventos desse prefixo; os containers
continuam no índice evidence_files. source_media_links no índice fornece
ponteiros lógicos para os items e IDs necessários ao drill-down.

URI, reference_value, member_path, paths absolutos, payload e mensagem pessoal
não entram na projeção nova. O renderer continua stdlib/EvidenceError e somente
JSONs: sem CASE_ROOT, SQLite, originals, working, query, 8A1 ou nova provenance.

## Findings, ordem e pointers

source_media_provenance_link é DERIVED somente para LINK_EXACT_MEDIA_CONTENT
e LINK_ARCHIVE_MEMBER_ONLY. NO_CATALOG_MEMBER_MATCH, NO_SOURCE_MEDIA_REFERENCE
e UNSUPPORTED_SOURCE_REFERENCE_TYPE são coverage/limitação, nunca finding positivo.
Status mantêm exatamente a semântica 8A4. Totais de findings positivos usam os
status_counts completos; returned conta positivos no prefixo, sem novo ranking.

Primeiro todos os tipos antigos na ordem histórica; depois findings source-media
por janela canônica e ordem de item. Isso conserva F-IDs antigos e W-IDs.
Apêndice humano usa analysis_window.source_media_links.items[N], sem imprimir
IDs persistidos, SHA ou locators da fonte. Referências múltiplas não são fundidas.

## Apresentação, classificação e gaps

Exatamente as 20 seções existentes, na mesma ordem. Integração em policies,
janelas, mídia, findings, limitações, gaps e apêndice; subseções são permitidas.
Cada novo finding apresenta F/W, UTC/platform/event kind, status, OBSERVED/DERIVED
e semântica conservadora. occurrence_count representa ocorrências catalogadas
do mesmo conteúdo exato; não envios, publicações, destinatários ou ações humanas.
Member-only: membro de arquivo verificado, sem correspondência em ExactMediaContent
sob a policy atual; não infere formato, vídeo ou invalidade.

Na 1.1 o flag case-wide media_event_link_available é removido. Resultados de
cobertura ficam na janela; a policy disponível é declarada mesmo no anchor.
Gap D descreve cobertura parcial quando há link positivo nos snapshots e
ausência de link aplicável somente no conjunto fornecido quando não há.
Não afirma ausência global da capacidade. A/E/F não são automatizados.

communication.message attachments permanecem SOURCE_LIMITATION: não há vínculo
por tempo, thread, dispositivo, rede, ordem ou proximidade. WhatsApp continua
condicional/não acionado; nenhuma SPECIFIC_TECHNICAL_BASIS é criada. Sem inferência
de publicação, upload, envio, exclusão, disseminação, identidade, autoria, sessão,
causalidade ou questão jurídica. REPORTED/HYPOTHESIS não são gerados.

## Consistência, privacidade e consequências

DB da janela e source-media compartilham read_catalog mode=ro/query_only/BEGIN.
Verificação de bytes usa Foundation sem enfraquecer path/handle/SHA/tamanho.
Filesystem continua separado; não há atomicidade DB/filesystem. Leituras
adicionais podem ampliar o custo/tempo de retenção da transação. Resumo de mídia
case-wide e pHash mantêm catálogos separados declarados no envelope.

Schema v5; sem migration, tabela, índice, view, run, cache ou entidade persistida.
Dependências e lockfile inalterados. Templates fixos, sem LLM ou integração externa.
Snapshots reais técnicos e relatório ficam externos ao Git. Markdown não publica
UUID, SHA, paths, URI, valores de device/rede, mensagens ou nomes de input.

## Validação

Baseline anterior à alteração funcional: 1058 PASS, exit 0, Linux.
Testes focados: 132 PASS; regressões Linux: 513 PASS. Suíte funcional final:
1093 coletados, 1093 PASS, exit 0. Ruff check/format PASS; mypy Linux PASS em
70 módulos; cinco helps CLI com exit 0. Os seis hashes de produto/testes conferem
com esse estado; a suíte completa não foi repetida no fechamento.

Fixtures exclusivamente sintéticas. A fixture 1.0 congelada permanece idêntica
à captura anterior à implementação. Revisão local identificou uma coincidência
entre sua data sintética preexistente e o filtro amplo de datas do caso; a
proveniência sintética foi confirmada sem editar ou regenerar a fixture.

Validação real final: PASS, exit 0. O histórico permanece distinto do fechamento:
uma tentativa anterior foi PARTIAL por igualdade integral de metadados, incluindo
atime. O diagnóstico posterior stat-only contra a baseline histórica 8A4 encontrou
diferenças somente de atime em 13 originais. Causa e momento não foram estabelecidos;
esse diagnóstico não reconstrói o pre-state perdido daquela tentativa.

A correção ficou no helper local ignorado da 8A4.1; produto, testes, fixture
congelada e helper histórico 8A4 não foram alterados neste fechamento. O comparador
passou em 38 verificações sintéticas locais. No Linux, membership, tamanho, mtime,
modo e ctime são invariantes obrigatórios; atime é observacional. No Windows,
atime e ctime/birthtime são observacionais. Working, database e outputs existentes
mantêm comparação estrita. SHA/tamanho, schema/definição, contagens e verificação
de bytes permanecem obrigatórios.

Uma execução intermediária corrigida passou nos gates de integridade e renderer,
mas parou no import local da revisão de privacidade, antes de gravar relatórios.
Após corrigir o caminho de importação no helper, o fluxo completo foi repetido com
uma nova baseline do estado atual. Na execução concluída, todos os invariantes
obrigatórios ficaram SAME; atime Linux/Windows e ctime Linux/Windows tiveram zero
diferenças. Nenhum metadado foi restaurado ou ajustado. O mount observado foi
9p, ro,noatime, sem rede e não root; SQLite mode=ro/query_only. Windows renderizou
somente os mesmos JSONs, sem executar source query nativa contra originais.

Os três snapshots 1.1 existentes foram regenerados em memória e comparados
byte a byte, sem sobrescrita. Projeção independente e regressão 8A4 EQUAL;
compatibilidade legada sintética e real BYTE_IDENTICAL. Repetição, permutação de
inputs e paridade Windows/Linux BYTE_IDENTICAL. Preservados 41 findings antigos,
acrescidos seis source-media, com F/W-IDs estáveis e exatamente 20 seções.
Gap D parcial; occurrence_count, member-only, attachments e WhatsApp conservam
as limitações acima. DB/schema v5/todas as tabelas inalterados, zero novos runs;
verify final: 13 OK. Revisões de privacidade do relatório e dos candidatos Git PASS.

Somente após esses gates foram criados o relatório humano e o relatório final
de validação, exclusivamente no output externo. A validação registra separadamente
o histórico PARTIAL, a observação histórica de atime e a baseline/execução frescas.
Não houve sobrescrita de artefatos históricos. 8B continua futura, com escopo próprio.
