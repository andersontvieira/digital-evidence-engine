# ADR 0036 — Final Legal-Technical Dossier & Export Contract

Status: Accepted.

Milestone: 8B0 concluída, exclusivamente contrato/documentação, após aprovação
humana. A aceitação autorizou somente a arquitetura e o contrato. Posteriormente,
8B1-A–G foram implementados sob ADR 0037 e validados sinteticamente em Windows/Linux.
PDF/ZIP e validação real não integram esse fechamento; 8B2/8B3 permanecem futuras.
README, architecture e AGENTS registram o estado atual de implementação.

## 1. Contexto e finalidade

Base de design: AGENTS.md, README.md, docs/architecture.md e ADRs
[0031](0031-consolidated-technical-report-contract.md),
[0032](0032-read-only-report-data-snapshot.md),
[0033](0033-first-consolidated-technical-report.md),
[0034](0034-exact-source-media-provenance-link.md) e
[0035](0035-consolidated-report-media-link-integration.md).
Schema de evidências permanece v5; report.data_snapshot/1.1.0,
report.consolidated/1.1.0 e source_media.provenance_link/1.0.0 estão aceitos.
8A4.1 e o contrato 8B0 estão concluídos; 8B1 foi implementada e validada
sinteticamente sob ADR 0037. 8B2/8B3 permanecem futuras com escopo próprio.

O dossiê organiza resultados técnicos já aprovados para leitura por advogado ou
outro revisor humano autorizado e revisão por profissional técnico. Não realiza
nova investigação nem responde quem praticou uma ação. O relatório consolidado
continua sendo o relatório técnico detalhado canônico; o dossiê o referencia,
sem substituí-lo, reescrevê-lo ou ampliar suas conclusões.

Não determina identidade humana, autoria humana, titularidade de conta,
propriedade de dispositivo físico, atribuição de sessão, causalidade, intenção,
culpa, responsabilidade, tipificação jurídica ou admissibilidade probatória.
Não se apresenta como laudo pericial certificado ou software pericial certificado.
O profissional jurídico poderá combinar o material com documentos externos,
declarações, testemunhos e argumentação fora do motor. O núcleo técnico é o mesmo
para revisão civil ou criminal: não há modos separados por área jurídica.
Jurisdição, petições, estratégia, ônus da prova e defesa de uma tese ficam externos.

## 2. Fronteira epistemológica e compatibilidade

| Classe existente | Tratamento no dossiê v1 |
| --- | --- |
| OBSERVED | Apresentar somente quando já estiver assim classificado em artefato técnico aprovado, conservando origem e limites. |
| DERIVED | Apresentar somente resultados já produzidos pelas policies aprovadas, com versão, suporte e limitações. |
| REPORTED | Não converter em finding técnico. Declarações externas exigiriam papel suplementar e contrato futuro explícitos; v1 não admite depoimentos como fonte de afirmações técnicas. |
| HYPOTHESIS | Nunca promover a fato. v1 não gera hipóteses nem conclusões a partir delas. |

As classes de fonte da seção 3 e os papéis de arquivo são categorias de entrega,
não substituem essas quatro classes epistemológicas. A inclusão de um documento,
legenda ou referência de seleção não constitui suporte técnico novo.
Revisões suplementares são preservadas como documentos externos; suas afirmações
não são extraídas para formar novos findings ou contornar o limite REPORTED.

Não há nova correlação, ranking probatório, score, confidence, fusão de pessoas
ou atribuição de pessoa a conta, dispositivo, IP, mensagem, publicação, mídia ou
evento por coexistência. Não promover NormalizedEvent a OBSERVED. Preservar
unidades, total/returned/truncated, prefixos, escopo, coverage e distinção entre
linhas físicas e current events. Ausências continuam limitadas ao conjunto
selecionado, janela, policy e versão; nunca significam ausência no mundo real.

F/W/G conservam exatamente o significado e a numeração do relatório escolhido,
conforme ADRs 0033/0035. Não renumerar, fundir ou criar finding por exportação.
Labels de materiais/anexos são referências de apresentação, nunca novos IDs
persistidos de evidência. A seleção de materiais não altera a ordem interna de
arrays técnicos nem deduplica ocorrências ou suas fontes.

Os contratos históricos 1.0.0 continuam válidos nos consumidores já existentes.
O perfil inicial de dossiê aqui aceito admite somente o conjunto canônico
1.1.0 definido abaixo; não converte conjuntos legados silenciosamente. Isso não
remove suporte 1.0.0 da 8A2. O antigo limite global de media-event dos ADRs
0031–0033 não deve ser reaplicado aos novos inputs 1.1.0: prevalece a ampliação
explícita e estreita do ADR 0035, sem autorizar pHash-event linking.

## 3. Duas camadas e classes de entrada

