# Arquitetura

## Milestone 5B

Motor local sem rede e sem certificação pericial, com três parsers Instagram/Meta
e dois parsers Google Takeout (SubscriberInfo e ChangeHistory), além de três
parsers Apple (inventário de dispositivos, sign-on e atividade técnica de mídia).
Typer coordena a CLI; SQLAlchemy 2.x persiste SQLite; Pydantic 2.x valida limites
de ZIP e DTOs de manifesto, sem duplicar cada entidade ORM.

| Módulo                         | Responsabilidade                                                                         |
| ------------------------------ | ---------------------------------------------------------------------------------------- |
| cli/evidence.py                | Opções, mensagens técnicas e exit codes                                                  |
| config.py                      | Limites validados e imutáveis de ZIP                                                     |
| ingest/generic/paths.py        | Áreas do caso, exclusão de links e descoberta                                            |
| ingest/generic/hashing.py      | SHA-256 streaming e verificação de estabilidade                                          |
| ingest/generic/archives.py     | Inventário validado e extração ZIP                                                       |
| ingest/generic/service.py      | Coordenação transacional e proveniência                                                  |
| ingest/generic/verification.py | Comparação de originais com baseline                                                     |
| ingest/parsing/framework.py    | Contratos puros, JSON estrito e locators reversíveis                                     |
| ingest/parsing/service.py      | Fontes catalogadas, hashes, idempotência e atomicidade por fonte                         |
| ingest/instagram/parsers.py    | Somente profile activity, recently deleted e mensagens                                   |
| ingest/google/html.py          | Projeção determinística das tabelas HTML restritas                                       |
| ingest/google/parsers.py       | Somente SubscriberInfo e ChangeHistory                                                   |
| ingest/parsing/csv.py          | Projeção CSV textual com índices lógicos e limites                                       |
| ingest/apple/parsers.py        | Somente inventário, sign-on e atividade técnica de mídia                                 |
| cli/parse.py                   | Contagens de parsing sem payloads no console                                             |
| models/entities.py             | Foundation, ParserRun e ParsedRecord                                                     |
| storage/database.py            | SQLite, foreign keys, schema v5 e migrações explícitas v1 -> v2 -> v3 -> v4 -> v5        |
| normalization/                 | Contratos estáticos e transações de eventos DERIVED por normalizer                       |
| observations/                  | Dois observers estáticos de fatos atômicos DERIVED por ParsedRecord                      |
| correlation/                   | Grupos de igualdade exata com supports, sem identidade ou temporalidade                  |
| query/                         | Timeline, busca técnica, proveniência e janela com contexto do mesmo registro; read-only |
| reports/manifest.py            | Snapshot determinístico e escrita atômica                                                |
| media/                         | Assinaturas limitadas, verificação Foundation e grupos SHA-256 read-only                 |

Outros adaptadores, engine completo de correlação e busca textual ficam futuros.
Normalização canônica de eventos está implementada na 3A. Renderização em timezone
local, correlação temporal, resolução de identidade, busca textual e dossier permanecem futuros.

## Fluxo e transações

1. Validar raiz externa ao projeto/Git e originals existente; recusar links,
   junctions, hard links e áreas sobrepostas; criar somente áreas graváveis ausentes.
2. Abrir database/evidence.db; inicializar schema vazio com user_version=5
   ou exigir schema reconhecido. Ativar foreign_keys em toda conexão.
3. Persistir IngestionRun RUNNING com UUID, versão, início UTC e limites usados.
4. Adquirir BEGIN IMMEDIATE; descobrir arquivos ordenados e verificar a baseline.
   Escritores SQLite concorrentes são serializados, com timeout de 30 s.
5. Calcular SHA-256 em blocos, abrindo originais somente para leitura.
   Validar identidade por device/inode/tipo. Para estabilidade durante a leitura,
   comparar size/mtime em ambas as plataformas e também ctime no POSIX.
   Windows não usa ctime/birthtime como invariante de mutação.
6. Originais idênticos não geram registros repetidos; ausência/alteração aborta
   sem atualizar baseline.
