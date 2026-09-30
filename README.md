# digital-evidence-engine

Motor técnico local para preservação, catalogação, normalização e
rastreabilidade de evidências digitais, preparado para futura indexação,
pesquisa, correlação multissinal e resolução controlada de identidade.

**Não é software pericial certificado.** Hashes verificam consistência de conteúdo;
não comprovam autoria, autenticidade anterior à aquisição ou admissibilidade.

**Real case evidence must never be committed to this repository.**

## Estado atual

A 8A3 concluiu a revisão analítica externa, sem código de produto. A 8A4 está
concluída e implementa [Exact Source–Media Provenance Link](docs/adr/0034-exact-source-media-provenance-link.md):
referências aprovadas já persistidas até membros exatos verificados.
A integração ao relatório humano 8A4.1 está concluída sob
[ADR 0035](docs/adr/0035-consolidated-report-media-link-integration.md).

A 8B0 está concluída: [ADR 0036 — Final Legal-Technical Dossier & Export Contract](docs/adr/0036-final-legal-technical-dossier-export-contract.md)
Accepted após revisão humana, somente arquitetura/contrato. A 8B1.0 também está
concluída: [ADR 0037 — Deterministic Dossier Assembly](docs/adr/0037-deterministic-dossier-assembly.md)
Accepted, contrato de implementação. Os slices 8B1-A–G estão implementados e
validados sinteticamente em Windows nativo e Docker/Linux Python 3.12.
A 8B2.0 está concluída: [ADR 0038 — Human PDF Export Contract](docs/adr/0038-human-pdf-export-contract.md)
Accepted após revisão humana. A qualificação da API pública ReportLab 5.0.1 falhou
na ausência de metadata/trailer. 8B2-A.1 demonstrou viabilidade sintética limitada
de adaptador privado controlado. 8B2-A.1.1 está concluída:
[ADR 0039 — Controlled ReportLab Adapter Private Coupling](docs/adr/0039-controlled-reportlab-adapter-private-coupling.md)
Accepted, com acoplamento restrito à superfície enumerada e versão 5.0.1.
8B2-A está concluída, com revisão técnica humana aprovada: fundação e adaptador controlado
implementados e qualificados sob ADRs 0038/0039. Toolchain canônica Linux/amd64,
seis fontes DejaVu, ToUnicode/subsets, PDFium para validação visual de desenvolvimento,
materiais de licença e inventário qualificados/preservados tecnicamente.
[Qualificação, hashes e gates finais](docs/pdf-toolchain-qualification.md).
8B2-B COMPLETE — HUMAN REVIEW APPROVED, implementada e qualificada sinteticamente:
`render_dossier_pdf(data: bytes) -> bytes` apresenta somente o Markdown de dossiê fornecido.
A arquitetura prevê saída separada pdf-presentation-v1, sem mutar directory-v1.
Render canônico em Linux/amd64 fixado, não render nativo multiplataforma.
Probes e PDFs de dossiê gerados/validados exclusivamente com dados sintéticos.
8B2-C NOT STARTED; PDF do relatório consolidado, CLI/serviço PDF e publicação PDF não implementados.
Sem alegação PDF/A, PDF/UA, assinatura ou certificação. A 8B3 permanece
futura e exclusivamente responsável pela execução real controlada; nenhum caso
real foi acessado na qualificação 8B2-A/B.

O contrato organiza material técnico para advogado/revisor humano, sem advocacy
ou inferência de identidade, autoria ou conclusão jurídica. Define duas camadas:
HUMAN LEGAL-TECHNICAL DOSSIER e TECHNICAL SUPPORT PACKAGE. A seleção explícita
dossier.selection/1.0.0 exige um report.consolidated/1.1.0 compatível e o conjunto
completo compatível de report.data_snapshot/1.1.0: exatamente um anchor e zero ou
mais janelas, sem máximo numérico semântico criado pelo dossiê ou omissão silenciosa.
Só CANONICAL_TECHNICAL alimenta narrativa técnica humana; materiais suplementares,
de validação e visuais são anexos separados. A montagem não consulta
CASE_ROOT/DB/originals, não investiga nem produz findings novos.

CLI disponível para montagem de artefatos explicitamente selecionados:

```console
dee dossier assemble --selection <selection.json> --output-dir <new-output-directory>
```

O renderer puro deve reproduzir byte a byte o relatório selecionado a partir dos
snapshots selecionados, preservando os bytes fornecidos. Completude refere-se
somente ao pacote selecionado, não ao caso real. directory-v1 tem 14 seções
pt-BR determinísticas, índice e metadata de seleção, manifesto e SHA256SUMS.
Staging e publicação sem substituição falham sem publicar pacote parcial;
budgets operacionais do ADR 0037 geram RESOURCE_LIMIT, sem descartar janelas.
Os cinco arquivos gerados são human/dossier.md, human/annex-index.md,
technical/selection-metadata.json, integrity/manifest.json e integrity/SHA256SUMS.txt.
Não houve validação real de dossiê: ela permanece exclusivamente na futura 8B3.