A camada **HUMAN LEGAL-TECHNICAL DOSSIER** contém Markdown legível sem JSON bruto,
índice de anexos, resumo de integridade e referências locais aos materiais.
Exposições visuais explicitamente selecionadas são anexos contextuais separados.
PDFs do dossiê e do relatório consolidado ficam reservados à 8B2.

A camada **TECHNICAL SUPPORT PACKAGE** conserva os artefatos técnicos selecionados
com seus bytes e contratos, permitindo auditoria da apresentação humana.
Não equivale à entrega das evidências originais. As duas camadas integram um
único diretório de entrega; compartilhar só parte dele é uma decisão externa,
que não deve ser apresentada como pacote integralmente verificado.

| Classe de entrada | Papéis admitidos ou exclusão em v1 |
| --- | --- |
| CANONICAL_TECHNICAL | Um relatório report.consolidated/1.1.0 e seu conjunto completo de report.data_snapshot/1.1.0. Source-media entra somente pela representação já aceita nesses contratos. |
| SUPPLEMENTAL_TECHNICAL | Revisão técnica dirigida de operador e suporte estruturado explicitamente fornecidos. São anexos, não fontes de novos findings canônicos. |
| VISUAL_EXHIBIT | Imagem JPEG/PNG explicitamente selecionada pelo operador apenas para visualização contextual, com legenda aprovada e rótulo local. Não gera relação com finding/evento. |
| VALIDATION_ARTIFACT | Relatório técnico selecionado sobre execução, geração ou integridade de artefatos. Não atesta automaticamente outra execução ou todo o pacote. |
| ORIGINAL_EVIDENCE | Excluída da montagem v1, inclusive quando explicitamente listada. Não copiar automaticamente containers, exports ou arquivos originais. |
| LEGACY_MANUAL_WORK_PRODUCT | Planilhas e relatórios exploratórios/manuais históricos excluídos por padrão e não canônicos. Inclusão suplementar exige contrato futuro explícito; não basta trocar seu rótulo de classe. |

Relatórios de validação são alocados em VALIDATION_ARTIFACT, não duplicados como
SUPPLEMENTAL_TECHNICAL. Um item tem exatamente uma classe e um papel compatível.
Papel conflitante ou classe não aprovada falha; renomear arquivo não muda sua
natureza. O operador responde pela classificação explícita do material; a
validação estrutural não consegue provar que bytes arbitrários são uma fonte
legítima ou detectar todo original disfarçado de documento suplementar.

O conjunto canônico obrigatório contém exatamente um report.consolidated/1.1.0
compatível e seu conjunto completo e compatível de report.data_snapshot/1.1.0:
exatamente um anchor e zero ou mais snapshots com analysis_window, conforme os
contratos de report/snapshot aceitos e o conjunto canônico selecionado. Aplicam-se
integralmente as validações de conjunto, policies, versão, coerência case-wide
e janelas dos ADRs 0033/0035. A montagem não omite silenciosamente nenhuma janela
do conjunto canônico selecionado. Este ADR não estabelece máximo numérico de
snapshots ou janelas no nível semântico do dossiê.

Limites operacionais de recursos foram posteriormente especificados e testados
independentemente pela 8B1 sob ADR 0037. Esses limites de implementação
não redefinem a validade semântica de um conjunto canônico que seja compatível.

O relatório deve corresponder byte a byte à renderização aprovada desses JSONs.
A montagem implementada na 8B1 confere essa correspondência com o renderer puro 8A2;
isso valida apresentação de dados já existentes, sem executar 8A1, queries ou
gerar findings adicionais. Divergência falha, sem substituir o relatório recebido.
Nenhum conjunto alternativo de findings é criado pelo dossiê.

Fronteira normativa da narrativa humana em dossier v1 / 8B1: somente
CANONICAL_TECHNICAL pode originar afirmações técnicas em dossier.md, descrições
de eventos/findings, linhas de cronologia, contagens, tabelas técnicas, afirmações
sobre o que os dados estabelecem ou não estabelecem e declarações de provenance
técnica além da simples indexação de um anexo.

SUPPLEMENTAL_TECHNICAL, VALIDATION_ARTIFACT, VISUAL_EXHIBIT e
LEGACY_MANUAL_WORK_PRODUCT nunca podem ser parseados, resumidos, interpretados
ou explorados para produzir narrativa técnica humana, seja por LLM ou por
extração determinística de texto livre. Quando sua classe permitir inclusão,
somente podem ser copiados como artefatos separados, listados em annex-index.md
e referenciados como material explicitamente separado de suporte, validação ou
contexto. Isso não autoriza LEGACY_MANUAL_WORK_PRODUCT em v1.

A inclusão desses materiais não altera F/W/G, findings, cronologia, contagens
técnicas, statements canônicos, relações source-media ou classificação
epistemológica. Um VALIDATION_ARTIFACT pode ser identificado como documento de
validação, mas sua prosa não pode ser reinterpretada em conclusão técnica nova.
Uma revisão dirigida de operador não adquire o papel do relatório consolidado
canônico pela seleção, cópia, indexação ou referência no dossiê.