7. Inserir EvidenceFiles novos, extrair ZIPs validados em staging exclusivo,
   criar ArchiveMembers e referências SourceRecord whole-file.
8. Conferir tamanho/hash de todos os membros materializados, inclusive anteriores;
   sincronizar arquivos extraídos e, no POSIX, os diretórios até a raiz do caso.
   Commit dos novos registros, contagens e status COMPLETED. Atualizar instante
   do catálogo somente quando arquivos forem adicionados.
9. Em falha normal, rollback dos novos registros e limpeza do staging próprio.
   Persistir FAILED e erro técnico em transação separada.

Nenhuma execução apaga ocorrências anteriores. Falha de limpeza também é registrada.
Falhas de infraestrutura que impeçam escrever no SQLite podem impedir atualização
final do run. Crash/kill pode deixar RUNNING e staging órfão: não existe transação
conjunta entre banco e filesystem, nem limpeza automática de runs anteriores.
Reingestão recusa extrações ausentes/alteradas, sem restaurá-las; verify se limita
a originais. Após erro de commit, consultar o status persistido antes da limpeza:
se o resultado é incerto ou já comprometido, preservar staging e exigir revisão.

## Caso e isolamento

/case/originals é somente leitura; working, database e output recebem derivados.
Compose monta originals e código read-only, usa usuário não-root e desativa rede
em execução. Não há paths Windows hardcoded. CASE_ROOT fornece default explícito,
sobrescrito por --case-root; somente Compose lê .env.

CasePaths verifica caminhos visíveis e check_path percorre ancestrais. O operador
assegura mounts sem aliases ocultos, originais estáveis e isolamento de processos
hostis. Checagens antes/depois não eliminam todas as corridas de filesystem.
Mount read-only/noatime é necessário quando atime do host deve ser preservado.

## ZIP

Somente primeiro nível, com ZIP aninhado opaco. Validação de todos os nomes, tipos,
duplicatas, conflitos e limites declarados precede a escrita. Durante a extração,
descomprimir o intervalo comprimido inteiro, contar bytes reais e validar CRC/tamanho,
sem o truncamento de ZipExtFile pelo tamanho declarado. Destinos usam nomes gerados:
working/ingest-<run>-<sufixo>/<evidence-id>/<índice>.bin.
Nome de membro e path extraído ficam separados no banco.
Dois-pontos são aceitos apenas na identidade lógica (ADR 0014), nunca como destino
físico ou ADS. A recusa de drives Windows, paths absolutos e UNC permanece.

Defaults por ZIP: 512 MiB/membro, 2 GiB total, 10000 entradas, razão 200.
STORE/DEFLATE apenas; sem symlinks, criptografia ou extractall. Decoding segue
UTF-8/CP437 do ZIP; erros e nomes não NFC são recusados, sem reparo silencioso.
Diretórios são validados mas não persistidos como arquivos. Colisões por casefold
incluem todos os prefixos implícitos. Leituras de metadados são limitadas a 32 MiB;
entradas reais da central directory são contadas antes da alocação de ZipInfo.
Não há quota global de memória, CPU ou disco.

## Schema e contratos

IDs externos são UUIDv4. Paths relativos distinguem ocorrências; hashes distinguem
conteúdo. EvidenceFile tem unicidade (case_id, relative_path); ArchiveMember,
(evidence_file_id, member_path). SourceRecord exige exatamente uma origem.
Entidades produzidas apontam para IngestionRun. FKs não usam cascade destrutivo.

Novos bancos recebem v5. Catálogos v1/v2/v3/v4 exigem dee evidence migrate para escrita:
v1 -> v2 adiciona parsing; v2 -> v3 adiciona NormalizationRun/NormalizedEvent.
Passos conhecidos e user_version são atualizados numa transação, sem sucesso parcial.
v3 -> v4 adiciona somente ObservationRun, DeviceObservation e NetworkObservation.
v4 -> v5 adiciona CorrelationRun, CorrelationCandidate e CorrelationSupport.
Verify/manifest podem ler v2/v3/v4 sem migração; v1 continua recusado antes de migrate.
Tabelas e registros da Foundation permanecem intactos. Versões desconhecidas e
bancos não versionados com tabelas são recusados. Não há Alembic nem migração silenciosa.
Antes de abrir um catálogo não vazio para escrita normal, validar schema em modo
read-only, para não recuperar journal de um banco v1 que deveria ser recusado.

