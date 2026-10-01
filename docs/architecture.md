# Arquitetura

## Milestone 8B0 — contrato de dossiê e exportação

Concluída sob ADR 0036 Accepted, somente arquitetura/contrato. A camada
de dossiê/exportação organiza e apresenta artefatos aprovados acima do relatório
consolidado; não investiga nem o substitui. 8B1-A–G estão implementados e validados
sinteticamente em Windows nativo e Docker/Linux Python 3.12, sob ADR 0037 Accepted.

dossier.selection/1.0.0 seleciona explicitamente um report.consolidated/1.1.0 e
seu conjunto completo compatível de report.data_snapshot/1.1.0, com exatamente um
anchor e zero ou mais janelas. Sem máximo numérico semântico de janelas no dossiê;
limites operacionais do ADR 0037 são aplicados e cobertos por testes sintéticos.
Somente CANONICAL_TECHNICAL origina narrativa técnica humana. Suplementos,
validações e visuais ficam separados, sem novos findings, correlações ou mudanças
em F/W/G. Sem varredura implícita de output, CASE_ROOT, DB, originals/working,
parsing, rede/cloud/API/LLM ou inferência de identidade/autoria.

Duas camadas: HUMAN LEGAL-TECHNICAL DOSSIER, com 14 seções, e TECHNICAL SUPPORT
PACKAGE auditável. Paths lógicos relativos POSIX e portáveis, com rejeição de
escape, links, duplicatas e colisões; publicação fail-closed via staging, sem
sobrescrever destino ou publicar pacote parcial. dossier.package_manifest/1.0.0
registra path, papel, classe, tamanho e SHA-256 dos payloads, excluindo manifesto
e SHA256SUMS. SHA256SUMS cobre payloads e manifesto, excluindo a si próprio:
dependência acíclica, sem assinatura jurídica ou promessa de autenticidade.
Textos/JSON, índice e mapping de paths são determinísticos sob inputs/configuração
idênticos. O relatório canônico conserva suas 20 seções e contratos anteriores.

Originais excluídos; visuais somente JPEG/PNG contextuais explicitamente selecionados,
sem relações com eventos/findings. Attachments não resolvidos continuam
SOURCE_LIMITATION; WhatsApp fora do dataset técnico representado. PDF tem contrato
aceito no ADR 0038 e acoplamento privado restrito aceito no ADR 0039; fundação 8B2-A
concluída/qualificada, com revisão técnica humana aprovada. 8B2-B implementada e
qualificada sinteticamente: COMPLETE — HUMAN REVIEW APPROVED.
8B2-C implementada e qualificada sinteticamente: COMPLETE — HUMAN REVIEW APPROVED.
ZIP/archive exige escopo separado. 8B3 será validação
real futura, não realizada ou autorizada pela aceitação 8B0. Schema permanece v5;
8B1 não adiciona dependência ou persistência de análise.

## Milestone 8B1 — montagem determinística implementada

Concluída sob [ADR 0037 Accepted](adr/0037-deterministic-dossier-assembly.md).
O contrato permanece Accepted; a implementação A–G foi concluída e validada.
CLI: `dee dossier assemble --selection ... --output-dir ...`. Fluxo implementado:

```text
selection.json
  → validação estrita da seleção
  → preflight de todos os inputs/budgets e ausência do destino
  → staging exclusivo no mesmo parent/filesystem
  → captura estável dos artefatos explicitamente selecionados
  → validação dos formatos das cópias capturadas
  → validação dos snapshots/modelo canônico
      → renderer consolidado puro → comparação byte a byte com relatório selecionado
  → resolução dos destinos visuais e anexos
  → projeção humana por allowlist, após comparação bem-sucedida
  → dossiê/índice/metadata determinísticos
  → escrita exclusiva dos três arquivos gerados de apresentação/metadata
  → manifesto + SHA256SUMS
  → verificação de completude
  → sincronização de diretórios quando suportada e revalidação das identidades
  → publicação do staging sem substituir destino
```

O relatório fornecido é copiado sem alteração. Completude significa o conjunto
de suporte declarado/selecionado, com um anchor e zero ou mais janelas únicas
compatíveis, sem omissão silenciosa. Não atesta inexistência de janelas externas
ou geração de todas as janelas possíveis do caso; não há CASE_ROOT, DB ou
descoberta de inputs. Não executa investigação, análise nova ou novos findings.
Somente CANONICAL_TECHNICAL alimenta as 14 seções humanas aprovadas. O total global
exact_candidates.supports.total fica fora da projeção humana, sem repartição por
device/network; mantém-se nos artefatos técnicos.