## 4. Seleção explícita: dossier.selection/1.0.0

Contrato de documento estruturado local, posteriormente implementado pela 8B1
sob ADR 0037 como dossier.selection/1.0.0.
Não depende de schema do banco. O identificador de policy e a versão são
obrigatórios; não há UUID aleatório, identificador baseado em relógio nem
datetime.now(). Não é necessário um identificador pessoal ou global da seleção.

| Elemento conceitual | Regra v1 |
| --- | --- |
| policy_id / policy_version | dossier.selection / 1.0.0, igualdade exata; outras versões falham. |
| canonical_inputs | Relatório e conjunto completo de snapshots obrigatórios, com papel e referência local explícitos. |
| supplemental_inputs | Lista opcional de revisão técnica ou suporte estruturado; ausente equivale a lista vazia. |
| validation_artifacts | Lista opcional de documentos de validação selecionados; não é execução automática de verify. |
| visual_exhibits | Lista opcional com as condições da seção 7; não há inclusão presumida. |
| issued_date | Opcional, data de calendário válida no formato YYYY-MM-DD, fornecida pelo operador; ausente fica ausente, sem usar data do host, input ou filesystem. |
| case_reference | Token opaco opcional de correlação entre pacote e exibição, aprovado pelo operador; não é case_id nem requisito de geração. |
| delivery_profile | Obrigatório; v1 define somente directory-v1, contendo as duas camadas e sem PDF gerado ou ZIP. |

Cada item identifica input_reference, local_label, source_class e role.
expected_sha256 é opcional e justificado para conferir uma baseline explicitamente
fornecida; quando presente deve ter formato SHA-256 e coincidir com os bytes.
Não baixar ou procurar o arquivo quando a referência falhar. Cada input é um
arquivo regular explicitamente selecionado, não um diretório a explorar.

input_reference é um caminho relativo POSIX a partir do diretório da seleção,
com a política de segurança da seção 8. Essa base contém somente os artefatos
previamente preparados para entrega; não é CASE_ROOT. Não aceitar URI, rede,
cloud, drive, UNC ou referência absoluta. Nunca enumerar recursivamente fontes,
incluir todos os arquivos de output, selecionar por similaridade de nome ou
adivinhar papel pela extensão. Não seguir referências internas de um artefato
para carregar outros arquivos. Recursos remotos de Markdown/documentos não são
buscados nem ativados pela montagem.

local_label é explícito, único no conjunto e estável: token ASCII minúsculo
iniciado por letra, seguido de letras, dígitos ou hífen, com até 48 caracteres.
Não pode codificar valor pessoal, UUID, hash opaco ou nome real de input.
case_reference, se usado, segue a mesma forma e revisão de exposição; não serve
para resolver identidade ou consultar um caso. Não gerar labels de nome, hash,
ordem do filesystem, relógio ou conteúdo pessoal. Não reparar labels inválidos.
Itens com mesmo label, referência duplicada ou papéis conflitantes são erros;
arquivos distintos de conteúdo igual conservam suas entradas e provenance.

case_reference não é nome de pessoa, identificador de parte processual ou
CPF/documento; não precisa conter número de processo e não estabelece identidade.
É somente um token opcional de correlação documental, não um campo de atribuição
humana. person_name, client_name, party_name, CPF, process_number, court e campos
de jurisdiction não integram a seleção v1; permanecem externos, salvo escopo
futuro separado. A ausência de case_reference não impede gerar o dossiê.

Listas de seleção são conjuntos ordenados canonicamente por role e local_label;
a ordem da seleção não muda bytes finais. Essa regra não reordena os arrays
internos dos artefatos técnicos. A metadata derivada da seleção registra apenas
policy/version, perfil, opcionais presentes, labels, papéis/classes, paths do
pacote e opções explícitas de exibição. Exclui input_reference e paths do host.
A seleção operacional original não é copiada automaticamente para o pacote.

## 5. Estrutura humana congelada

Título: Dossiê Técnico de Organização de Evidências Digitais. São exatamente
14 seções de primeiro nível lógico, sempre presentes e nesta ordem:

1. Identificação do documento
2. Finalidade
3. Escopo e limitações
4. Fontes e materiais técnicos
5. Metodologia técnica
6. Cronologia técnica relevante
7. Atividades digitais relevantes
8. Relações técnicas entre fontes e mídias
9. Comunicações e anexos
10. Contexto técnico de dispositivos
11. Contexto técnico de rede
12. Atividades e alterações de conta
13. O que os dados estabelecem e o que não estabelecem
14. Mapa de provenance e índice de anexos

A seção 1, Identificação do documento, permanece completa e determinística
quando case_reference está ausente: usa o título e a identificação de contrato
já definidos, sem exigir nem inventar referência pessoal, processual ou do caso.