## Parsing sem normalização

EvidenceFile ou ArchiveMember -> SourceRecord -> ParsedRecord. A descoberta consulta
somente os SourceRecords de inventário da Foundation. Fontes diretas são resolvidas
pela descoberta segura de originals; extrações usam paths relativos validados sob
working. A fonte é conferida contra tamanho/SHA-256 catalogados. Containers são
verificados por streaming uma vez por execução; cada membro candidato é verificado.

ParserContext fornece o path relativo/interno. Parser exige parser_id/version,
matches_path, supports e parse; ParserResult contém observações e diagnósticos.
Nome/path e estrutura são exigidos juntos. Sem loader de plugins ou novas dependências.
parse_catalog recebe decoder explícito: strict_json no fluxo Instagram ou table_document
no fluxo Google, ou csv_document no fluxo Apple. A projeção CSV mantém headers e
linhas lógicas em ordem, com células textuais e locators $/rows/N; somente os três
contratos Apple da ADR 0013 são selecionados. Payloads técnicos são subconjuntos
fiéis da linha original, sem persistir colunas comerciais na projeção de mídia.
A projeção HTML mantém headers e linhas das tabelas em ordem;
$/tables/T/rows/R resolve uma linha de dados, excluindo header. O decoder usa somente
html.parser, sem rede ou recuperação de tabelas malformadas. A ADR 0012 fixa o contrato.
O serviço verifica se cada locator resolve no documento decodificado e se o payload é subconjunto fiel
do objeto indicado. Locators repetidos abortam a fonte.

BEGIN IMMEDIATE serializa execução por fonte/parser. Um savepoint reúne todos os
SourceRecords de parsing e ParsedRecords; qualquer falha elimina esse conjunto,
mantendo um ParserRun FAILED com código técnico. Outras fontes podem continuar.
Sucesso e registros são comprometidos juntos. Interrupção antes do commit não deixa
sucesso parcial; falha global de persistência pode impedir registrar o erro.
Em exceção no commit final, fechar a sessão e consultar o resultado persistido:
ausência da tentativa permite registrar COMMIT_FAILED; tentativa já persistida é
preservada e exige revisão manual, sem reclassificar sucesso durável como FAILED.

Índice único parcial admite apenas um ParserRun COMPLETED por fonte de inventário,
parser_id e versão; ParsedRecord é único por run/locator. Tentativas falhas são
preservadas, versões novas coexistem e exports distintos nunca são fundidos.
Não há fingerprint adicional: identidade técnica mais hash de origem já delimitam
a observação. Fingerprint de conteúdo não deve virar deduplicação de eventos.

JSON tem teto de 32 MiB, profundidade 64 e 100000 registros; não há streaming de JSON
nem quota global de memória. Valores textuais não recebem reparo de mojibake. Raw
timestamp é preservado sem normalização. IP syntax/model code extraído do user agent
são anotações locais com origem; não alimentam correlação ou interpretação.

## Normalização canônica

ParsedRecord -> NormalizedEvent é uma derivação, sem leitura/extração de novos
valores dos originais. Três normalizers estáticos selecionam parser_id/versão/tipo;
um evento por registro elegível, ordinal zero. Conversas e inventário Apple são skips.
FK até ParsedRecord preserva a cadeia de evidência. Payload completo não é duplicado.
Campos raw usam escalares JSON; timestamp principal conserva exatamente o raw anterior.

Identidade é ParsedRecord + normalizer_id + versão + ordinal. BEGIN IMMEDIATE
serializa cada run; savepoint agrupa todos os novos eventos. Falhas preservam runs
anteriores e permitem FAILED técnico sem payloads. Commit incerto é inspecionado.
UTC exige base explícita; raw_only/missing continuam válidos. Sem entidades de
identidade, geolocalização, correlação ou deduplicação. Contratos na ADR 0015.
Google 1.1.0 adiciona somente o formato exato `YYYY-MM-DD HH:MM:SS Z`, com UTC
declarado na fonte (ADR 0016); Meta/Apple continuam 1.0.0. Eventos Google 1.0.0
permanecem intactos. A seleção de versões atuais é externa, sem nova view persistente.