JSON usa caps de bytes antes do decode, primitives estritas compatíveis ou
stdlib com hooks para duplicatas/não finitos/lexemas numéricos, seguida de
travessia limitada de profundidade/nós. Exaustão resulta RESOURCE_LIMIT, sem
exigir parser próprio ou dependência nova; não há garantia exata de memória.
Paths relativos portáveis, containment, rejeição de links/reparse e leitura
estável Foundation asseguram que os bytes conferidos sejam os copiados.
directory-v1 mantém metadata/manifesto/sums determinísticos e acíclicos;
completude é verificada antes do rename sem substituição. Sem PDF ou ZIP.

Módulos implementados: selection, validation, projection, rendering, packaging,
integrity e service, com adaptador cli/dossier. CLI → service → módulos explícitos;
projeção/renderização não importam serviço/packaging. Reuso apenas de reports
puros e utilitários nominais sem execução de caso, conforme ADR 0037; sem imports
de storage/ORM/serviços de ingestão/query/análise no pacote dossier. Testes de
imports do pacote e sentinelas de execução da CLI cobrem a fronteira.

Slices internos A–G: seleção/paths; compatibilidade canônica; projeção/rendering;
cópia/layout/metadata; integridade; publicação/CLI; regressões/paridade e fechamento.
Todos implementados. O pacote directory-v1 contém cópias exatas e cinco arquivos
gerados: human/dossier.md, human/annex-index.md, technical/selection-metadata.json,
integrity/manifest.json e integrity/SHA256SUMS.txt. Paridade de bytes Windows/Linux
validada para todos os 31 arquivos sintéticos, incluindo 21 snapshots. Publicação
real Linux renameat2(RENAME_NOREPLACE) e Windows os.rename validada; staging por
identidade, sem substituição/retry nem I/O após publicação confirmada. Isso não
promete snapshot atômico dos inputs ou durabilidade após perda de energia.
Gates completos e skips registrados no ADR 0037, seção 20.
Schema permanece v5. Validação real fica para 8B3,
PDF para 8B2 e ZIP/archive para escopo separado; sem acesso real nesta promoção.

## Milestone 8B2.0 — contrato de exportação PDF aceito

Concluída após revisão humana sob [ADR 0038 Accepted](adr/0038-human-pdf-export-contract.md).
8B1-A–G permanece concluída; a qualificação posterior 8B2-A está registrada abaixo.
A arquitetura
prevê saída separada pdf-presentation-v1, consumindo os dois Markdown aprovados,
sem mutar directory-v1 ou reconstruir narrativa/snapshots. ReportLab/pypdf/pypdfium2
e fontes empacotadas foram propostas para qualificação explícita em A;
nenhuma dependência foi instalada ou qualificada na promoção documental 8B2.0.
Render canônico definido em Linux/amd64 fixado,
não render nativo multiplataforma. Nenhum PDF gerado ou validado nesta promoção; sem alegação
PDF/A, PDF/UA, assinatura ou certificação. 8B3 permanece futura e exclusivamente
responsável pela execução real controlada; nenhum caso real acessado nesta promoção.
Na promoção 8B2.0, os últimos gates eram os de 8B1-G; os probes então disponíveis
demonstravam viabilidade. Os gates posteriores da fundação estão documentados abaixo.

## Milestone 8B2-A.1.1 — contrato de adaptador ReportLab aceito

A API pública ReportLab 5.0.1 falhou na ausência de metadata/trailer exigida pelo
ADR 0038. 8B2-A.1 investigou o bloqueio e demonstrou viabilidade sintética limitada.
8B2-A.1.1 concluída sob [ADR 0039 Accepted](adr/0039-controlled-reportlab-adapter-private-coupling.md):
revisão humana aceitou o risco de manutenção apenas do acoplamento privado exato
enumerado, restrito ao ReportLab 5.0.1. Artefatos/hashes foram qualificados na retomada de A.
Serialização central permanece no ReportLab; pypdf é validador somente leitura.
Sem pós-processamento, monkeypatch, fork/modificação do vendor ou uso arbitrário
de internals. Divergências de versão/shape falham fechadas; upgrades exigem revisão
e requalificação. Nenhuma decisão do ADR 0038 foi alterada.

