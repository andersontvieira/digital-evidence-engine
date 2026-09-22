# ADR 0034 — Exact Source–Media Provenance Link

Status: Accepted; gates sintéticos e fechamento de integridade real concluídos.

## Contexto e design gate

A revisão analítica externa 8A3 demonstrou uma cadeia específica de referência
de fonte até mídia. Seus artefatos e dados não fazem parte do repositório.
A auditoria do modelo confirmou que ParsedRecord.payload_json preserva o item
integral e que annotations_json contém observed_field/uri, valor literal e
source_locator nos arrays Meta 1.1.0. Nenhuma mudança de parser, contrato
persistido, schema, normalizer, reparse ou reingestion é necessária.

## Decisão e source-reference contract

Policy `source_media.provenance_link / 1.0.0`, feature_class DERIVED, relation_kind
`source_media.exact_provenance_link`. CLI `dee media source-links` com start/end
UTC Z obrigatórios, intervalo [start,end), filtros platform/event-kind exatos e
limit default 500, entre 1 e 5000. Usa current_event_policy vigente sem latest.

O adapter explícito aceita somente parser_id=meta.recently_deleted_content,
parser_version=1.1.0, record_type=recently_deleted_content. No payload do item
array, em locator $/N, percorre somente label_values com label literal Mídia
ou sua variante já contratada pelo parser (`M\u00c3\u00addia`), lista media e
campo direto uri de cada objeto. Não pesquisa recursivamente, não usa outros
campos uri, metadata, annotations ou originais como fallback. Não repara texto.
O reconhecimento das duas variantes de label não transforma reference_value.

Payload é decodificado como JSON estrito. Estrutura contratada malformada ou
URI não textual gera erro técnico global. Campo ausente/null/string vazia não
produz referência. Campos/containers não contratados permanecem fora da busca;
o formato objeto legado não possui campo aprovado por este adapter v1.
Contrato de parser/version/type não aprovado produz UNSUPPORTED_SOURCE_REFERENCE_TYPE;
contrato aprovado sem referência produz NO_SOURCE_MEDIA_REFERENCE. Não significa
que o artefato inteiro não possua mídia. Novos adapters exigem escopo e testes.

SourceMediaReference preserva parsed_record_id, platform, parser_id/version,
source_field_locator, reference_value literal e classification=OBSERVED.
Referências múltiplas conservam seus locators, mesmo com valores iguais.
Annotations já disponíveis corroboram a viabilidade do design; o resolver
consome diretamente o campo contratado do payload persistido.

## Matching exato e path safety

Provenance existente determina o EvidenceFile da fonte. A consulta exige esse
ID e igualdade BINARY literal com ArchiveMember.member_path. Sem basename,
substring, suffix, case folding, URL decode, slash rewriting ou normalização
Unicode/path. Zero matches produz NO_CATALOG_MEMBER_MATCH, limitado ao catálogo
e ao container consultados; não afirma inexistência histórica. Mais de um
match gera SOURCE_MEDIA_CATALOG_MEMBER_CARDINALITY, nunca escolha arbitrária.

Referência é dado, nunca argumento para construir caminho de filesystem.
Mesmo ../, drive, NUL ou referência com aparência absoluta só participa da
comparação SQL. O valor literal pode aparecer como dado no JSON técnico; nenhum
caminho absoluto operacional é gerado ou divulgado. Após match, member_path
catalogado inseguro é recusado. O arquivo original é selecionado exclusivamente
no inventário seguro de paths descobertos da Foundation, pela referência
catalogada do container. Não há extração ou escrita a partir do member_path.

A validação de identidade lógica reutiliza archives.validate_name, a primitive
canônica da Foundation, tanto para o valor catalogado quanto para ZipInfo real.
Dois-pontos seguros, como logical:name.jpg, são aceitos sob ADR 0014. Drives,
absolutos, traversal, backslashes, controles/NUL, Unicode não NFC e nomes
reservados/não portáveis permanecem recusados. Nenhuma normalização transforma
a igualdade de lookup. Diretórios não podem virar identidade de arquivo.
working_relative_path é caminho físico separado; materialized_path continua
recusando dois-pontos. A exceção lógica não autoriza destinos físicos ou ADS.