Ausência de conteúdo adequado em uma seção produz declaração delimitada de
ausência nos artefatos selecionados, nunca preenchimento por inferência.
“Relevante” significa pertencente aos materiais selecionados pelo operador,
sem ranking automático de interesse ou força. O dossiê usa templates fixos e
projeções aprovadas; não resume texto pessoal livre por LLM nem cria narrativa
investigativa. Seções temáticas não atribuem semântica de ação além da já
estabelecida pelo artefato canônico e sua policy.

Toda afirmação técnica apresentada conserva a classificação, unidade, escopo,
limitações e referência de suporte. O mapa aponta para o label do relatório,
F/W/G existente quando aplicável e ponteiro lógico já aprovado do snapshot.
Afirmações de cobertura sem finding apontam para a seção/componente existente,
sem inventar F-ID. Ordenação temporal somente de valores UTC já sustentados;
raw/timezone e ambiguidades permanecem disponíveis via provenance, sem nova
conversão. Não intercalar fontes para criar sessões ou relações cronológicas.

A seção 14 referencia annex-index.md, que relaciona todos os materiais entregues
por label, papel, classe, path relativo do pacote e finalidade limitada. O
relatório consolidado integral permanece acessível nesse índice. O resumo de
integridade explica o escopo SHA-256 e referencia integrity/ sem imprimir hashes
completos no corpo humano nem alegar nova verificação de originais.

## 6. Apresentação, dispositivos e privacidade

Não expor por padrão no dossiê UUIDs, SHA-256 completos, IPs completos, device
identifiers, cookies/tokens, emails, telefones, paths absolutos, member paths
internos ou nomes reais de inputs. Texto bruto de mensagens pessoais exige
necessidade e aprovação explícitas sob contrato próprio; v1 não oferece um
mecanismo de exceção que o injete na prosa humana. Artefatos técnicos podem
conservar identificadores exigidos por seus contratos aprovados; packaging não
os propaga para novas superfícies por conveniência.

Projeções humanas usam campos permitidos, escaping de Markdown e rejeição de
markup ativo/links externos em labels/legendas. Texto fornecido pelo operador
não é template executável nem instrução para o motor. Filtros estruturais não
garantem anonimato: captions, datas, contexto e imagens podem ser identificáveis.
Exposições explícitas exigem revisão humana de privacidade; o índice deve
distinguir o que é contexto fornecido do que é finding técnico.

Model codes preservam o valor reportado pela fonte e sua classificação técnica,
sem device id → pessoa, model code → proprietário ou conta → pessoa. Um exemplo
puramente sintético de código é MODEL-SYNTH-A; não representa aparelho real.
Um futuro nome comercial seria mapeamento informativo opcional com tabela,
proveniência e versão explícitas, separado do código observado e sem implicar
propriedade. Não há implementação, lookup externo ou inferência desse mapeamento
na 8B0; sua habilitação futura exige escopo e validação próprios.

## 7. Mídia, comunicações, WhatsApp e exposições visuais

Source-media somente reproduz os resultados aprovados representados em 1.1.0.
LINK_EXACT_MEDIA_CONTENT não demonstra upload, envio, publicação, exclusão ou
disseminação. occurrence_count conta ocorrências catalogadas do mesmo conteúdo,
não ações, destinatários ou pessoas. LINK_ARCHIVE_MEMBER_ONLY é membro verificado
sem correspondente em ExactMediaContent sob a policy vigente; não implica
formato, vídeo, invalidade ou incapacidade geral. Gap D permanece cobertura
parcial/contratada, sem novo cálculo ou generalização para todos os eventos.

communication.message attachments sem relação explícita URI/path/hash/bytes
sustentada por capacidade aprovada continuam SOURCE_LIMITATION. A presença de
um campo isolado não cria um adapter: o ADR 0034 não aprova message attachments.
Montagem não resolve anexos por proximidade temporal, thread, sender, dispositivo,
rede, ordem, basename, pHash, similaridade visual ou inferência de filename.
Não decidir qual anexo corresponde a qual mídia.

WhatsApp fica fora do dataset técnico representado, salvo futura aquisição,
parser e análise separadamente aprovados. O dossiê pode declarar essa exclusão
de escopo; não infere atividade WhatsApp por tempo, mídia ou contatos Meta/Instagram.
Permanece condicional/não acionado, sem gerar SPECIFIC_TECHNICAL_BASIS. 8B não
autoriza implementação de WhatsApp nem entrega de originais.

Cada visual exhibit exige input_reference, local_label, display_caption textual
fornecida pelo operador, operator_selected=true, source_class=VISUAL_EXHIBIT e
role=contextual_visual. Exige também display_approved=true como registro explícito
de revisão humana da exposição; não é certificação de privacidade. A legenda é
metadata de apresentação contextual, não declaração de fato ou finding. Não
admite campo que associe automaticamente exhibit a evento, source-media item ou
F-ID. Uma relação futura exigiria contrato técnico separado e suporte aprovado.