## Observações de dispositivos/rede

Dois observers 1.0.0 derivam diretamente de ParsedRecords, evitando multiplicação
por versões de NormalizedEvent e incluindo inventário Apple. Cada fato referencia
o campo original pelo locator e conserva raw. IP canonical usa apenas ipaddress;
device facts não recebem valor canônico. Nenhuma entidade ou correlação é criada.
Transação por observer preserva atomicidade e runs FAILED; idempotência usa
registro/observer/versão/ordinal. Não há leitura de originals/working nem fusão
entre fontes. Contratos, ordem, sentinelas e limites estão na ADR 0017.

## Candidatos por igualdade exata

DeviceObservation/NetworkObservation -> CorrelationSupport -> CorrelationCandidate.
Um correlator 1.0.0 agrupa somente observações dos observers 1.0.0. Regra device
exige igualdade de fact_kind/namespace/raw persistido; regra network exige versão/IP
canônico, permitindo plataformas diferentes. Cada grupo >=2 guarda digest da chave
e N supports tipados, sem pairwise edges. Não há tempo, score ou identidade.

BEGIN IMMEDIATE e savepoint tornam cada run atômico. Reexecução valida todos os
supports/ordinals e detecta grupos desaparecidos; divergência falha sem reescrita.
Não há leitura de ParsedRecord, NormalizedEvent ou arquivos brutos nesta camada.
Constraints e seleção de versões estão documentadas na ADR 0018.

## Current timeline read-only

`current_event_policy` 1.0.0 seleciona explicitamente normalizers Meta/Apple 1.0.0
e Google 1.1.0. A seleção é reutilizável em SQL, sem MAX(version) ou persistência.
`query/timeline.py` consulta somente nove colunas técnicas de NormalizedEvent,
em conexão mode=ro/query_only e snapshot de leitura único; exige schema v5.
Não lê ParsedRecord, candidates, originals ou working, nem grava runs/cache/views.

UTC não NULL determina inclusão e ordem, com desempate platform/event_kind/event_id.
Filtros UTC Z usam [start,end); platform/event_kind são igualdade exata. Limit limita
items, sem reduzir matched_total. Undated conta os atuais sem UTC sob os filtros
platform/event_kind, sem aplicação de janela temporal. JSON não contém dados raw
ou relógio operacional. Contrato e limites na ADR 0019; schema continua v5.

## Busca técnica e proveniência

Search usa apenas device.observer/network.observer 1.0.0. Device compara namespace
e JSON string exatos; network canonicaliza apenas a entrada IP. Nenhum raw value
é retornado. Membership vem exclusivamente de CorrelationSupport persistido.
Provenance resolve cinco tipos por UUID, seguindo FKs até SourceRecord e original
direto ou ArchiveMember/container, com locators e hashes catalogados. Não abre
evidência nem conecta eventos a sibling observations. Histórico permanece acessível.

`query.catalog.read_catalog` reutiliza o opener read-only da 4A1, exige schema v5
e mantém um snapshot por consulta. Sem nova entidade, migration ou cache.
Projeções, limites, ordenação, NOT_FOUND e risco externo de shell history: ADR 0020.
Busca técnica não produz conclusão de identidade, sessão, localização ou autoria.

## Janela de eventos com contexto de origem

Incident-window usa read_catalog e timeline_in_snapshot para compor eventos atuais,
proveniência da 4A2 e observations 1.0.0 do mesmo ParsedRecord numa única transação
de leitura. Contextos nunca se propagam por tempo, valor ou candidate; memberships
são somente os supports persistidos. Sem novos vínculos entre eventos, entidades,
schema ou persistência. Bounds UTC Z obrigatórios; ordem idêntica à timeline.
Resumo essencial com total completo e prefixo limitado; contrato na ADR 0021.

## Matrix de candidates persistidos na janela