A promoção 8B2-A.1.1 foi exclusivamente documental; a implementação e qualificação
posteriores de A estão registradas a seguir, sem ampliar a superfície privada.

## Milestone 8B2-A — fundação PDF qualificada

Concluída, com revisão técnica humana aprovada, sob ADRs 0038/0039 Accepted.
Adaptador controlado implementado/qualificado; toolchain canônica Linux/amd64,
seis fontes DejaVu, embedding/ToUnicode/subsets, PDFium para validação visual de
desenvolvimento, materiais de licença preservados e inventário canônico qualificados.
DTOs imutáveis/parser Markdown fechado, budgets e validador read-only pypdf;
somente probe PDF sintético de duas páginas, sem acesso a caso.
Gates, versões, hashes e limites em [pdf-toolchain-qualification.md](pdf-toolchain-qualification.md).
O fechamento de A não implementou renderer final, CLI ou publicação PDF;
o renderer de dossiê posterior está descrito abaixo. directory-v1 permanece intacto.
8B3 permanece futura e exclusivamente real.
Sem alegações PDF/A, PDF/UA, assinatura ou certificação.

## Milestone 8B2-B — renderer de dossiê PDF

COMPLETE — HUMAN REVIEW APPROVED, implementada e qualificada sinteticamente.
`dossier/pdf_renderer.py:render_dossier_pdf(data: bytes) -> bytes` consome somente
Markdown fornecido: parser fechado → medição/paginação → comparação de duas
passagens → ControlledCanvas → validação independente antes de retornar bytes.
Preserva as 14 seções, H3 e conteúdo original; TOC somente H2, bookmarks com raiz
H1 e filhos H2, destinos ordinais internos e índice de anexos como texto inerte.
Tabelas de largura fixa repetem headers e conservam linhas lógicas inteiras;
layout impossível falha UNSUPPORTED_LAYOUT. Fontes, mínimos e margens do ADR 0038
permanecem fixos. O validador confere cada fragmento com o DTO original, posições,
repetições e destinos, além das restrições da fundação. Nenhuma nova superfície
privada ReportLab, dependência, schema ou decisão de ADR.
Determinismo, PDFium e inventário: [qualificação](pdf-toolchain-qualification.md).
8B2-A permanece COMPLETE — HUMAN REVIEW APPROVED. CLI/serviço, descoberta,
manifesto/publicação PDF não implementados; 8B3 futura. Nenhum caso real acessado.

## Milestone 8B2-C — renderer de relatório consolidado PDF

COMPLETE — HUMAN REVIEW APPROVED. API
`dossier/pdf_renderer.py:render_consolidated_report_pdf(data: bytes) -> bytes`.
Fonte: bytes já fornecidos de `technical/canonical/consolidated-report.md`;
destino de apresentação: `human/consolidated-report.pdf`. A API retorna bytes,
sem ler pacote, snapshots, DB, CASE_ROOT ou originals/working e sem chamar o
produtor de relatório. Fixtures produzidas somente nos testes sintéticos.

O mesmo layout atende exatamente dois perfis fechados: dossier e consolidated-report.
O parser existente preserva o H1 e os 20 H2; header fixo `Relatório técnico consolidado`,
20 entradas/links internos no TOC e 21 destinos/outlines ordinais, sem H3 nos bookmarks.
O validador seleciona título, ordem, header e cardinalidades contratuais pelo kind,
independentemente do plano. Tabelas até oito colunas reutilizam largura fixa,
headers repetidos e linhas indivisíveis; layout impossível falha fechado.
Nenhuma nova regra de layout, dependência ou superfície privada ReportLab.
SHA e pixels aprovados de B permanecem inalterados. Inventário, fingerprints e
gates completos em [qualificação](pdf-toolchain-qualification.md).
8B2-C não conclui toda a 8B2 nem autoriza execução real; 8B3 permanece futura.

## Milestone 8A4.1 — integração source-media ao relatório