display_caption é metadata contextual de apresentação fornecida pelo operador.
Não entra na cronologia, em findings técnicos ou nas afirmações técnicas da
seção 13; não estabelece identidade/autoria, relação evento/mídia nem suporte de
provenance para afirmação técnica. Sempre que exibida no dossiê humano ou no
índice de anexos, deve acompanhar o aviso fixo pt-BR, visualmente distinto dos
findings: “Legenda contextual fornecida pelo operador — não constitui finding técnico.”
Não classificar semanticamente a veracidade da legenda. A revisão humana de
privacidade/exposição permanece obrigatória.

v1 admite, por seleção explícita, somente JPEG e PNG já preparados para anexo,
copiados sem transformação ou inspeção semântica. PDF externo arbitrário não é
aceito como VISUAL_EXHIBIT: 8B1 não fornece sanitização de PDF, análise de conteúdo
ativo, inspeção de arquivos embutidos ou validação de segurança semântica.
Essa restrição não proíbe artefatos técnicos Markdown/JSON ou relatórios de
validação aprovados sob suas próprias classes contratadas. PDFs gerados pelo
produto pertencem exclusivamente à 8B2. Um contrato futuro poderá admitir PDFs
externos como exhibits após definir sua fronteira de segurança/validação;
nenhum parser, sanitizer ou dependência PDF é introduzido nesta etapa.
A montagem não faz OCR, reconhecimento de
face/objetos, inferência de autoria visual, pHash-event linking ou extração de
imagens de originais. Não resolve recursos embutidos/externos nem executa conteúdo
ativo. Formatos não aprovados falham. A análise de conteúdo malicioso e a remoção
de metadados não são capacidades implicitamente prometidas; materiais visuais
devem ser preparados e revisados fora da montagem antes da seleção.

## 8. Layout v1 e segurança de caminhos

Layout canônico relativo à raiz de entrega, independente do nome dessa raiz:

```text
package/
  human/
    dossier.md
    annex-index.md
  technical/
    canonical/
      consolidated-report.md
      snapshots/<local_label>.json
    supplemental/<local_label>.md
    validation/<local_label>.md
    structured/<local_label>.json
    selection-metadata.json
  exhibits/
    visual/<local_label>.<approved_extension>
  integrity/
    manifest.json
    SHA256SUMS.txt
```

Placeholders representam labels sintéticos/contratados, nunca filenames de caso.
Diretórios opcionais sem itens podem ser omitidos; o conjunto de arquivos define
o pacote. Revisão suplementar usa Markdown, suporte estruturado usa JSON,
validação usa Markdown; visual usa somente jpg ou png conforme formato declarado e
validado sem interpretação investigativa. Nomes de origem não são copiados para
o destino. A 8B2 reserva human/dossier.pdf e human/consolidated-report.pdf, ausentes
no directory-v1 da 8B1; habilitá-los exigirá contrato de perfil futuro explícito.

Paths lógicos e input_reference usam POSIX, relativos e portáveis. Rejeitar
absolutos, drive prefixes, UNC, traversal, componentes vazios, ponto/ponto-ponto,
backslashes, NUL/controles, ADS/dois-pontos, trailing dot/espaço e nomes reservados
Windows. Rejeitar duplicatas, colisões case-fold e prefixos arquivo/diretório;
não corrigir silenciosamente. Outputs usam somente os nomes fixos e labels ASCII
acima. Input paths Unicode devem ser NFC sem normalização silenciosa.

Não seguir symlinks, junctions ou reparse points em inputs, pais ou destino;
recusar arquivo não regular e escapes após resolução. A raiz de inputs e o
destino não podem se sobrepor. Validar path/handle e estabilidade de leitura
para que os bytes conferidos sejam os copiados; arquivo alterado durante leitura
falha. Não restaurar atime/ctime ou ajustar permissões dos inputs. Sem promessa
de preservação de atime causada por leitura do host; regras Foundation por
plataforma continuam válidas. Nenhuma checagem autoriza abrir originals/working.

## 9. Manifesto e SHA256SUMS: dependência acíclica

Contrato dossier.package_manifest/1.0.0, implementado em 8B1-E e validado em 8B1-G.
Envelope com policy_id, policy_version e entries ordenadas por package_path.
Cada entrada de payload exige:

| Campo | Semântica |
| --- | --- |
| package_path | Caminho relativo canônico, sem host path. |
| role | Papel de entrega explícito, como human_dossier, annex_index, consolidated_report, report_snapshot, technical_review, structured_support, validation_report, contextual_visual ou selection_metadata. |
| source_class | Uma classe de entrada aprovada para arquivos copiados; GENERATED_PRESENTATION para dossiê/índice e GENERATED_METADATA para metadata de seleção. Estas duas categorias de saída não são classes de entrada ou epistemológicas e não tornam a apresentação canônica. |
| byte_size | Tamanho inteiro não negativo dos bytes efetivamente empacotados. |
| sha256 | SHA-256 hexadecimal minúsculo dos mesmos bytes empacotados. |