Fechamento sintético 8B1-G: Linux Python 3.12.14, pytest **1885 passed / 3 skipped**;
Windows nativo Python 3.12.11, **1864 passed / 24 skipped**, ambos exit 0.
Paridade do pacote completo de 31 arquivos (21 snapshots) PASS; publicação real
Linux renameat2(RENAME_NOREPLACE) e Windows os.rename PASS. Os dois gates de
junction Windows executaram e passaram. Skips Linux são os três gates exclusivos
Windows; skips Windows cobrem operações POSIX, symlinks sem permissão no host e
semântica de backslash. Ruff check/format e mypy PASS. Detalhes no
[ADR 0037, seção 20](docs/adr/0037-deterministic-dossier-assembly.md#20-fechamento-sintético-8b1-g).
Schema continua v5, sem alteração de dependências, lockfile ou policies.

Originais ficam excluídos do pacote v1. Visuais são JPEG/PNG contextuais selecionados
explicitamente, sem relações automáticas com eventos/findings. WhatsApp permanece
fora do dataset técnico atual; message attachments não resolvidos continuam
SOURCE_LIMITATION. Markdown, JSON, paths e artefatos de integridade são
determinísticos: manifesto cobre payloads; SHA256SUMS cobre payloads mais manifesto,
sem incluir a si próprio. O renderer de dossiê PDF 8B2-B usa ADRs 0038/0039 e a
fundação/toolchain qualificada em 8B2-A; relatório consolidado PDF permanece futuro. ZIP/archive e
sua reprodutibilidade exigem escopo separado. Aceitar 8B0 não autoriza implementar
ou executar essas etapas, nem validar um caso real.

A 8A0 concluiu o [contrato do relatório técnico consolidado](docs/adr/0031-consolidated-technical-report-contract.md).
A 8A1 concluiu o [Read-only Report Data Snapshot](docs/adr/0032-read-only-report-data-snapshot.md):
JSON técnico determinístico com contagens, coverage, policies, provenance,
candidates a achados e inputs de lacunas. A 8A2 implementou o
[First Consolidated Technical Report](docs/adr/0033-first-consolidated-technical-report.md):
templates Markdown pt-BR determinísticos nas 20 seções do contrato.

```console
dee report consolidated --snapshot /synthetic/anchor.json --snapshot /synthetic/window.json
```

O renderer 8A2 recebe JSONs 8A1 sob os limites operacionais do ADR 0033,
com exatamente um anchor sem janela; esses limites não são um máximo semântico
de janelas do dossiê 8B0. Não recebe case-root nem acessa DB/originals/working.
Confere igualdade das seções
case-wide, ordena janelas e inclui todos os finding candidates retornados, com
F/W/G locais e ponteiros de provenance. Lacunas automáticas somente B/C/D sob
regras explícitas; A/E/F e a necessidade de WhatsApp exigem contexto externo.
stdout UTF-8/LF somente; relatório e snapshots reais permanecem fora do Git.

Novos snapshots e consolidated usam policies 1.1.0. Conjuntos homogêneos 1.0.0
continuam aceitos com o comportamento histórico; misturar versões gera erro.
Na 1.1, janelas incluem source_media.provenance_link/1.0.0, com referência
OBSERVED e vínculo DERIVED. Somente exact-content e member-only geram findings,
apendados após todos os antigos, preservando F/W-IDs e as 20 seções.
Gap D descreve cobertura parcial ou ausência limitada aos snapshots fornecidos.
Message attachments permanecem SOURCE_LIMITATION; WhatsApp não é acionado.

```console
dee report snapshot --case-root /case
dee report snapshot --case-root /case --start 2026-01-01T00:00:00Z --end 2026-01-01T01:00:00Z --max-delta-seconds 300 --platform meta --event-kind content.activity
```

Exemplo sintético. O trio start/end/max-delta-seconds é opcional e indivisível;
platform/event-kind exigem a janela completa. Resumos case-wide usam um único
snapshot DB read-only; mídia mantém leituras verificadas e catálogos separados,
sem atomicidade global SQLite/filesystem. stdout somente, sem arquivo automático.
Limites independentes: 500 eventos incident, 100 candidates matrix e 1000 pares
temporais/overlap e 1000 source-media items, com totais e truncamento explícitos.
Source-media usa os mesmos bounds/filtros na mesma transação da janela, sem
usar o raio temporal. Anchor não executa source-media. Projeção omite URI,
reference_value, member_path e payload; IDs/hashes técnicos não são impressos
no Markdown. Occurrence count conta ocorrências catalogadas do mesmo conteúdo,
sem inferir envios, publicações ou disseminação. Schema v5 preservado.
O snapshot estruturado não gera relatório em prosa, conclusão jurídica ou decisão
de identidade/autoria. Dados e relatórios reais permanecem fora do Git.

Milestone 6B implementa [Temporal + Exact Signal Overlap](docs/adr/0030-temporal-exact-signal-overlap.md),
conforme o [contrato 6B0](docs/adr/0029-temporal-exact-signal-overlap-contract.md).
Enriquece o prefixo de pares temporais com memberships de candidates exatos
device/network persistidos, sem score ou identidade.

Milestone 6A entrega pares candidatos read-only de proximidade temporal entre
eventos current ([ADR 0028](docs/adr/0028-temporal-proximity-candidates.md)).
Preserva a 5B, com pHash read-only por conteúdo exato JPEG/PNG
([ADR 0026](docs/adr/0026-perceptual-image-hashing.md)), sobre a 5A1 e
o inventário read-only de mídia da Foundation,
timeline atual, busca técnica, proveniência, janela de eventos com contexto de
origem e matrix read-only de candidates persistidos na janela. Sem resolução
de identidade, correlação conclusiva, score, WhatsApp, timeline investigativa,
OCR, IA/ML, dashboard ou integrações externas.

## Pares candidatos temporais (6A)

```console
dee correlate temporal-candidates --case-root /case --start 2026-01-01T00:00:00Z --end 2026-01-01T01:00:00Z --max-delta-seconds 300
```

Exemplo exclusivamente sintético. A janela UTC é `[start,end)`; `--platform` e
`--event-kind` filtram os eventos current antes de formar pares. O raio inteiro
é obrigatório (1–86400 segundos), escolhido pelo operador como limite de consulta.
O delta é exato em microssegundos inteiros. A proximidade é candidate técnico
DERIVED; não prova relação entre eventos, pessoas ou dispositivos, sessão,
autoria ou causalidade.

`--limit` (default 1000, 1–10000) retorna um prefixo, preservando eligible_events
e matched_pairs completos. Pares seguem a chave completa da timeline para A e
depois B: UTC, plataforma, tipo, ID. Sem pair_id artificial, score, confidence,
persistência ou combinação com device/network/pHash. Os endpoints contêm somente
os nove campos técnicos da timeline; IDs permitem aprofundar a proveniência via
`dee query provenance` e `dee query incident-window`. JSON determinístico, com
paridade Windows/Linux. Janelas densas podem exigir tempo quadrático na contagem
de pares, mesmo com limite pequeno. Detalhes no [ADR 0028](docs/adr/0028-temporal-proximity-candidates.md).

## Temporal + Exact Signal Overlap (6B)

```console
dee correlate temporal-exact-overlap --case-root /case --start 2026-01-01T00:00:00Z --end 2026-01-01T01:00:00Z --max-delta-seconds 300 --limit 1000
```

Exemplo exclusivamente sintético. Argumentos, filtros e limites seguem a 6A.
Um único snapshot read-only preserva exatamente os pares, deltas, prefixo,
ordem e contagens temporais. A carga em lote obtém memberships de observations
do mesmo ParsedRecord de cada endpoint, sob versões elegíveis explícitas da 3C1.
Os arrays device/network mostram somente a interseção de candidate IDs persistidos,
sem multiplicidade, ordenados lexicalmente. Shared exact candidate é membership
técnica compartilhada; não estabelece mesmo dispositivo, pessoa, conta ou sessão.

Arrays vazios são normais e não provam diferença. `same_parsed_record` explicita
a igualdade dos IDs dos registros; nesse caso, o overlap pode derivar da mesma
observation, sem duas fontes independentes. Não há filtro por overlap, score,
ranking, pHash linking ou persistência. Relações inconsistentes alcançadas geram
erro técnico global (exit 2), sem saída parcial. Candidate IDs permitem drill-down
via `dee query provenance --kind candidate`. Detalhes no ADR 0030.

## Arquitetura e preservação

Originais nunca são criados, editados, renomeados, apagados nem recebem mudanças de
permissões pelo motor. Casos ficam fora do repositório. Links, junctions, hard links
e áreas sobrepostas são recusados. Mesmo conteúdo em paths diferentes preserva
ocorrências distintas. Hashes catalogados nunca são substituídos silenciosamente.

O pacote src/evidence_engine separa CLI, ingestão genérica, modelos, persistência
e manifestos. SourceRecord aponta para EvidenceFile ou ArchiveMember, ligado ao
ZIP original, ao SHA-256 e à execução que produziu o registro. OBSERVED, DERIVED,
REPORTED e HYPOTHESIS permanecem conceitos separados. ParsedRecord armazena os
valores extraídos como OBSERVED; NormalizedEvent existe separadamente como DERIVED.
Horários operacionais são UTC;
timestamps de filesystem não são tratados como criação de conteúdo.

O aplicativo não usa rede, telemetria, upload ou APIs externas. Consulte
[arquitetura](docs/architecture.md), [modelo](docs/evidence-model.md),
[ADRs](docs/adr/) e [regras de trabalho](AGENTS.md).

## Instalação reproduzível

Requer Python 3.12+; a baseline validada é Python 3.12. Dependências de execução:
Typer, SQLAlchemy 2.x, Pydantic 2.x, ReportLab 5.0.1 e pypdf 6.19.0.
pytest, Ruff e mypy são de desenvolvimento, assim como pypdfium2 5.13.0,
usado somente para validação visual PDF, não para rendering de produção.
uv.lock fixa versões transitivas e hashes, incluindo marcadores Windows/Linux.
uv 0.8.22 sincroniza o ambiente; setuptools e o layout src são mantidos.

PowerShell no Windows 11:

```powershell
py -3.12 -m pip install --user uv==0.8.22
py -3.12 -m uv sync --locked --extra dev --python 3.12
.\.venv\Scripts\dee.exe --help
.\.venv\Scripts\dee.exe version
```

Selecione .venv/Scripts/python.exe no VS Code. No Linux/macOS, com uv 0.8.22
instalado, use `uv sync --locked --extra dev --python 3.12` e ative
`source .venv/bin/activate`. Os comandos abaixo pressupõem o ambiente ativado.
Sem ativação no Windows, use `.\.venv\Scripts\dee.exe`.

Downloads acontecem somente na instalação/build. Para atualizar dependências
deliberadamente, altere pyproject.toml, execute `uv lock --python 3.12`, revise
uv.lock e repita as verificações. Não use --upgrade incidentalmente.
Pillow 12.3.0 e ImageHash 4.3.2 suportam a 5B; BeautifulSoup/lxml e python-dateutil seguem adiados.

## Caso e CLI

A raiz deve existir e conter originals/. Ingest cria as outras três áreas se
ausentes, nunca originals/. Todos os diretórios ficam fora do projeto.

```text
/case/
├── originals/   # somente leitura
├── working/     # extrações
├── database/    # evidence.db
└── output/      # manifest.json
```

```sh
dee --help
dee version
dee evidence --help
dee evidence ingest --case-root /case
dee evidence manifest --case-root /case
dee evidence verify --case-root /case
```

CASE_ROOT no ambiente fornece o default; --case-root tem precedência.
A CLI nativa não carrega .env automaticamente. Compose lê .env para os volumes e
define CASE_ROOT=/case dentro do container.

Ingest enumera originais em ordem estável, calcula hashes, verifica a baseline,
extrai ZIPs novos e persiste em transação. Cada execução tem UUID e status.
Repetir sem mudanças adiciona somente IngestionRun. Arquivo novo gera ocorrência;
original modificado ou ausente causa erro e rollback de todas as novas evidências
dessa execução. Use verify para obter os paths afetados.
Reingestão também confere tamanho e hash das extrações catalogadas: ausência ou
alteração provoca erro explícito, sem rematerialização automática.

Manifest grava atomicamente output/manifest.json e emite o mesmo JSON em stdout.
Inclui schema_version, engine_version, generated_at, case e files, com membros
dos ZIPs ordenados. Não inclui paths absolutos. **generated_at é o instante de
atualização do catálogo**, não o horário de cada exportação. Mesmo catálogo e
versão do motor geram bytes idênticos, inclusive após reingestão sem mudanças.
Aquisições independentes têm UUIDs/horários próprios e não geram manifestos iguais.

Verify recalcula hashes contra o SQLite, sem reparo ou alteração de baseline:

| Estado    | Significado                           |
| --------- | ------------------------------------- |
| OK        | Hash coincide                         |
| MISSING   | Original catalogado ausente           |
| MODIFIED  | Hash diverge                          |
| UNTRACKED | Arquivo presente ainda não catalogado |

Exit codes: 0 para sucesso (inclusive UNTRACKED isolado), 1 para MISSING/MODIFIED,
2 para erro técnico/configuração ou ingestão recusada. Verify usa o banco, não
importa manifestos externos e não verifica derivados em working.
Verify e a leitura do manifesto abrem SQLite em mode=ro e query_only. Banco ausente
não é criado; journal que exige recovery gera erro, sem recuperação automática.
Catálogos configurados externamente em WAL são recusados para evitar criação de
arquivos compartilhados. A baseline usa DELETE journal mode.

## Parsing Instagram/Meta

**PARSE ≠ NORMALIZE ≠ CORRELATE.** O parser consulta somente fontes já catalogadas,
confere SHA-256 e preserva valores de cada registro. Campos desconhecidos são
mantidos no payload daquele registro com warning; não há reparo de texto, inferência
de destinatário, nome comercial de aparelho ou associação de IP/device entre fontes.

```sh
dee parse --help
dee parse instagram --case-root /case
```

Catálogos novos usam schema v5. Catálogos v1/v2/v3/v4 exigem migração explícita antes
de escrita; verify/manifest podem ler v2/v3/v4 sem migrar. Faça backup consistente antes:

```sh
dee evidence migrate --case-root /case
```

A migração transacional percorre v1 -> v2 (parser_runs/parsed_records) e v2 -> v3
(normalization_runs/normalized_events), seguida de v3 -> v4 (observation_runs,
device_observations/network_observations) e v4 -> v5 (correlation_runs,
correlation_candidates/correlation_supports), conforme a versão inicial. Atualiza
user_version e conserva linhas anteriores. Não cria caso ausente,
não migra versões desconhecidas e não é acionada automaticamente pelo parsing.
O schema do manifesto de evidências permanece v1, independente do schema SQLite.

Contratos suportados (perfil/conteúdo excluído 1.1.0; mensagens 1.0.0):

| Artefato/path                                                  | Estrutura mínima                                                                            | Parser                        |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ----------------------------- |
| profile_activity.json, inclusive sob prefixo de export         | objeto com profile_account_insights: lista de registros, ou array de itens com label_values | meta.profile_activity         |
| recently_deleted_content.json, inclusive sob prefixo de export | objeto com recently_deleted_media: lista de registros, ou array de itens com label_values   | meta.recently_deleted_content |
| messages/inbox/\*\*/message\_<número>.json                     | objeto com messages: lista e title textual ou participants: lista                           | meta.instagram_messages       |

São contratos explícitos testados com fixtures sintéticos, não uma promessa de
compatibilidade com todas as variantes históricas da Meta. Nome correto com outra
estrutura gera UNSUPPORTED e warning auditável; não produz observações. Cada item
deve ser objeto com pelo menos um campo do artefato; item inválido aborta a fonte.
As tabelas de campos e validações ficam em ingest/instagram/parsers.py.

Nos arrays, cada payload preserva somente seu item, em locator como $/3.
Labels explícitos e containers limitados são reconhecidos em label_values.py;
annotations observed_field conservam valor, tipo JSON e locator até o campo.
Labels desconhecidos e containers não suportados ficam no payload com warning.
Não há reconhecimento pelo conteúdo, reparo de texto ou conversão de strings
como "true"/"false" para booleanos. Aliases de labels são literais explícitos.
timestamp_raw vem somente do timestamp do item; horários aninhados mantêm seus
papéis e locators nas annotations, sem substituir esse timestamp quando ausente.
Os contratos objeto anteriores continuam aceitos; registros 1.0.0 não são apagados
quando a execução 1.1.0 cria seu conjunto separado. Não há alteração de schema SQLite.

Cada observação aponta a SourceRecord e a um locator como
$/profile_account_insights/12 ou $/messages/17. A conversa é um registro separado
em $, contendo metadata sem repetir a lista de mensagens. Metadata de conversa
presente em arquivos diferentes continua sendo observação de cada fonte.

timestamp_raw guarda o valor JSON original, sem conversão UTC ou timezone inferido.
Vários timestamps candidatos ficam preservados no payload com warning, sem escolher
um deles. Timestamps internos de media ficam no respectivo objeto do payload.
IP recebe apenas classificação sintática; inválidos permanecem raw com warning.
Código de modelo explicitamente presente no user agent recebe anotação com o locator
de origem; não é convertido em nome comercial nem propagado para outro registro.

Repetir parsing intacto adiciona zero registros. A identidade técnica combina
fonte de inventário, parser_id, parser_version e locator. Exportações distintas
e versões distintas do parser permanecem conjuntos independentes.
Falha desfaz todos os ParsedRecords e SourceRecords
de parsing daquela fonte, registra ParserRun FAILED e permite continuar as demais.
Tentativas falhas/unsupported permanecem auditáveis; sucesso anterior é reutilizado
somente após nova conferência do conteúdo. Não há reparse sofisticado nem reparo.
Falha no commit final tem resultado conferido no catálogo: se houve rollback,
registrar COMMIT_FAILED quando o armazenamento permitir; se já houve persistência,
preservar o resultado e retornar erro operacional para revisão manual.

A saída JSON da CLI contém apenas contagens, incluindo records_parsed (novos) e
records_existing (já processados). Exit 0 inclui warnings/unsupported; exit 1 indica
falhas em fontes, com resultados válidos de outras fontes preservados; exit 2 indica
erro operacional global/configuração/schema. Consulte warnings_json/error_code em
parser_runs para diagnósticos, sem payloads no console.

Limites fixos: 32 MiB por fonte JSON, profundidade 64 e 100000 registros por fonte,
incluindo a conversa. O JSON é carregado em memória dentro desse limite. UTF-8 e BOM
UTF-8 são aceitos; chaves duplicadas, números não finitos e JSON inválido são recusados.
Paths de seleção também precisam ser relativos e canônicos, sem segmentos . ou ..,
backslashes ou prefixos de drive. Catálogos existentes passam por pré-verificação
read-only antes de abertura gravável normal, impedindo recovery de v1 antes da recusa.

## Parsing Google Takeout

`dee parse google --case-root /case` usa somente fontes já catalogadas e as mesmas
transações, verificações de hash e regras de idempotência do parsing Instagram.
Os parsers `google.subscriber_info` e `google.change_history` começam em 1.0.0.

Seleção exige path canônico, filename SubscriberInfo.html/ChangeHistory.html
ou sufixo .SubscriberInfo.html/.ChangeHistory.html com prefixo de conta opaco,
mais headers compatíveis. A posição da tabela ou das colunas não seleciona o parser.

SubscriberInfo requer Timestamp, IP Address, Activity Type, Interactive,
Initiating Service, Geo, Raw User Agents e Challenges (timestamp, outcome, dusi).
ChangeHistory requer Timestamp, IP Address e Change Type; Old Value e New Value
são opcionais. Cada linha é observação separada, inclusive linhas idênticas.
Payloads usam os headers originais como chaves e textos das células como valores;
vazios continuam strings vazias, colunas ausentes não são inventadas.

O decoder restrito usa html.parser da biblioteca padrão, sem novas dependências.
UTF-8/BOM, entidades HTML e br (como newline) são decodificados; não há reparo de
mojibake ou conversão de datas. timestamp_raw é o texto de Timestamp. IP só recebe
validação sintática e model code só é anotado literalmente em Raw User Agents.
Geo é texto informado pela fonte, não consulta externa. Não há nomes comerciais.

Locators como $/tables/0/rows/17 resolvem na projeção determinística table_document
dos bytes HTML originais; índices começam em zero e rows exclui o header.
Tabelas aninhadas, spans, headers duplicados e tabelas incompletas são recusados,
sem observações parciais. Isso pode recusar variantes HTML válidas fora do contrato.
Limites adicionais: 1000 tabelas, 101000 linhas incluindo headers, 256 colunas,
64 níveis de markup na célula; continuam os tetos de 32 MiB e 100000 observações.
HTML fora das duas tabelas/artefatos fica fora do escopo. Consulte a
[ADR 0012](docs/adr/0012-google-html-table-observations.md).

## Parsing Apple

`dee parse apple --case-root /case` reutiliza o catálogo, a conferência de hashes,
as transações por fonte e a idempotência existentes. Seu contrato de parsing não mudou.
Somente três parsers, todos 1.0.0:

| Parser                      | CSV                             | timestamp_raw                   |
| --------------------------- | ------------------------------- | ------------------------------- |
| apple.device_inventory      | Apple ID Device Information.csv | Device Last Heartbeat Timestamp |
| apple.sign_on_activity      | Apple ID SignOn Information.csv | Logged In Date                  |
| apple.media_device_activity | Purchase Server Events.csv      | Event Time                      |

Os dois primeiros exigem o diretório literal `Informações da Conta Apple e do dispositivo/`.
O terceiro exige `Apple_Media_Services/Stores Activity/Other Activity/`, com variante
explícita contendo `Apple Media Services/` imediatamente após `Apple_Media_Services/`.
Filename isolado ou diretório diferente não seleciona parser. Headers obrigatórios
estão definidos em `ingest/apple/parsers.py`; colunas opcionais ausentes não são criadas.

`csv_document` usa csv da biblioteca padrão, UTF-8 com BOM opcional e vírgula.
Preserva whitespace, células vazias, identificadores com zeros e `Not Available`.
Quoted fields, aspas escapadas e newline dentro de célula são suportados. Headers
duplicados/vazios, largura incompatível, NUL e erros do leitor estrito abortam a fonte.
Limites: 32 MiB, 100000 linhas lógicas, 256 colunas e limite de campo do csv
(128 KiB no runtime validado). Locators `$/rows/N` excluem o header; `N` começa em zero
e conta registros CSV, não linhas físicas. Headers em locators de campo escapam ~ e /.

Payload do inventário projeta os 18 campos técnicos documentados; sign-on preserva
os sete campos do contrato; mídia projeta somente 12 campos técnicos, excluindo
campos comerciais. Os bytes originais e a cadeia de proveniência permitem recuperar
as outras colunas. IP só recebe validação sintática; inválido fica raw com warning.
O papel do timestamp principal é explícito em annotation; os demais horários ficam
raw no payload, sem timezone inferido ou conversão UTC.

Não há associação entre identificadores, preenchimento de modelo, interpretação
de Signon Status, localização por StoreFront ou tradução de código para nome comercial.
Passkeys e os demais artefatos Apple permanecem fora do parsing. Um inventário de
snapshot não demonstra ausência histórica de aparelhos. Consulte a
[ADR 0013](docs/adr/0013-apple-csv-observations.md).

## Normalização de eventos

```sh
dee normalize --help
dee evidence migrate --case-root /case
dee normalize events --case-root /case
```

Normalizers `meta.event_normalizer`, `google.event_normalizer` e
`apple.event_normalizer` operam somente sobre ParsedRecords catalogados.
Versões produtoras: Meta/Apple 1.0.0 e Google 1.1.0. Google 1.0.0 permanece como
derivação histórica; versões coexistem sem reescrita dos eventos anteriores.
Não releem evidências nem alteram parsers. Produzem sete event kinds: account.profile_activity,
content.activity, communication.message, account.security_activity, account.change,
account.sign_on e media.activity. Conversas e inventário Apple são skips intencionais.

ParsedRecord é OBSERVED; NormalizedEvent é DERIVED e aponta por FK à observação.
Campos \*\_raw são escalares JSON preservando tipo, inclusive timestamp_raw copiado
do ParsedRecord. Não duplicam o payload. IP/identifier/model/action/status vêm somente
do próprio registro e annotations existentes; não há nova extração de user agents.
Valores conflitantes ficam NULL com diagnóstico técnico, sem escolher silenciosamente.

Epoch inteiro Meta usa unidade do campo (timestamp/creation_timestamp em segundos,
timestamp_ms em milissegundos), quando é o único papel do timestamp principal.
Datas com Z, offset explícito ou sufixo UTC podem gerar occurred_at_utc. Datas sem
zona, formatos desconhecidos e valores inválidos ficam raw_only; ausência do timestamp
principal fica missing. Não substituir pelo horário aninhado nem inferir zona por
IP/StoreFront/máquina. UTC usa microssegundos fixos e Z; raw nunca é substituído.

Cada normalizer tem um run auditável e transação independente. Falha desfaz seus
novos eventos, registra FAILED quando possível e permite continuar os demais.
Repetir sem mudanças cria zero eventos; fontes diferentes permanecem ocorrências
distintas. CLI imprime apenas contagens. Exit 0 permite raw_only/warnings, 1 indica
falha por normalizer e 2 erro operacional/schema. Consulte diagnostics_json/error_code.
Google 1.1.0 também aceita exatamente `YYYY-MM-DD HH:MM:SS Z`, validando calendário
e horário. O literal Z sustenta explicit_utc; essa regra não amplia Meta/Apple nem
o contrato temporal genérico. A contagem física pode incluir versões históricas;
validar o conjunto atual exige selecionar versões explicitamente.
Detalhes na [ADR 0015](docs/adr/0015-canonical-event-normalization.md) e na
[ADR 0016](docs/adr/0016-google-source-declared-utc.md).

## Política de ZIP

Somente o primeiro nível é extraído. ZIP aninhado é membro opaco. Reconhecimento
usa a estrutura ZIP, não só a extensão; .zip inválido provoca erro explícito.

Limites por ZIP, configuráveis no comando ingest:

| Opção             | Default                     |
| ----------------- | --------------------------- |
| --max-file-bytes  | 536870912 (512 MiB)         |
| --max-total-bytes | 2147483648 (2 GiB)          |
| --max-members     | 10000, incluindo diretórios |
| --max-ratio       | 200                         |

Exemplo: `dee evidence ingest --case-root /case --max-members 500 --max-ratio 100`.

O inventário inteiro é validado antes da escrita. Recusamos traversal, paths
absolutos/Windows, backslashes, links e arquivos especiais, duplicatas e colisões
de maiúsculas, nomes não portáveis (exceto `:` lógico), Unicode inválido/não NFC, criptografia e métodos
diferentes de STORE/DEFLATE. Nomes não são corrigidos silenciosamente. Limites de
bytes também valem durante leitura; CRC e tamanho são conferidos. Sem extractall.
A descompressão mede todo o intervalo comprimido, independentemente do tamanho
declarado, para impedir truncamento com CRC falsificado. Colisões incluem diretórios
implícitos. Metadados ZIP têm limite fixo de 32 MiB por leitura; a contagem real da
central directory é limitada antes da criação dos objetos de membros.

Extrações usam diretório exclusivo por execução e nomes numerados .bin.
member_path/filename originais ficam no banco: nenhum nome do ZIP vira destino.
`:` é permitido somente no nome lógico; paths absolutos, UNC e designadores de
drive Windows continuam recusados. Não se materializam ADS. A exceção restrita
está documentada na [ADR 0014](docs/adr/0014-logical-zip-colon.md).
Diretórios vazios são validados mas não recebem ArchiveMember. Falhas normais
removem somente staging próprio e fazem rollback; originais permanecem intactos.

## Docker Desktop

Use containers Linux. A imagem base está fixada por digest e instala o lockfile.

```powershell
docker build -t digital-evidence-engine:dev .
docker run --rm --network none digital-evidence-engine:dev dee --help
Copy-Item .env.example .env
# Configure quatro diretórios externos existentes em .env.
docker compose config --quiet
docker compose build
docker compose run --rm dee dee evidence ingest
docker compose run --rm dee dee evidence manifest
docker compose run --rm dee dee evidence verify
```

Container não-root, sem rede; código e originals são montados somente para leitura.
Compose não cria paths ausentes silenciosamente. Use paths absolutos com / no
Windows. No Linux ajuste DEE_UID/DEE_GID e permissões das áreas graváveis, sem
alterar originais. Áreas não podem sobrepor originais nem seus ancestrais, inclusive
na topologia de mounts do host. Mudanças de dependências/metadata exigem rebuild.

## Observações canônicas de dispositivos/rede (3B)

```sh
dee observe --help
dee observe device-network --case-root /case
```

`device.observer` e `network.observer` 1.0.0 leem somente ParsedRecords catalogados.
Cada DeviceObservation representa um identificador ou modelo explícito, conservando
namespace e raw. Cada NetworkObservation representa um campo IP explícito: válido
recebe canonical/versão; inválido conserva raw e aviso técnico. Não há associação
de IP a mensagens ou preenchimento por outro registro.

Os fatos são DERIVED e apontam ao campo original, sem constituir entidades de
dispositivo/rede, correlação, localização ou autoria. Derivar de ParsedRecord
evita multiplicar fatos por versões de eventos e inclui o inventário Apple.
Raw fields são escalares JSON em TEXT; não há conversão de IDs/modelos comerciais.
Reexecução cria zero observações quando nada mudou; ocorrências entre registros
nunca são fundidas. Cada observer tem transação e run próprios. A CLI imprime
somente contagens; exit 1 indica observer com falha e 2 erro operacional/schema.
Detalhes na [ADR 0017](docs/adr/0017-device-network-observations.md).

## Candidatos por igualdade exata (3C1)

```sh
dee correlate --help
dee correlate exact --case-root /case
```

`exact_match.correlator` 1.0.0 aceita somente observers 1.0.0. As duas regras 1.0.0
agrupam device por fact_kind/namespace/value_raw exato e rede por versão/IP canônico
persistido. Grupos exigem pelo menos duas observações e mantêm um support por
ocorrência, sem relações pairwise. Device não cruza namespaces; IP pode cruzar
plataformas, sem afirmar identidade, localização, autoria ou sessão compartilhada.

Candidates guardam digest SHA-256 da chave versionada; supports referenciam os valores
nas observações. Reexecução intacta cria zero candidates/supports. Divergência no
conjunto de supports falha o run, sem alterar resultados anteriores. Adicionar
observações a um grupo antigo exige versionamento explícito em escopo posterior.
CLI imprime somente contagens; exit 1 indica run com falha, 2 erro operacional.
Sem tempo, score ou engine completo de correlação. Veja a
[ADR 0018](docs/adr/0018-exact-correlation-candidates.md).

## Consulta da timeline atual (4A1)

```sh
dee query --help
dee query timeline --case-root /case --limit 1000
dee query timeline --case-root /case --platform google --event-kind account.change
dee query timeline --case-root /case --start 2026-01-02T03:04:05Z --end 2026-01-03T00:00:00Z
```

Política `current_event_policy` 1.0.0: Meta/Apple normalizers 1.0.0 e Google 1.1.0.
Versões históricas permanecem intactas; versões futuras não entram automaticamente.
Consulta exige schema v5 e abre SQLite somente para leitura, sem criar runs, views,
índices ou migrar. Não requer backup nem altera o catálogo.

Ordem: UTC, platform, event_kind, event_id, todos crescentes. Bounds exigem UTC
explícito com Z e usam [start,end). platform/event_kind aceitam um valor exato cada.
Limit: 1–10000, default 1000. JSON informa matched_total, returned, truncated e
undated_current_events; esta última contagem respeita platform/event_kind,
independentemente da janela temporal, sem inventar UTC.

Items contêm IDs do evento/ParsedRecord, UTC, platform, event_kind,
normalizer_id/version, time_status e time_basis. Nenhum payload, IP ou device é
retornado. Sem export, busca textual, rendering local ou correlação temporal.
Detalhes na [ADR 0019](docs/adr/0019-current-event-timeline-policy.md).

## Busca técnica e proveniência (4A2)

```sh
dee query device --case-root /case --namespace meta.synthetic.identifier --value SYNTHETIC-DEVICE-X
dee query network --case-root /case --ip 203.0.113.10 --limit 100
dee query provenance --case-root /case --kind candidate --id <uuid> --limit 500
```

Device exige namespace e string literal, serializada como JSON sem coerção, trim
ou alteração de case. `--value 123` busca a string, não o número. Filtros opcionais:
`--platform` e `--fact-kind identifier|model`. Network usa somente `ipaddress.ip_address`
para canonicalizar a entrada e comparar IP/versão persistidos, sem reler ip_raw;
filtros opcionais `--platform` e `--source-role`. Observers elegíveis: device.observer
1.0.0 e network.observer 1.0.0, sem aceitação automática de versões futuras.

Buscas retornam contagens e metadados, sem ecoar device values ou IPs. Ordem:
platform, parsed_record_id, observation_ordinal, observation_id. Limit 1–10000,
default 100; matched_total independe do limite. candidate_ids são memberships já
persistidos, ordenados, sem criar agrupamentos ou inferir identidade.

Provenance aceita exatamente event, parsed-record, device-observation,
network-observation e candidate. Segue somente FKs até original/container e SHA-256
catalogado, sem ler evidência bruta. Eventos históricos são acessíveis por ID;
current_policy_match informa a política 4A1. Candidate preserva support_ordinal,
com limit 1–1000 (default 100), returned_supports e supports_truncated; sem cursor.
Objeto ausente: JSON NOT_FOUND, exit 2. Entrada inválida/falha técnica: exit 2.

Schema v5, mode=ro/query_only e snapshot de leitura, sem migration, backup ou runs.
JSON determinístico não inclui payloads nem raw values. Paths, locators, IDs e hashes
da proveniência continuam dados de caso: não os adicione ao Git. Argumentos CLI
podem ficar no histórico do shell do operador, fora do controle do engine.
Busca não implica correlação, identidade, ownership ou autoria. A 4A2 não produz
correlação temporal; candidates temporais read-only são fornecidos separadamente
pela 6A. Busca textual permanece futura. [ADR 0020](docs/adr/0020-technical-search-provenance.md).

## Janela de eventos com contexto (4B1)

```sh
dee query incident-window --case-root /case --start 2026-01-02T00:00:00Z --end 2026-01-03T00:00:00Z
```

Start/end obrigatórios em UTC Z, intervalo [start,end). Filtros opcionais:
`--platform`, `--event-kind`; limit default 500, máximo 5000. Mesma política current
e ordenação da timeline. Cada item contém os nove campos do evento, proveniência
da 4A2 e device_context/network_context somente do **mesmo ParsedRecord**, produzidos
pelos observers 1.0.0. Contextos ordenam por observation_ordinal/observation_id;
candidate_ids vêm apenas de CorrelationSupport persistido, em ordem ASC.

Sem observation própria, o contexto fica vazio. Não se copiam fatos de registros
próximos ou de mesmo candidate/valor. Origem comum não prova dispositivo, pessoa,
sessão ou autoria. Um único snapshot read-only, schema v5, sem reler evidência nem
persistir resultados. Sem raw device values, IPs ou payloads.

matched_total conta todos os eventos datados da janela; returned/truncated descrevem
o prefixo. undated_current_events mantém a semântica 4A1; não há agregados adicionais
de contexto. JSON determinístico; resultados reais permanecem fora do Git.
Detalhes na [ADR 0021](docs/adr/0021-incident-window-view.md).

## Matrix de candidates na janela (4B2)

```sh
dee query incident-candidates --case-root /case --start 2026-01-02T00:00:00Z --end 2026-01-03T00:00:00Z --candidate-kind device
```

Seleciona eventos atuais com os mesmos bounds UTC Z [start,end) e filtros opcionais
platform/event-kind da timeline. candidate-kind aceita device/network; omitido inclui
ambos. Só aparecem candidates já persistidos, via observations 1.0.0 do **mesmo
ParsedRecord** e respectivos CorrelationSupports. Nenhuma correlação nova é criada.

candidate_support_count é global; window_event_count conta eventos distintos na
janela; window_support_occurrences conta links evento/support, sem colapsar múltiplas
observations. window_platforms/event_kinds vêm apenas dos eventos filtrados.
Ordenação: event count DESC, support occurrences DESC, candidate kind/ID ASC.
Eventos preservam a ordem da timeline; links usam support_ordinal/observation_id ASC.
Contagens não representam força probatória, identidade, sessão ou autoria.

Limit 1–1000, default 100, limita candidates; matched_candidates permanece completo.
returned_candidates/truncated descrevem o prefixo. Todos os eventos internos são
retornados, sem cursor. Janelas grandes podem produzir saída extensa. JSON compacto
omite raw values/IPs/payloads/provenance completa; use os IDs com os comandos
provenance/incident-window existentes para drill-down. Snapshot único read-only,
schema v5, sem persistência adicional. [ADR 0022](docs/adr/0022-incident-candidate-matrix.md).

## Inventário de mídia e duplicatas exatas (5A)

```sh
dee media --help
dee media inventory --case-root /case
```

Inspeciona somente EvidenceFiles e ArchiveMembers catalogados: originals em leitura
e membros já materializados em working. Sem reextração ou reparo. Prefixo limitado
a 4096 bytes reconhece JPEG, PNG, GIF, WEBP e HEIF/HEIC/AVIF por brands explícitas;
extensão é apenas hint. MP4/MOV genéricos e outros ISO-BMFF não classificados ficam
fora dos media items, sem inferir presença de vídeo. Assinatura não é decode.

Todas as ocorrências passam pela verificação streaming de size/SHA-256 catalogados
com estabilidade antes/depois. Ausência ou divergência encerra com exit 2, sem
atualizar baseline ou retornar JSON parcial. Hashes iguais agrupam mídias verificadas
em duplicate_groups, preservando todos os IDs/paths de ocorrência, sem pares N².
Bytes iguais não provam mesmo evento, fonte, upload ou autoria.

JSON determinístico informa scanned_occurrences, recognized_media, verified_media,
unrecognized_occurrences, format_counts, kind_counts, contagens de duplicatas, items
e duplicate_groups. Sem imagem, thumbnail, base64 ou path absoluto. Não escreve
resultados; outputs reais permanecem fora do Git. Schema v5, nenhuma dependência
nova, perceptual hash ou entidade persistida. Leituras podem atualizar atime conforme
filesystem/mount. Contrato e limitações: [ADR 0023](docs/adr/0023-media-inventory-exact-duplicates.md).

## Conjunto de conteúdos exatos (5A1)

`dee media contents --case-root /case` reutiliza o inventário verificado da 5A
e retorna um content por SHA-256 distinto, incluindo singletons. Preserva todas
as occurrences; contagens por formato/tipo são por conteúdo, não por ocorrência.
Representative é a primeira occurrence na ordenação documentada, apenas para
futuro processamento computacional; não é evidência canônica ou preferência de
origem/autoria. Inconsistências de formato/tipo/tamanho por SHA causam erro técnico.
JSON determinístico, schema v5 e nenhuma escrita ou dependência nova. Sem decode
ou perceptual hashing. [ADR 0024](docs/adr/0024-exact-media-content-set.md).

## pHash técnico por conteúdo (5B)

`dee media perceptual-hash --case-root /case` reutiliza a 5A1 e processa somente
o representative de cada conteúdo JPEG/PNG, revalidando size/SHA-256 e estabilidade.
Decode completo, EXIF transpose, alpha sobre branco, RGB e nenhum transform ICC.
image.phash/1.0.0 usa hash_size=8, highfreq_factor=4 e retorna 64 bits/16 hex.
pHash é uma feature DERIVED: **pHash não é prova de igualdade** ou autoria.
Sem threshold, classificação, dHash, matriz de distâncias ou persistência.

Exit 0 indica sucesso; exit 1 emite JSON completo com FAILED/UNSUPPORTED por
conteúdo; exit 2 aborta por erro global/operacional/integridade, sem JSON parcial.
APNG/multiframe são recusados e os guards de decompression bomb são preservados.
Todas as occurrences permanecem associadas ao resultado; não há fallback de fonte.
Compatibilidade Foundation Windows resolvida pela
[ADR 0027](docs/adr/0027-platform-file-identity-and-read-stability.md): identidade e
estabilidade seguem políticas explícitas por plataforma. Validação integrada real
Windows/Linux equivalente, incluindo JSON byte-identical; limitação anterior da
5B encerrada em suplementos externos, preservando o relatório histórico.
Outputs reais permanecem fora do Git.

## Exact Source–Media Provenance Link (8A4)

```console
dee media source-links --case-root /case --start 2024-01-01T00:00:00Z --end 2024-01-01T01:00:00Z --platform meta --event-kind content.activity --limit 500
```

Exemplo sintético. Bounds UTC obrigatórios [start,end); filtros exatos;
current_event_policy vigente. O adapter v1 aceita somente
meta.recently_deleted_content/1.1.0/recently_deleted_content, nos campos uri
da lista media sob labels Mídia explicitamente contratados do payload persistido.
Não pesquisa URIs arbitrárias nem relê JSON original para descobri-las.

Igualdade literal de referência e member_path no mesmo EvidenceFile; bytes e
SHA/tamanho do ZIP/membro verificados read-only. Retorna LINK_EXACT_MEDIA_CONTENT,
LINK_ARCHIVE_MEMBER_ONLY, NO_CATALOG_MEMBER_MATCH, NO_SOURCE_MEDIA_REFERENCE ou
UNSUPPORTED_SOURCE_REFERENCE_TYPE. MEMBER_ONLY não significa arquivo inválido;
apenas falta de conteúdo correspondente sob a policy atual. Formatos não mudam.
Falha de integridade é global, exit 2, sem JSON parcial nem ajuste do catálogo.

limit 1–5000 (default 500) retorna prefixo por UTC/platform/kind/event ID/locator/
referência; summary preserva totais de eventos, referências, itens e status.
Referências múltiplas geram vários itens por evento; ausência gera um item.
Todos os matches são verificados antes do corte. DB usa um read snapshot;
filesystem tem verificações próprias, sem atomicidade conjunta. Inventário
existente também verifica outras ocorrências e suas materializações em working.

Referência é OBSERVED e link é DERIVED. Nenhuma afirmação de publicação, envio,
autoria, identidade, sessão ou causalidade. Sem fuzzy, pHash ou ligação de
communication.message por tempo/thread. stdout somente; dados reais fora do Git.
A integração humana é versionada pela 8A4.1; contratos 1.0.0 permanecem históricos.

## Testes e qualidade

```sh
python -m pytest
ruff check .
ruff format --check .
mypy src
```

Ou no container:

```sh
docker compose run --rm dee python -m pytest -p no:cacheprovider
docker compose run --rm dee ruff check --no-cache .
docker compose run --rm dee ruff format --check --no-cache .
docker compose run --rm dee mypy --cache-dir=/tmp/dee-mypy src
```

Fixtures são gerados em diretórios temporários com nomes synthetic-\* e conteúdo
artificial. A suíte cobre imutabilidade, hashes, proveniência, rollback, CLI e
ZIPs adversariais. Nenhum export real é necessário.

Crie um caso sintético fora do repositório com Python 3.12:

```python
from pathlib import Path
import tempfile
import zipfile

root = Path(tempfile.mkdtemp(prefix="synthetic-dee-"))
(root / "originals").mkdir()
(root / "originals/synthetic-document.txt").write_bytes(b"synthetic document")
with zipfile.ZipFile(root / "originals/synthetic-export.zip", "w") as archive:
    archive.writestr("synthetic-folder/synthetic-member.txt", b"synthetic member")
print(root)
```

Use o caminho impresso nos três comandos CLI. Repetir ingest retorna files_added=0.
Alterar **apenas esse arquivo sintético** depois da ingestão produz MODIFIED;
removê-lo produz MISSING; criar outro produz UNTRACKED.

## Limitações

- Sem ZIP recursivo, criptografado ou compressão além de STORE/DEFLATE.
- Limites são por ZIP, sem quota de disco global ou timeout. O teto de 32 MiB dos
  metadados e o limite de entradas não constituem quota total de memória/CPU.
- MIME é application/zip quando identificado; demais formatos ficam ausentes.
- Checagens de links/metadados não substituem isolamento contra processos hostis
  alterando simultaneamente arquivos, paths ou mounts. Originais devem estar estáveis.
- Leituras podem atualizar atime conforme o filesystem. Use mount read-only/noatime
  para preservar metadados do host; o motor não chama operações de alteração desses
  metadados nos originais.
- Filesystem e SQLite não compartilham transação: crash pode deixar run RUNNING e
  staging órfão. Arquivos são sincronizados antes do commit; diretórios também são
  sincronizados no runtime POSIX. Isso não garante atomicidade em falha de energia
  nem durabilidade de diretórios no Windows nativo. Commit de resultado incerto
  preserva staging e exige inspeção manual; não há limpeza de runs anteriores.
- Verify cobre originais; reingestão detecta extrações removidas/alteradas e falha,
  sem restaurá-las. A conferência adiciona uma leitura dos derivados por ingestão.
- case_root no banco é a localização inicial operacional. Paths relativos permitem
  mover as quatro áreas do caso; manifestos não exportam esse path absoluto.
- Alterações não são aceitas como novas versões automaticamente; use aquisição
  separada até existir uma política explícita de revisão.

.gitignore e .dockerignore complementam a revisão de diff/status; não detectam
conteúdo sensível automaticamente nem protegem inclusões forçadas.
As decisões da revisão adversarial estão na [ADR 0010](docs/adr/0010-adversarial-integrity-boundaries.md).

## Roadmap

| Milestone | Escopo                                                               |
| --------- | -------------------------------------------------------------------- |
| 0         | Bootstrap e arquitetura — concluído                                  |
| 1         | Evidence Foundation — concluída                                      |
| 2A        | Framework + três artefatos Instagram/Meta — concluída                |
| 2B        | Suporte Meta array/label_values — concluída                          |
| 2C        | SubscriberInfo e ChangeHistory Google Takeout — concluída            |
| 2D        | Três CSVs Apple e validação controlada — concluída                   |
| 2 futura  | Ampliação de formatos somente mediante escopo aprovado               |
| 3A        | Normalização canônica de eventos — concluída                         |
| 3B        | Observações atômicas Device/Network — concluída                      |
| 3C1       | Grupos candidatos por igualdade exata — concluída                    |
| 4A1       | Read-only current timeline query — concluída                         |
| 4A2       | Technical Search & Provenance Drill-down — concluída                 |
| 4B1       | Incident Window View — concluída                                     |
| 4B2       | Incident Candidate Matrix — concluída                                |
| 4 futura  | Search e ampliação da timeline                                       |
| 5A        | Media inventory + exact duplicate baseline — concluída               |
| 5A1       | Exact media content set — concluída                                  |
| 5B0       | Perceptual hash contract — concluída                                 |
| 5B        | Perceptual image hashing — concluída; Windows/Linux validados        |
| W1        | Windows Foundation identity/read-stability compatibility — concluída |
| 6A        | Temporal Proximity Candidates — concluída                            |
| 6B0       | Temporal + Exact Signal Overlap — contrato concluído                 |
| 6B        | Temporal + Exact Signal Overlap — concluída                          |
| 7         | WhatsApp — condicional, não acionada                                |
| 8A0       | Consolidated Technical Report Contract — concluída                   |
| 8A1       | Read-only Report Data Snapshot — concluída                           |
| 8A2       | First Consolidated Technical Report — concluído                      |
| 8A3       | Directed Investigative Review — concluída; análise externa, sem produto |
| 8A4       | Exact Source–Media Provenance Link — concluída                       |
| 8A4.1     | Consolidated Report Media-Link Integration — concluída               |
| 8B0       | Final Legal-Technical Dossier & Export Contract — concluída; ADR 0036 Accepted |
| 8B1.0     | Deterministic Dossier Assembly implementation contract — concluída; ADR 0037 Accepted |
| 8B1       | Deterministic Dossier Assembly — A–G implementados; fechamento sintético Windows/Linux concluído |
| 8B2.0     | Human PDF Export Contract — concluída; ADR 0038 Accepted             |
| 8B2-A     | PDF Toolchain Qualification & Foundation — concluída, revisão técnica humana aprovada; gates sintéticos em docs/pdf-toolchain-qualification.md |
| 8B2-A.1   | Controlled Adapter Feasibility — viabilidade sintética limitada demonstrada |
| 8B2-A.1.1 | Controlled ReportLab Adapter Contract — concluída; ADR 0039 Accepted |
| 8B2-B     | Human Dossier PDF — COMPLETE — HUMAN REVIEW APPROVED |
| 8B2-C     | Consolidated Technical Report PDF — não iniciada |
| 8B3       | Final Package Integrity & Real-Case Validation — futura              |