Concluída sob ADR 0035. Fluxo: source_media.provenance_link/1.0.0 → report
snapshot 1.1.0 → projeção explícita sem URI/path/payload → finding
source_media_provenance_link → consolidated report 1.1.0.
source_links_in_snapshot recebe a mesma Connection da janela; mantém verificações
Foundation separadas de filesystem, sem atomicidade DB/filesystem. Anchor não
executa a query. Limite de 1000 items preserva totais/status do universo completo.
O renderer permanece snapshot-only, sem import/acesso a banco ou evidências.
Novos findings positivos são apendados após os antigos; F/W-IDs e 20 seções
permanecem estáveis. Gap D descreve cobertura estreita; message attachments
continuam SOURCE_LIMITATION. WhatsApp condicional/não acionado; implementação
8B1 implementada sob ADRs 0036/0037 aceitos, com fechamento exclusivamente sintético.
Conjuntos 1.0.0 mantêm report 1.0.0 e Markdown histórico; mistura de versões e
versões desconhecidas falham explicitamente. Sem schema/persistência/dependências.

## Milestone 8A4 — exact source–media provenance link

Concluída sob ADR 0034, com fechamento de integridade controlado em Linux.

Fluxo: CurrentEvent → ParsedRecord → approved SourceMediaReference extractor →
exact ArchiveMember resolution → byte verification → existing ExactMediaContent
lookup → SourceMediaLink projection. Contrato detalhado no ADR 0034.

media/source_links.py lê somente campos aprovados do payload persistido Meta
1.1.0; não é parser genérico de URI. Resolve path literal no mesmo container,
verifica a entrada única do ZIP e SHA/tamanho no leitor estável da Foundation.
Reutiliza inventory_in_snapshot e project_contents, sem mudar políticas de
formato, schemas ou persistência. O wrapper público de inventory mantém sua API.
Uma read transaction abrange todos os componentes DB; filesystem não é atômico
com SQLite. Mesmo referências fora do prefixo são verificadas antes de limit.

Fonte é OBSERVED, resolução DERIVED. Não é media similarity, inferência de
message attachment nem evidence attribution. 8A1/8A2 continuam sem consumir essa
query nos contratos 1.0.0; integração 1.1.0 está na 8A4.1. 8A3 foi análise externa.

## Milestone 8A2 — first consolidated technical report

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
| correlation/                   | Candidates exatos persistidos, pares temporais e composição overlap read-only            |
| query/                         | Timeline, busca técnica, proveniência e janela com contexto do mesmo registro; read-only |
| reports/manifest.py            | Snapshot determinístico e escrita atômica                                                |
| reports/snapshot.py            | Projeção técnica read-only para relatório, sem persistência                              |
| reports/consolidated.py        | Validação de JSONs 8A1, modelo consolidado e templates Markdown determinísticos          |
| cli/report.py                  | Snapshot JSON ASCII/LF e consolidated Markdown UTF-8/LF; ambos stdout/read-only          |
| dossier/ e cli/dossier.py      | Seleção explícita, captura, projeção, integridade e montagem directory-v1 sem DB/caso    |
| media/                         | Assinaturas limitadas, verificação Foundation e grupos SHA-256 read-only                 |

Outros adaptadores, engine completo de correlação e busca textual ficam futuros.
Normalização canônica de eventos está implementada na 3A. Renderização em timezone
local, ampliação da correlação multissinal, resolução de identidade e busca textual permanecem futuros.

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
adicional de bytes. Essa projeção é a unidade de entrada reutilizada pela 5B para
processar cada conteúdo uma vez. ADR 0024.

5B0 definiu o contrato histórico (ADR 0025). media/ agora implementa pHash read-only
sobre exact contents da 5A1: JPEG/PNG, revalidação do representative, decode completo,
pixels orientados e alpha branco, sem ICC. Uma execução por conteúdo e projeção
a todas as occurrences; sem schema/persistência, threshold ou matriz. ADR 0026.

Foundation separa identidade (dev, ino, tipo) de estabilidade: size/mtime em ambas
as plataformas, mais ctime no POSIX. Windows não usa ctime nem birthtime como
invariante de mutação. Comparações path/handle antes/depois, path safety e baseline
SHA-256/tamanho preservadas. Compatibilidade real Windows/Linux validada pela W1,
encerrando a limitação de plataforma da 5B. ADR 0027.

## Candidates temporais read-only (6A)