local_label opcional liga um payload copiado ao item de seleção e justifica
rastreabilidade sem divulgar o path original. Nenhuma identidade pessoal,
generated_at, UUID aleatório, relógio ou host path é exigido ou armazenado.
Novos campos opcionais exigem justificativa/versionamento, sem bag genérica de
metadata. O manifesto é índice de integridade, não afirmação de autenticidade,
autoria, admissibilidade, validade jurídica ou peso probatório.

Regra congelada: seja P o conjunto de todos os arquivos do pacote exceto
integrity/manifest.json e integrity/SHA256SUMS.txt. O manifesto contém exatamente
um registro por arquivo de P e nenhum outro. SHA256SUMS.txt cobre exatamente
P mais integrity/manifest.json; exclui somente a si próprio. Isso verifica o
manifesto sem dependência recursiva. Arquivo extra, ausente ou entrada duplicada
invalida a completude do pacote. Diretórios não recebem hash.

SHA256SUMS usa linhas `sha256`, dois espaços ASCII e `package_path`, ordenadas
por path, em UTF-8/LF, com LF final. Hash é calculado sobre bytes, sem conversão
de line endings de payloads copiados. A integridade do próprio SHA256SUMS exige
referência externa confiável se necessário; modificações coordenadas de payload,
manifesto e sums não são detectáveis por uma baseline interna substituída.

Somente SHA-256 em v1. Não há assinatura criptográfica, ICP-Brasil, criptografia
ou certificado. Conferência demonstra consistência de bytes contra o manifesto
do pacote, não assinatura jurídica, autoria, completude da cadeia de custódia
ou autenticidade anterior à aquisição. Hashes continuam identificadores técnicos
potencialmente sensíveis, e o manifesto não implica anonimato.

## 10. Determinismo e fronteira arquitetural

Para inputs aprovados byte-idênticos, seleção/configuração explícita idênticas
e mesma versão do contrato/implementação, exigir bytes idênticos em dossier.md,
annex-index.md, selection-metadata.json, manifest.json e SHA256SUMS.txt; também
iguais mapping de paths, conjunto de arquivos e ordenação do pacote. Permutar
listas de seleção não altera saída. Payloads copiados preservam exatamente
seus bytes, inclusive line endings existentes.

Textos gerados: UTF-8 sem BOM, LF e LF final; idioma dos templates fixo pt-BR.
JSON gerado: chaves ordenadas, ensure_ascii=True, separadores compactos, LF
final, sem floats especiais/chaves duplicadas. Contagens/tamanhos são inteiros,
não bools. Não usar locale, timestamps/permissões do filesystem, ordem de
enumeração, paths absolutos, current clock ou UUID para gerar conteúdo.
issued_date explícita é metadata documental, não timestamp de evidência e não
atesta aquisição; ausência não recebe default. Não há promessa de bytes iguais
entre versões de renderer nem de PDF/ZIP reprodutível nesta etapa.

A montagem implementada na 8B1 recebe somente artefatos já gerados, locais e selecionados.
Não aceita --case-root, não abre evidence.db, não consulta SQLite, originals ou
working, não parseia fontes, normaliza eventos, observa device/network, correlaciona,
executa análise temporal ou source-media query, calcula pHash, faz OCR, infere
identidades, usa rede/cloud/API/LLM ou produz novos findings. Não chama verify
de evidências: a conferência SHA local aqui é somente dos artefatos do pacote.
O renderer existente continua snapshot-only. DB/filesystem não se tornam
atômicos; validação estrutural dos inputs não comprova autenticidade criptográfica.

## 11. Falhas e publicação

Validação fail-closed antes de publicar. Rejeitar versão de seleção não suportada,
canonical artifact version desconhecida, conjunto misto/incompatível, ausência
de relatório/anchor requerido, divergência relatório/snapshots, classe não aprovada,
papéis conflitantes, path duplicado/colisão/escape, inclusão de original,
expected hash divergente, input instável, issued_date inválida, visual sem seleção
ou aprovação explícita e violação de privacidade detectável pelas regras estruturais.
Campos desconhecidos que alterem seleção/exposição não são ignorados silenciosamente.
Não fazer fallback para scanner, contrato antigo, fonte real ou rede.

Erros são técnicos e não reproduzem payload, identificadores sensíveis ou paths
absolutos. A implementação 8B1 define códigos estáveis e limites de recursos sob ADR 0037
antes de aceitar arquivos; ausência de regra de formato/validação é rejeição,
não permissão genérica. Documentos suplementares não são executados ou tratados
como instruções. A validação não garante detectar todo dado sensível em prosa
ou imagem; a revisão humana continua obrigatória para entrega real.