## Verificação de ArchiveMember e falhas

Abre o original com original_reader (checks de path, identidade e estabilidade
antes/depois). Exige container ZIP e uma única entrada com filename literal.
Membro ausente/duplicado gera SOURCE_MEDIA_ZIP_MEMBER_CARDINALITY. Confere
file_size, SHA-256 e bytes lidos contra o membro catalogado; divergência gera
CATALOG_MEMBER_INTEGRITY_MISMATCH. Confere também SHA/tamanho do container no
mesmo handle. Erros de ZIP geram códigos técnicos sem reproduzir dados da fonte.

Qualquer falha operacional/integridade invalida a consulta inteira, exit 2,
sem JSON parcial e sem atualizar baseline. Todos os itens correspondentes à
consulta são resolvidos/verificados antes do limit; erro depois do prefixo
também falha globalmente. Não equivale a auditoria de todos os ZIP members não
referenciados: inventory mantém seu próprio escopo de verificação já existente.

## Reuso de ExactMediaContent e member-only

Extraiu-se inventory_in_snapshot, preservando o wrapper inventory_media e seu
algoritmo. O serviço reutiliza essa primitive e project_contents existentes,
sem nova detecção de formato ou agrupamento SHA. O inventário continua verificando
originais/materializações de working, inclusive ocorrências não reconhecidas.
Portanto, problema em outra ocorrência desse inventário também pode invalidar
a consulta. Os JSONs de origem podem ser lidos para hash pelo inventário, nunca
para redescobrir semanticamente uma referência.

Lookup de conteúdo exige a ocorrência exata (IDs de container/member e path),
além de coerência SHA/tamanho. LINK_EXACT_MEDIA_CONTENT contém IDs persistidos,
member_path, SHA/tamanho verificados e o ExactMediaContent existente completo,
incluindo todas as occurrences e occurrence_count. Representative não recebe
prioridade evidenciária. Duplicação em outras fontes não muda a origem do link.

LINK_ARCHIVE_MEMBER_ONLY significa apenas membro verificado sem correspondente
no conjunto ExactMediaContent da policy consultada. Não significa arquivo inválido,
ausência de mídia ou incapacidade geral de processar o formato. MP4/MOV genéricos
não são incorporados implicitamente. A policy de formatos permanece inalterada.

## Output, classificação, ordenação e limit

Envelope: policy, scope, consistency, summary, items. Cada item separa event
(os nove campos existentes da timeline), source_reference ou null, provenance,
resolution e limitations. Link/resolution são DERIVED; campo extraído é OBSERVED.
Sem payload integral, clock, generated_at, UUID novo, random, score ou confidence.
stdout ASCII JSON determinístico com LF explícito; nenhuma saída automática.

Ordenação: UTC, platform, event_kind, event_id, source_field_locator e
reference_value. Evento sem referência gera um item com source_reference=null.
Eventos sem UTC suficiente são excluídos da janela e contados separadamente,
sob os mesmos filtros current/platform/kind da timeline; não recebem posição
temporal inventada. Empates são resolvidos por IDs/locators, nunca por status.

summary distingue eligible_events, source_references e unidades
event_source_reference_items. matched_total/returned/truncated referem-se a
itens, que podem exceder eventos. status_counts cobre TODOS os matched items,
explicitamente, e limit materializa somente seu prefixo canônico. Contar e
verificar todo o universo pode exigir memória/tempo mesmo com limit pequeno.

## Consistência e ausência de persistência

Uma conexão/read transaction, SQLite mode=ro/query_only, BEGIN e schema v5 para
eventos, payloads, provenance, resolução e catálogo de mídia. Leitura de bytes
usa checks de estabilidade independentes: não há atomicidade DB + filesystem.
consistency declara esses escopos e se ExactMediaContent foi consultado. Quando
não há membro a resolver, não executa inventário de mídia sem necessidade.