`correlation/temporal.py` reutiliza `read_catalog` e `timeline_in_snapshot` sem
limite de eventos, num único snapshot SQLite read-only/query_only. A política
current explícita permanece 1.0.0 (Meta 1.0.0, Google 1.1.0, Apple 1.0.0).
Janela UTC `[start,end)` e filtros exatos de plataforma/tipo precedem os pares.
O raio inteiro obrigatório é limite de consulta. Somente current UTC event time
decide a inclusão: não consulta device, network, exact candidates ou pHash.

Uma varredura sobre a timeline ordenada conta todos os pares elegíveis, usando
microssegundos inteiros, e materializa apenas o prefixo limitado. A ordem é a
chave completa de A seguida da chave completa de B; empates seguem a timeline.
`TemporalPairCandidate` é DTO DERIVED transitório, separado do ORM persistido.
Não há pair_id, score, confidence, sessão, identidade ou autoria. Schema v5 e
as entidades persistidas permanecem intactos; sem novas tabelas, runs, cache,
índices, views ou escrita. Endpoints reutilizam os nove campos da timeline;
proveniência detalhada continua nos comandos de query existentes. ADR 0028.

## Contrato Temporal + Exact Signal Overlap (6B0)

A 6B0 definiu o contrato histórico da interseção read-only entre `TemporalPairCandidate`
da 6A e memberships de `CorrelationCandidate` exatos persistidos pela 3C1.
A 6B implementa essa composição em `correlation/overlap.py`. Somente observations do mesmo ParsedRecord de cada
endpoint contribuem, sob versões explícitas de observers, correlator e regras.
Device/network permanecem conjuntos separados; ausência de interseção é válida
e não demonstra diferença. Multiplicidade de supports não é peso; endpoints do
mesmo ParsedRecord são sinalizados sem presumir fontes independentes.

O contrato preserva prefixo, ordem e contagens temporais da 6A, sem filtro por
overlap, ranking ou score. Exige um único snapshot `read_catalog` para eventos,
observations e supports, com memberships carregadas em lote, sem N+1 SQL.
Schema v5, sem persistência adicional. pHash permanece excluído do contrato
6B: a 6B não consome o source-media provenance link introduzido posteriormente
na 8A4 nem define vínculo pHash-evento.
O wrapper 6A e a composição 6B reutilizam `temporal_candidates_in_snapshot` e
`_sweep_pairs`, com validação comum dos argumentos. A associação da 4B1 e a carga
6B usam `same_record_predicate`. Projeções explícitas carregam IDs e metadados,
sem raw values, em lotes determinísticos de até 400 referências; não há SQL por par.
IDs de observations têm escopo por tabela: o lookup usa somente a FK tipada
device_observation_id ou network_observation_id correspondente, sem cruzar braços.
Supports adicionais dos candidates alcançados servem somente à validação de
integridade. Referências, braços, casos, runs, versões, ordinais e support_count
são conferidos; inconsistência alcançada causa erro global, sem partial success.
O contrato permanece no ADR 0029; implementação e validação estão no ADR 0030.

## Report contract (8A0)

A 8A0 define o contrato do Relatório Técnico Consolidado de Análise e Organização
de Evidências Digitais, sem geração implementada e sem certificação pericial.
Futuros reports serão consumidores read-only das camadas existentes; não alteram
o evidence database nem recalculam fatos já disponíveis. Schema permanece v5.
Devem reutilizar queries, provenance e policies versionadas, mantendo distinguíveis
OBSERVED, DERIVED, REPORTED e HYPOTHESIS, sem promover hipótese a fato.

A 8A1 implementa o snapshot estruturado e determinístico de suporte;
a 8A2 implementa rendering/consolidação e seleção auditável dos achados.
DTO, schema JSON e comando 8A1 estão definidos no ADR 0032; formatos do relatório
humano em Markdown estão definidos no ADR 0033; outros exports permanecem futuros.
Achados terão bases técnicas/provenance e limitações, com contagens por unidade,
distinção current/historical e ausência limitada ao universo consultado.
Não haverá conclusão automática de identidade, autoria, sessão, causalidade
ou questão jurídica. O gap analysis obrigatório da 8A2 poderá orientar o escopo
de WhatsApp, sem pressupor sua necessidade. Contrato completo no ADR 0031.
Historicamente, a 8A0 não concluiu Milestone 8 nem o dossiê final. O contrato 8B0
está aceito e 8B1-A–G foi implementada. O contrato PDF 8B2.0 está aceito sob
ADR 0038, complementado pelo acoplamento privado aceito no ADR 0039. 8B2-A
está concluída/qualificada, com revisão técnica humana aprovada; 8B2-B implementada
e qualificada sinteticamente, COMPLETE — HUMAN REVIEW APPROVED; 8B2-C COMPLETE
— HUMAN REVIEW APPROVED, somente sintética; execução real 8B3 futura.