Destino final deve estar ausente; nunca substituir pacote existente. Escrita usa
staging separado no filesystem de destino, monta e confere todos os arquivos,
hashes e completude, e publica somente após sucesso. Falha contratual ou de I/O
não deixa pacote parcial publicado. Staging não é entrega; se não puder ser
removido com segurança, registrar falha sem apresentá-lo como sucesso e tratar
seu conteúdo como sensível. Não apagar arquivos preexistentes ou fontes.
No destino final, não acrescentar logs/arquivos fora do manifesto após a publicação.

## 12. Segurança operacional e entregas futuras

Empacotar pode duplicar dados sensíveis; seleção explícita é obrigatória e o
próprio output pode ser sensível. Inputs, derivados, staging e pacotes reais
permanecem fora do Git. .gitignore não é controle de privacidade nem proteção
para arquivos já rastreados. Nenhum nome, data, imagem, identificador ou conteúdo
de caso deve entrar em fixtures, logs ou exemplos do repositório. Transporte,
criptografia e assinatura estão fora de v1 sem escopo separado.

Original Evidence Source Package exige milestone e aprovação explícitas próprias.
Selecionar um visual preparado não autoriza a montagem a buscar seu original.
Revisão jurídica e revisão de privacidade não são substituídas pelo hash.

| Milestone | Entrega e fronteira |
| --- | --- |
| 8B0 — Final Legal-Technical Dossier & Export Contract | Concluída; este ADR Accepted após revisão humana, somente arquitetura/contrato. |
| 8B1 — Deterministic Dossier Assembly | Dossiê Markdown, índice, metadata de seleção, estrutura de diretórios, manifesto e SHA256SUMS; sem biblioteca PDF ou ZIP obrigatório. A–G posteriormente implementados sob ADR 0037 e validados sinteticamente; não implementados por este ADR 8B0. |
| 8B2 — Human PDF Export | PDFs do dossiê e relatório consolidado; decidir renderer/toolchain, fontes, página, cabeçalhos/rodapés, paginação, overflow de tabelas, bookmarks/TOC, metadata, determinismo, imagens, privacidade e acessibilidade aplicável. Nenhum renderer escolhido em 8B0. |
| 8B3 — Final Package Integrity & Real-Case Validation | Validação real controlada fora do Git, conteúdos permitidos/proibidos, privacidade, integridade, determinismo, revisão final e paridade entre plataformas quando aplicável. Não autorizada como execução real pela 8B0. |

Diretório determinístico basta para 8B1. ZIP/archive final, se necessário, exige
decisão separada sobre layout, metadata e reprodutibilidade; não se promete ZIP
byte-idêntico. PDF exige contrato de renderer da 8B2; não se promete PDF byte-idêntico
agora. Assinatura permanece fora dessas autorizações e depende de escopo próprio.

## 13. Matriz mínima de testes contratada em 8B0 e posteriormente implementada em 8B1

Todos os materiais de teste devem ser inteiramente sintéticos. Esta matriz
documenta exigências posteriormente implementadas e validadas sinteticamente em
8B1-A–G sob ADR 0037; a etapa contratual 8B0 não criou testes ou fixtures.