Reutiliza timeline_in_snapshot sem limite interno de eventos e same_record_context
da 4B1 para navegar pelos supports persistidos até candidates existentes. Um único
read_catalog mantém snapshot coerente; nenhuma nova relação ou persistência.
Contagens globais de supports ficam separadas de eventos/ocorrências da janela.
Platforms/event kinds são dos eventos filtrados; limite aplica-se só a candidates.
IDs permitem drill-down pela 4A2 sem duplicar proveniência. Contrato, ordenação,
semântica de múltiplos eventos por ParsedRecord e limites: ADR 0022.

## Inventário de mídia catalogada

Entrada exclusivamente EvidenceFile/ArchiveMember, sem depender de parsers ou eventos.
read_catalog mantém snapshot v5; original_reader e sha256_stream verificam conteúdo
e estabilidade de leitura de originals e materializações existentes. Prefixo limitado,
signature-first e extensão como hint; ISO-BMFF ambíguo permanece unsupported.
Agrupamento SHA-256 em memória conserva todas as ocorrências/proveniências. Não há
decode, perceptual hash, nova entidade, dependência ou escrita de resultado. ADR 0023.

`media contents` projeta os items verificados da 5A em conteúdos SHA-256 distintos,
com todas as occurrences e representative determinístico para uso computacional.
Singletons são conteúdos; contagens de formato/tipo são por conteúdo. Inconsistência
de formato/tipo/tamanho no mesmo SHA falha tecnicamente. Sem novo scanner ou leitura
adicional de bytes. A futura 5B poderá processar cada conteúdo uma vez. ADR 0024.

5B0 definiu o contrato histórico (ADR 0025). media/ agora implementa pHash read-only
sobre exact contents da 5A1: JPEG/PNG, revalidação do representative, decode completo,
pixels orientados e alpha branco, sem ICC. Uma execução por conteúdo e projeção
a todas as occurrences; sem schema/persistência, threshold ou matriz. ADR 0026.

Foundation separa identidade (dev, ino, tipo) de estabilidade: size/mtime em ambas
as plataformas, mais ctime no POSIX. Windows não usa ctime nem birthtime como
invariante de mutação. Comparações path/handle antes/depois, path safety e baseline
SHA-256/tamanho preservadas. Compatibilidade real Windows/Linux validada pela W1,
encerrando a limitação de plataforma da 5B. ADR 0027.

## Manifesto, verificação e logs

Manifesto exporta a baseline, não afirma integridade atual: execute verify.
Ordenação por relative_path/member_path e serialização estável.
generated_at=inventory_updated_at garante repetibilidade no mesmo catálogo/versão;
UUIDs e horários diferem entre aquisições independentes.
Escrita usa temporário em output, fsync e replace, nunca paths de originals.

Verify compara SQLite e hashes atuais: OK, MISSING, MODIFIED, UNTRACKED.
Exit 1 para divergência/ausência; 2 para erro operacional.
Verify e manifesto leem SQLite com mode=ro e query_only, sem inicialização/migração.
Banco ausente gera erro; hot journal não é recuperado. WAL é recusado antes da
conexão para evitar efeitos colaterais de shared memory. Leituras ainda podem
atualizar atime do host conforme o mount; não há promessa contrária.
Logs registram IDs, contagens e erros técnicos; não incluem payloads, SQL com
parâmetros, tracebacks ou paths absolutos nas mensagens da CLI.

## Dependências e validação

uv 0.8.22 sincroniza uv.lock; setuptools fixado continua backend.
Docker fixa base por digest. Windows/Linux usam o mesmo lockfile; Python 3.12 é
baseline validada. Downloads servem às ferramentas, não à execução do motor.
Pillow/ImageHash entram na 5B, com transitivas no lock; BeautifulSoup/lxml e
python-dateutil continuam adiados até uso concreto.

Testes sintéticos cobrem integridade, proveniência, idempotência, rollback, CLI,
manifesto, ZIPs adversariais, parsing, normalização, observações e candidatos exatos.
ADRs 0007–0027 documentam as decisões; os seis
princípios originais continuam válidos.