## Report data snapshot (8A1)

`dee report snapshot` compõe metadata/policies, inventory físico, coverage
histórica, resumo current pela policy explícita, candidates exatos elegíveis,
mídia verificada e zero ou uma analysis window. Trio temporal indivisível com
UTC Z, [start,end) e raio 1–86400; platform/event-kind só filtram a janela.

Todos os componentes DB e o índice de provenance compartilham um read_catalog
mode=ro/query_only/BEGIN. Primitives pequenas extraídas de incident, matrix e
overlap preservam as APIs públicas; a 6B recebe exatamente o prefixo calculado
pela 6A. Mídia conserva inventory/project_contents/perceptual_hashes e seus
checks de SHA/tamanho/estabilidade, com catálogos próprios declarados no envelope.
Não há snapshot atômico DB/filesystem.

IDs técnicos tipados, source locators e SHA catalogados permitem drill-down;
provenance de ParsedRecords é deduplicada no índice, sem paths/payloads pessoais.
Duplicatas conservam todas as ocorrências. Findings são projeções DERIVED sem
seleção interpretativa ou IDs inventados. Gap inputs contêm contagens, flags e
truncamentos, sem classificar A–F. Limites separados conservam unidades.
ParsedRecord permanece OBSERVED; NormalizedEvent permanece DERIVED.

JSON compacto ASCII com LF explícito, sem generated_at/clock/UUID. stdout somente,
sem runs, migrations, views, índices, caches ou arquivos automáticos. A 8A2 é
consumidora desses dados e do contrato 8A0.

## Consolidated technical report (8A2)

Fluxo: JSONs 8A1 → validação do conjunto → ConsolidatedReportModel → Markdown
pt-BR determinístico. `dee report consolidated --snapshot ...` aplica os limites
operacionais do ADR 0033 e exige um anchor sem janela. Eles não definem máximo
semântico de janelas no contrato 8B0. Não possui case-root. O módulo depende
apenas de stdlib/EvidenceError: nenhuma consulta ao evidence DB, originals,
working, mídia ou invocação de 8A1 durante rendering.

Igualdade de metadata/case-wide/gap inputs delimita a coerência do conjunto;
janelas únicas são ordenadas pela chave canônica. Findings incluem todos os
candidates retornados, com duplicatas case-wide apresentadas pelo anchor uma vez.
F/W/G são referências locais; apêndice usa ponteiros lógicos, sem UUIDs, hashes
ou nomes de arquivos de input. Contagens físicas/current e truncamentos permanecem
distintos. Distribuições de overlap descrevem somente o prefixo.

As 20 seções incluem gaps B/C/D sob regras explícitas; A/E/F não são automatizadas.
WhatsApp permanece condicional. Templates não usam LLM, prosa livre pessoal,
inferência nova ou integração externa. UTF-8/LF em stdout; sem persistência.
Report policy é separada da policy de snapshot e do evidence schema v5.
Os contratos históricos 1.0.0 permanecem suportados; a 8A4.1 amplia ambos para 1.1.0.
Custódia/autenticidade dos JSONs não é demonstrada pela validação estrutural.

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
ReportLab 5.0.1 integra o runtime como fundação do renderer PDF; pypdf 6.19.0
integra o runtime como validador estrutural somente leitura. pypdfium2 5.13.0 /
PDFium 153.0.7999.0 é exclusivo de desenvolvimento para validação visual,
sem rendering de produção por PDFium. O renderer de dossiê PDF da 8B2-B está
concluído e aprovado; o renderer de consolidated-report.pdf da 8B2-C está
concluído/qualificado sinteticamente e aprovado em revisão humana.

Testes sintéticos cobrem integridade, proveniência, idempotência, rollback, CLI,
manifesto, ZIPs adversariais, parsing, normalização, observações e candidatos exatos.
ADRs 0007–0039 documentam as decisões; os seis
princípios originais continuam válidos.