| Cenário | Resultado exigido |
| --- | --- |
| Pacote mínimo: relatório compatível e anchor | Duas camadas, 14 seções na ordem fixa, índice completo e referências válidas; sem anexos inventados. |
| Repetição e permutação de listas de seleção | Bytes idênticos nos cinco artefatos gerados; mapping/ordem de paths idênticos; arrays técnicos preservados. |
| Versões mistas/desconhecidas e perfil inválido | Rejeição global, sem conversão silenciosa ou fallback. |
| Relatório/anchor ausente, múltiplo ou relatório divergente | Nenhum pacote publicado. |
| Paths duplicados, colisões case-fold e arquivo/diretório | Rejeição, sem sobrescrita ou renomeação automática. |
| Traversal, absoluto, drive, UNC, backslash, ADS, reservados e Unicode inseguro | Rejeição antes de leitura/escrita fora da base. |
| Symlink/junction/reparse escape e input alterado durante leitura | Falha; nenhum byte não validado é publicado. |
| ORIGINAL_EVIDENCE e LEGACY_MANUAL_WORK_PRODUCT selecionados | Rejeição; nenhum scanner ou cópia implícita de original. |
| Revisão/suporte suplementar, validação ou visual com afirmações ou hipóteses | Somente cópia/indexação/referência separada quando a classe permitir; nenhuma extração de narrativa, por LLM ou texto livre determinístico. F/W/G, findings, cronologia, contagens, statements, relações source-media e classes epistemológicas canônicos permanecem iguais. LEGACY_MANUAL_WORK_PRODUCT continua excluído. |
| Visual sem operator_selected/display_approved, legenda inválida ou formato não aprovado | Rejeição. |
| Visual JPEG/PNG aprovado e PDF externo selecionado como VISUAL_EXHIBIT | JPEG/PNG elegíveis sob as demais regras; PDF rejeitado, sem parser/sanitizer PDF. Artefatos Markdown/JSON das classes técnicas aprovadas não são afetados. |
| Visual válido e imagem coincidente com mídia | Apenas anexo contextual; nenhuma associação a evento/finding/source-media, OCR ou inferência visual. |
| display_caption exibida no dossiê ou índice | Aviso fixo contextual presente e distinto dos findings; não alimenta cronologia, findings, seção 13, identidade/autoria, vínculo evento/mídia ou suporte de provenance. Sem classificação semântica de veracidade. |
| Attachment sem vínculo aprovado | SOURCE_LIMITATION; tempo/thread/sender/basename/pHash não resolvem mídia. |
| Artefatos Meta/Instagram próximos no tempo | Nenhuma atividade WhatsApp inferida ou parser acionado. |
| Findings/source-media/ocorrências/truncamentos existentes | Statements, classes, F/W/G, unidades, limites e ponteiros preservados; member-only conservador. |
| UUID/relógio/locale/ordem do filesystem controlados adversarialmente | Sem efeito nos bytes gerados e sem novos identificadores aleatórios. |
| issued_date ausente, explícita válida ou inválida | Ausente sem default; explícita preservada; inválida falha. |
| case_reference ausente ou token opaco válido | Seção 1 completa e determinística em ambos os casos; token não atribui identidade nem exige pessoa, parte, CPF/documento ou número de processo. Campos pessoais/jurisdicionais não são introduzidos. |
| Privacidade, captions, markup ativo e tokens pessoais sintéticos | Projeção allowlist/escaping, rejeições estruturais e separação humana/técnica; nenhuma promessa de anonimato. |
| Código de modelo sintético e identificadores coexistentes | Código permanece separado de eventual mapeamento informativo; nenhuma propriedade/identidade inferida. |
| SHA/tamanho, expected hash divergente e payload alterado | SHA dos bytes empacotados correto; divergência falha. |
| Manifesto/SHA256SUMS | Manifesto cobre P; sums cobre P mais manifesto; nenhum ciclo; extra/ausente/duplicata invalida completude. |
| Sentinelas CASE_ROOT/DB/originals/working, queries e novos findings | Acesso/execução proibidos; somente artefatos selecionados abertos. |
| Sentinelas rede/cloud/API/LLM e referências remotas | Nenhuma chamada ou resolução remota. |
| Falha contratual, de escrita ou publicação; destino já existente | Nenhum pacote parcial publicado, destino preexistente preservado. |
| Windows/Linux sob implementação suportada 8B1 | Paridade byte a byte dos textos/JSON gerados e mapping portátil, sem prometer metadata idêntica do host, PDF ou ZIP. |

## 14. Decisão aceita, consequências e revisão de compatibilidade

A seleção declarativa, duas camadas e hashes acíclicos separam organização
técnica de advocacy, mantêm evidências fora do Git e impedem que exportação vire
investigação oculta. Oferecem leitura acessível ao advogado e suporte auditável
ao profissional técnico, preservando provenance e limites epistemológicos.
Desacoplar PDF/archive permite revisão independente do renderer, sem mudar
semântica de findings para satisfazer layout ou transporte.

Custos: atribuição de pessoas/ações pode exigir documentos e trabalho externos;
o suporte técnico pode ser complexo para leitor não técnico; seleção de visuais
e revisão de exposição exigem trabalho explícito do operador; copiar materiais
duplica conteúdo sensível. Não há entrega automática de originais, WhatsApp,
PDF, ZIP ou assinatura. Hashes não substituem uma baseline externa confiável,
controle de custódia ou revisão jurídica.

Revisão contra contratos anteriores: ADR 0031 conserva classes, neutralidade,
unidades e limites de afirmações; ADR 0032 conserva snapshots/provenance/schema v5
e ausência de atomicidade global; ADR 0033 conserva renderer snapshot-only,
relatório detalhado, F/W/G e limitações de autenticidade; ADR 0034 conserva matching
exato, ausência de action semantics e SOURCE_LIMITATION de mensagens; ADR 0035
conserva versões 1.1.0/1.1.0/1.0.0, cobertura parcial e compatibilidade legada.
As 14 seções do dossiê não alteram as 20 seções do relatório consolidado.

Este contrato é genérico; exemplos de labels, modelo e paths são sintéticos.
A revisão 8B0 utilizou somente documentação e regressões sintéticas do repositório,
sem CASE_ROOT, evidências ou artefatos reais. O fechamento formal promoveu este ADR,
AGENTS.md, README.md e docs/architecture.md. A aceitação contratual não implementou
8B1; os slices A–G foram posteriormente implementados sob ADR 0037 e validados
sinteticamente. Execução real permanece na futura 8B3, com escopo separado.