Nenhuma tabela, run, candidate, observation, event, parser run, media row,
cache, view, índice ou migration. Sem alterações de dependências ou lockfile.
Preservação de atime depende do mount; validação real usa originais ro/noatime.

## Limitações e fronteiras 8A4.1

Limitações por item: SOURCE_REFERENCE_DOES_NOT_ESTABLISH_ACTION_SEMANTICS;
NO_IDENTITY_AUTHORSHIP_SESSION_OR_CAUSALITY; EXACT_MEMBER_PATH_EQUALITY_ONLY;
EXACT_MEDIA_CONTENT_LIMITED_TO_CURRENT_MEDIA_POLICY;
ABSENCE_LIMITED_TO_CATALOG_AND_QUERY_SCOPE; NO_MESSAGE_ATTACHMENT_INFERENCE.

Link não afirma published/uploaded/sent/deleted/authored/owned. Não usa pHash,
similaridade, tempo, thread, dispositivo ou rede para escolher mídia. Não é
atribuição de evidência a pessoa, sessão ou aparelho físico.

communication.message não tem adapter nesta versão, mesmo que um payload
sintético contenha URI. Attachments sem referência suficiente permanecem
SOURCE_LIMITATION. WhatsApp permanece condicional e fora do escopo.

8A1 e 8A2 não mudam: flags/limitações desses contratos descrevem o escopo de seus
próprios snapshots. A integração da nova query ao relatório humano pertence à
8A4.1 futura, com versionamento/contrato próprio. A 8B continua futura.

## Consequências e validação

A cadeia anteriormente externa passa a ser uma capacidade técnica reproduzível,
com cobertura estreita e explícita. Há leituras repetidas do container por membro,
verificação case-wide do inventário e materialização dos itens antes do prefixo;
não se introduz cache ou otimização que enfraqueça checks.

Baseline anterior à implementação: 950 testes PASS, exit 0. Após a correção de
compatibilidade ADR 0014: 108 testes sintéticos da capacidade PASS no Windows;
450 testes focados e regressões PASS no Linux. Suíte final: 1058 coletados,
1058 PASS, zero falhas, exit 0. Ruff check/format PASS; mypy Linux PASS em 70
módulos; helps raiz/media/source-links PASS. Hashes do produto e dos testes
conferidos contra esse estado; sem mudança posterior nesses arquivos. A suíte
completa não foi repetida no fechamento. Ruff check/format e mypy Linux passaram
novamente; somente helpers ignored e documentação foram ajustados no fechamento.

Validação real concluída: comparação independente EQUAL, determinismo Linux e
comparação com o JSON parcial preservado BYTE_IDENTICAL. DB SHA/bytes, schema,
contagens de todas as tabelas e membership/tamanho/mtime dos originais preservados;
nenhum run persistido. Mode, atime e ctime também permaneceram iguais no gate
controlado. Verificação de conteúdo final e revisão de privacidade passaram.

A tentativa anterior permanece registrada como incompleta: seu gate estrito de
metadados no host divergiu. O diagnóstico histórico ampliado separa observações
entre plataformas da comparação com a baseline POSIX anterior. A causa e o
momento da deriva histórica não foram estabelecidos; nenhum metadado foi
restaurado ou ajustado. O fechamento usou uma nova baseline do estado atual,
após preservar o JSON parcial, sem alegar igualdade com os metadados históricos.

Execução final exclusivamente em Linux, originais ro/noatime, sem rede, não root,
SQLite mode=ro/query_only. Atime é observacional; permaneceu igual nesse mount.
Ctime é invariante POSIX conforme Foundation; ctime/birthtime Windows não foi
convertido em invariante de mutação. A paridade Windows/Linux BYTE_IDENTICAL
pertence à execução anterior do mesmo código corrigido, atestada pelos hashes;
a consulta Windows não foi repetida nos originais durante o fechamento final.

Fixtures são sintéticas; helpers ignored, snapshots e artefatos reais permanecem
locais/externos ao Git. O relatório externo distingue validação do produto,
tentativa incompleta, observações históricas e fechamento da nova baseline.
