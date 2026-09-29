# ADR 0038 — Human PDF Export Contract

Status: Accepted.

Milestone: 8B2.0 — Human PDF Export Contract, somente documentação.
Revisão humana concluída; 8B2.0 aceita como contrato de implementação.
A aceitação autoriza os slices a partir da 8B2-A, sem iniciar sua execução nesta
promoção documental e sem autorizar execução real de caso. A qualificação explícita
de versões, licenças e capacidades do renderer/toolchain continua obrigatória na
8B2-A antes da 8B2-B; nenhuma dependência PDF foi qualificada por esta aceitação.
Base inspecionada: 9646977, após fechamento sintético 8B1-A–G.
Nenhum slice PDF foi implementado ou validado por este ADR. Aceitação humana
do contrato e aprovação explícita das dependências precedem implementação.

## 1. Contexto e relação com os contratos aceitos

Os ADRs [0036](0036-final-legal-technical-dossier-export-contract.md) e
[0037](0037-deterministic-dossier-assembly.md) permanecem Accepted, inalterados.
8B0 definiu o dossiê; 8B1 implementou sua montagem determinística, sem PDF.
8B2 acrescenta apresentação dos documentos já montados. Execução real permanece
na futura 8B3, sem autorização implícita por esta proposta ou sua aceitação.

Preservam-se os contratos dos ADRs [0031](0031-consolidated-technical-report-contract.md),
[0032](0032-read-only-report-data-snapshot.md),
[0033](0033-first-consolidated-technical-report.md) e
[0035](0035-consolidated-report-media-link-integration.md): report.consolidated/1.1.0,
report.data_snapshot/1.1.0, source_media.provenance_link/1.0.0 e schema v5.
PDF não modifica policies, classificações OBSERVED/DERIVED/REPORTED/HYPOTHESIS,
unidades, escopos, truncamentos, limites, referências ou F/W/G existentes.

## 2. Escopo e exclusões

Transformação de apresentação, offline, de exatamente dois documentos aprovados
do mesmo pacote 8B1. Sem investigação, CASE_ROOT, descoberta de caso, SQLite/DB/ORM,
originals/working, consultas, parsing de evidência, normalização, correlação,
novos findings, inferência de identidade/autoria/sessão/causalidade ou LLM.
Não executar novamente snapshots, build_consolidated_model, projeção humana ou
renderer Markdown para produzir ou conferir narrativa durante a exportação.

Excluídos: execução real, WhatsApp ingestion, OCR, reconhecimento facial,
interpretação de imagem, ingestão de PDF como exhibit, sanitização de PDF de
terceiros, ZIP/archive, email/upload/portal/cloud, criptografia/senha, assinatura,
ICP-Brasil/PAdES, certificados, autoridade de timestamp, petições, estratégia ou
conclusão jurídica. Sem selos, insígnias, campos de assinatura ou aparência de
certificação. O produto não é software pericial certificado.

## 3. Auditoria local da implementação

Foram lidos AGENTS, README, architecture e os ADRs acima. Inspeção de código,
configuração e testes, sem executar o pipeline ou abrir qualquer caso:

| Superfície | Constatação e consequência |
| --- | --- |
| dossier/selection.py e validation.py | Seleção estrita/DTOs imutáveis; validação canônica e JPEG/PNG já pertencem à montagem. Não repetir análise canônica no PDF. |
| dossier/projection.py e rendering.py | Dossiê possui título fixo, 14 H2, H3, parágrafos, tabelas, escaping e link relativo ao índice. Legendas ficam no índice, fora do dossiê. |
| reports/consolidated.py | Relatório possui título fixo, 20 H2, H3 de W/F/G, tabelas até oito colunas, listas, negrito de truncamento e literais entre backticks. Escaping difere do dossiê. |
| dossier/packaging.py | Captura estável Foundation, contenção, ownership, staging e publicação sem substituição Linux/Windows. Reusar primitives compatíveis, sem copiar lógica insegura. |
| dossier/integrity.py | Manifesto/sums acíclicos e árvore exata. verify_integrity_result depende de resultado em memória da montagem; não é um loader público para pacote publicado arbitrário. Será necessário um leitor estrito somente leitura desse contrato. |
| dossier/service.py e cli/dossier.py | assemble orquestra A–E e publica uma vez; não há operação de filesystem após publicação confirmada. CLI emite bytes ASCII/LF e erro sanitizado. |
| Testes rendering/service/integrity/cross_platform | Cobrem 14 seções, escaping, fontes separadas, integridade, falhas, 21 snapshots, CRLF copiado e fingerprint de 31 arquivos. Não são testes de PDF. |
| pyproject.toml / uv.lock | Python >=3.12; Pillow 12.3.0 e ImageHash 4.3.2 existentes. markdown-it-py 4.2.0 é transitivo; não constitui frontend PDF aprovado. Sem renderer/parser PDF declarado. |
| Ambiente Python local | Venv Python 3.12.11: nenhum ReportLab, WeasyPrint, Playwright, pypdf, PyMuPDF ou pypdfium2 encontrado no inventário de distribuições. Isso não prova ausência em todo o computador. |
| Ferramentas de sistema | Conversores/validadores PDF consultados não foram encontrados no PATH. Nenhuma capacidade de renderer foi exercitada. |
| Dockerfile / compose | Imagem Python 3.12-slim por digest, uv 0.8.22 e dev lock; sem instalação explícita de fontes/toolchain PDF. Compose atual contém mounts de caso e não serve à execução PDF. Não foi iniciado. |
| Assets / CI | Nenhum bundle TTF/OTF ou configuração CI rastreada foi encontrado. Não existe família de fontes aprovada para redistribuição pelo projeto. |

Gates anteriores de 8B1-G permanecem os registrados no ADR 0037; não foram
reexecutados nesta tarefa documental. Nenhuma propriedade PDF é deduzida desses
resultados. Não houve pesquisa de rede, instalação ou geração experimental.

## 4. Bytes de origem e fronteira de confiança

| Destino PDF | Única fonte de conteúdo |
| --- | --- |
| human/dossier.pdf | Bytes exatos de human/dossier.md do pacote validado. |
| human/consolidated-report.pdf | Bytes exatos de technical/canonical/consolidated-report.md do mesmo pacote. |

Os arquivos permanecem intactos. Decodificar sua gramática de apresentação não
autoriza extrair fatos para novo modelo, resumir, ordenar novamente ou corrigir
texto. Nenhum snapshot, suplemento, validação, índice de anexos ou imagem alimenta
a narrativa PDF. Esses payloads são lidos em streaming somente para integridade
do pacote. Não se seguem links ou ponteiros. Metadata administrativa é validada
para reconhecer directory-v1, mas não fornece novo conteúdo ao PDF.

O operador fornece um pacote previamente montado/aprovado por 8B1. Hashes internos
detectam incoerência; não comprovam que um pacote coerentemente adulterado foi
produzido pelo motor. Não há assinatura ou baseline externa nova. Não afirmar
autenticidade, completude do caso, verdade, aprovação jurídica ou custódia integral.

## 5. Arquitetura, perfil e versionamento decididos

Escolha B: saída de apresentação separada, imutável, posteriormente vinculável
pela 8B3. Nunca acrescentar PDF ao diretório publicado 8B1. Nunca copiar o pacote
inteiro para criar implicitamente um novo directory-v1.

Contrato independente proposto: **dossier.pdf_export/1.0.0**, perfil
**pdf-presentation-v1**. Não é um valor novo aceito por dossier.selection/1.0.0.
dossier.selection/1.0.0, directory-v1 e dossier.package_manifest/1.0.0 conservam
significado e bytes. O comando assemble permanece sem PDF e sem mudança automática.
Pacotes 8B1 sem PDF continuam válidos. Alteração incompatível do novo perfil
requer versão própria, nunca mudança silenciosa do contrato antigo.

Árvore exata da saída nova, quatro arquivos e nenhum diretório extra:

```text
human/dossier.pdf
human/consolidated-report.pdf
integrity/pdf-export-manifest.json
integrity/SHA256SUMS.txt
```

Não contém cópias de Markdown, snapshots, visuais, fontes, logs, HTML, thumbnails
ou relatório de testes. A vinculação técnica não transforma esta saída no pacote
final de entrega 8B3. Os caminhos reservados pelo ADR 0036 são preservados dentro
da nova raiz, sem alterar sua raiz original.

## 6. Auditoria das alternativas de renderer

Avaliação de adequação arquitetural, não benchmark nem confirmação de capacidades
de releases não disponíveis. As categorias abaixo não substituem documentação
de versão, licença e testes a obter mediante aprovação humana futura.

| Candidato | Adequação, risco e decisão |
| --- | --- |
| Geração direta Python: ReportLab | Selecionado como proposta única. Permite projetar uma fronteira de texto/estilos explícitos, sem engine de navegação ou HTML de entrada. Controle de tabelas, paginação, fontes, outlines, metadata e IDs deverá ser demonstrado na versão fixada; não foi testado aqui. Footprint, extensões nativas transitivas, Unicode, licença/distribuição e manutenção exigem confirmação. |
| HTML/CSS: WeasyPrint | Não selecionado. Introduziria representação HTML/CSS, resolução de assets e stack tipográfica nativa a controlar e fixar em Windows/Linux. Ganhos de layout não justificam essa fronteira adicional para a gramática limitada atual. Versões, dependências, licença e capacidades não verificadas localmente. |
| Browser: Chromium/Playwright | Não selecionado. Acrescentaria runtime de browser, navegação/script e superfície de rede/arquivos, além de seu ciclo de atualização, impressão e metadata. Isolamento e footprint maiores por construção da categoria; nenhuma garantia de outlines/fontes/determinismo da versão presumida. |
| Conversor nativo: wkhtmltopdf ou equivalente | Não selecionado. Binário externo e bibliotecas/fontes de sistema não auditados nem pinados; paridade e manutenção/licenciamento não estabelecidos localmente. Não substituir seleção por um executável encontrado no host. |

Para todos, Windows nativo, imagem Linux, Unicode/pt-BR, imagens, paginação,
repetição/split de tabelas, bookmarks, metadata, segurança e identidade binária
dependem da versão concreta. Nenhum possui comprovação local neste marco.
Imagens não são requisito do renderer v1 escolhido. A decisão ReportLab é
arquitetural, baseada na menor fronteira funcional necessária, não em familiaridade
ou alegação de que todas as capacidades já estejam comprovadas.

## 7. Toolchain proposta e gate de qualificação

Toolchain única: **ReportLab** para render; **pypdf** para parser/inspeção e extração
independentes do renderer; **pypdfium2/PDFium** somente para rasterização sintética
de regressão. Stdlib para modelo fechado, hashes, JSON e orquestração. Não usar
HTML/CSS intermediário, navegador ou fallback renderer. Não passar texto do usuário
diretamente ao mini-markup de Paragraph ou equivalente; construir spans seguros.

Antes de adicionar dependências, revisão humana deve confirmar releases exatas,
licenças e avisos transitivos, suporte Python/Linux, uso e distribuição das fontes,
controle de metadata/IDs/subsets/ToUnicode, outlines e comportamento de extração.
Não há números de versão inventados neste ADR. A qualificação inicial 8B2-A deve
registrar valores concretos e testes mínimos; sem isso não há ambiente autorizado
para gerar PDF do produto, nem avanço a B. Impossibilidade de satisfazer algum
requisito exige parar e revisar este ADR, não escolher silenciosamente alternativa.
Essas pendências são gates explícitos de implementação, não resultados aprovados.

## 8. Plano de dependências e build

| Componente novo | Papel / pin / impacto futuro |
| --- | --- |
| reportlab | Runtime exclusivamente da exportação. Versão exata, hashes de artefatos e fechamento transitivo no uv.lock após aprovação; auditar eventuais wheels/extensões e dependências nativas. |
| pypdf | Runtime de validação independente. Versão exata/hashes no mesmo lock; parser não é sandbox, continua limitado/isolado. Confirmar licença da release e limites de leitura antes de adotar. |
| pypdfium2 e PDFium | Dependência de desenvolvimento da regressão visual. Fixar wrapper, binário nativo, arquitetura, hashes e licenças/avisos dos dois. Não necessário para emitir PDFs em produção. |
| DejaVu Sans e DejaVu Sans Mono | Bundle de fontes proposto na seção 11, releases/arquivos/hashes exatos e licença de cada distribuição revisados antes de inclusão. Não são fonts do host. |
| Imagem canônica | Dockerfile PDF dedicado futuro; imagem/base e bibliotecas por digest/inventário. Não reaproveitar mounts de caso do Compose. Sem apt/download/pip durante exportação. |

Somente uma futura mudança aprovada altera pyproject, lock, assets e Dockerfile.
Não promover dependência transitiva a API implícita. Build com uv 0.8.22 e lock
fechado; versão exata de Python também integra a receita. Windows invoca a imagem
Linux por Docker, sem exigir instalar renderer/fontes nativamente. Instalação/build
é preocupação separada, nunca acionada automaticamente por dee dossier pdf.
Licenças e estado de manutenção não foram confirmados por rede nesta tarefa.

## 9. Ambiente canônico

Linux/amd64 em imagem OCI dedicada, Python **3.12.14** proposto por continuidade
com o gate Linux anterior; base por digest, OS e todas as bibliotecas/fontes
inventariadas. A release concreta do renderer, parser e bundle ainda deve ser
qualificada e fixada em A. Tag mutável, versão em intervalo ou fonte sem hash
nunca identificam um ambiente aceito.

Receita `render_environment_id` de 64 hex minúsculos = SHA-256 do inventário JSON
canônico de Python, OS/base digest, arquitetura, pacotes/versões/hashes, fontes,
versão da implementação/estilos e variáveis fixas. Inventário é artefato público
de build sem dado de caso ou path de host; fica versionado após revisão futura.
Não incluir o digest da imagem que contém o próprio inventário, evitando ciclo;
registrar a associação inventário → digest final da imagem no build externo.

Fixar LANG=LC_ALL=C.UTF-8, TZ=UTC, PYTHONHASHSEED=0 e
PYTHONDONTWRITEBYTECODE=1. Números, unidades e texto usam templates pt-BR fixos,
não locale. Sem relógio, hostname, username, UUID, paths do host ou descoberta
de fontes. Verificar inventário antes de processar conteúdo; divergência falha.
Não executar render nativo Windows nesta versão. Arquiteturas diferentes,
incluindo emulação, não herdam a garantia sem qualificação própria.

## 10. Garantia de determinismo

Modelo B: mesmos bytes de origem, mesma versão de apresentação, mesmo ambiente
canônico e configurações fixas produzem PDFs byte-idênticos. Repetições com clocks,
roots e ordens de enumeração diferentes devem comparar SHA-256 do PDF inteiro e
da saída de integridade inteira. O manifesto vincula também os demais bytes do
pacote; mudar suplemento sem mudar os dois Markdown mantém PDFs, mas altera o
vínculo técnico ao pacote. Não se promete igualdade entre releases diferentes.

Windows e Linux podem invocar a mesma imagem: isso é compatibilidade de invocação,
não render nativo em ambas as plataformas. A garantia é requisito a demonstrar
em 8B2-G, não propriedade já observada. Não aceitar equivalência textual como
substituto de identidade binária dentro do ambiente contratado.

## 11. Fontes e Unicode

Família proposta única para texto: DejaVu Sans Regular/Bold/Oblique/BoldOblique;
literais: DejaVu Sans Mono Regular/Bold. Cada arquivo deve ter versão/hash e
licença de embedding/subsetting/distribuição aprovados. Bundle interno somente
leitura da imagem; sem busca em diretórios de fontes do OS, rede ou estação.

Embeddar subsets determinísticos com mapas ToUnicode para todos os glifos usados,
incluindo chrome/TOC. Ordenar glifos e nomes de subset por regra fixa da versão
qualificada; não aceitar seeds aleatórias. Testar acentos pt-BR, travessão, setas,
sinais, underscores e literais usados pelos renderers atuais. Não normalizar NFC,
substituir caracteres, fazer transliteração ou desenhar tofu silenciosamente.

Não há fallback de família em v1. Fonte/estilo/glifo ausente ou sequência que a
toolchain não consiga posicionar e extrair corretamente falha FONT_UNSUPPORTED.
Texto Unicode não implica suporte universal a scripts/shaping/emoji. Combinações
de base/diacrítico exigem teste de posicionamento e extração preservada; a ausência
de suporte limita esta exportação operacional, não invalida o pacote 8B1.

## 12. Geometria e tipografia

A4 retrato, 210 × 297 mm, rotação zero. Margens esquerda/direita 20 mm,
superior/inferior 25 mm; corpo 170 × 247 mm. Conversão exata 72 pt por 25,4 mm,
arredondamento de coordenadas a 0,001 pt, determinístico. Não usar impressora ou
preferências do viewer. Sem páginas paisagem automáticas.

| Elemento | Fonte/tamanho/entrelinha em pt; espaçamento antes/depois |
| --- | --- |
| Título H1 único | Sans Bold 18/22; 0/14 |
| H2: seção numerada | Sans Bold 13/17; 14/8 |
| H3: subseção existente | Sans Bold 11/14; 10/6 |
| Corpo e listas | Sans Regular 10,5/14; 0/6; listas com recuo de 5 mm |
| Tabela e cabeçalho de tabela | Sans Regular/Bold 9/12; padding interno 3 pt em cada lado |
| Literais técnicos/code | Sans Mono 9/12, preservando conteúdo |
| Legenda contextual | Sans Regular 9/12; 4/6; estilo reservado, sem importar captions em v1 |
| Limitações/aviso | Corpo; Bold somente onde a gramática da fonte já marca negrito |
| Header/footer e TOC | Sans Regular 9/12; TOC com linhas na ordem de seções |

Texto preto, fundo branco; tabela com borda cinza de 0,5 pt e header cinza claro.
Contraste textual mínimo 4,5:1, sem distinção somente por cor. Piso absoluto 9 pt,
incluindo tabelas e chrome. Não reduzir fonte para fazer conteúdo caber.

## 13. Header, footer e numeração

Header fixo a 12 mm do topo: `Dossiê técnico` ou `Relatório técnico consolidado`,
respectivamente. Footer a 12 mm da borda inferior: `Página N`, começando em 1 na
primeira página, contando título e TOC. Sem total de páginas no footer, anexos ou
páginas não numeradas. Chrome fora da área de corpo, sem interseção de caixas.
Não acrescentar issued_date/case_reference, SHA, ID, nome de arquivo, data de
geração, usuário ou path ao chrome. O que já está no corpo aprovado permanece.

## 14. Sumário visível, bookmarks e links

Ambos têm sumário visível `Sumário` após o título, antes da primeira seção,
contendo somente os 14 ou 20 H2 fixos, com números de página. Sem resumo, título
inventado ou H3 dinâmico no sumário. Sumário não conta como seção do documento.
Reservar até duas páginas iniciais: título e TOC na primeira, continuação do TOC na
segunda somente se necessária; não emitir segunda página vazia. Corpo começa em
página nova. Paginação do TOC por medição fixa, antes de paginar corpo; segunda
passagem insere números nas posições reservadas, sem alterar layout. Não iterar
indefinidamente; divergência entre passagens falha RENDER_FAILURE.

Outlines obrigatórios: título fixo no nível raiz, H2 fixos como filhos, na ordem
original. H3 permanece no corpo, sem bookmark baseado em F/W/G/texto dinâmico.
Destinos locais por ordinal do heading, não por texto sensível. Capacidade de
outlines e TOC deve ser comprovada em A/B, nunca omitida silenciosamente.

Somente links internos GoTo para esses destinos. Link do Markdown ao índice é
apresentado como texto `Índice de anexos (annex-index.md)`, sem abrir/copiar índice
ou criar GoToR. URLs que ocorram como texto permanecem texto. Não ativar links
externos, file/URI/Launch, caminhos locais ou navegação; não resolver recursos.

## 15. Gramática fechada de apresentação

Entrada UTF-8 estrita, sem BOM/NUL, controles salvo LF, ou bidi controls. Os dois documentos
8B1 usam LF; CRLF nesses caminhos gerados não é normalizado: falha de contrato
de origem/gramática. Suplementos CRLF continuam válidos e opacos no pacote.
Sem trimming/normalização Unicode ou reescrita dos bytes capturados.

Reconhecer exclusivamente:

- Um H1 inicial com o título exato do renderer correspondente; 14 ou 20 H2
  numerados, textos e ordem iguais às constantes existentes. Não criar seção.
- H3 em posição de bloco, reproduzindo texto sem reinterpretar W/F/G; sem H4–H6.
- Parágrafos separados por linha vazia, listas simples `- ` sem aninhamento,
  tabelas pipe com header e separador `---`, número de células consistente.
- Escapes literais emitidos pelo dossiê para `\\`, backtick, asterisco,
  underscore, chaves, colchetes, parênteses, hash, pipe e exclamação; entidades
  `&amp;`, `&lt;`, `&gt;` decodificadas uma única vez como texto, nunca markup.
- No relatório, preservar escapes de tabela de backslash/pipe/underscore;
  underscore em prosa é literal. Backticks delimitam literais inline; `**...**`
  delimita o negrito existente. Sem interpretação recursiva dentro de literais.
- Exatamente o link fixo `[Índice de anexos](annex-index.md)` do dossiê,
  convertido conforme seção 14. Escapes de colchetes dinâmicos não são links.

Separar células somente por pipes não escapados, respeitando paridade de
backslashes; remover apenas sintaxe delimitadora, nunca conteúdo. Parênteses,
colchetes, operadores e pontuação em prosa continuam literais quando não formam
a construção fixa acima. Não usar autodetecção de URLs ou itálico por underscore.
HTML cru, imagens, fenced code, scripts, CSS, autolinks, outros links Markdown,
extensões/tokens desconhecidos falham UNSUPPORTED_MARKDOWN; não são descartados.
Entidade que representa `<tag>` continua dado literal escapado no backend.

Parser limitado a essa apresentação, com DTOs de blocos/spans e posições de
origem. Nenhuma mineração semântica nem parser Markdown genérico expansível.
Preservar cada parágrafo, item, heading, célula e literal na ordem original.
Testes usam os dois renderers reais para demonstrar cobertura da gramática, sem
chamá-los durante exportação e sem duplicar regras de negócio.

## 16. Tabelas, tokens longos e quebras de página

Largura fixa de tabela 170 mm; colunas de igual largura útil descontando padding,
distribuição do resto de arredondamento da esquerda para a direita. Alinhamento
esquerdo/topo; nenhuma altura fixa de linha, ellipsis ou clipping. Quebrar texto
em espaços; se um token exceder coluna, quebrar entre sequências base+diacríticos,
sem hífen inserido ou caractere removido. IDs, policies e ponteiros não autorizam
consulta, expansão ou exibição de valor adicional. Sem hifenização por dicionário.

Repetir header de tabela em cada página; dividir tabela somente entre linhas
lógicas. Linha inteira deve caber numa página vazia com header repetido. Se não
couber, falhar UNSUPPORTED_LAYOUT; não cortar a linha, reduzir fonte ou mudar para
outro renderer. Token/glifo que não caiba na largura mínima também falha. Esse
limite de layout é explícito, não omissão de célula ou invalidade técnica da fonte.

Título/TOC e corpo seguem seção 14. H2/H3 ficam com pelo menos duas linhas do
próximo bloco, ou header mais primeira linha de tabela. Parágrafos conservam
ao menos duas linhas em cada lado de quebra, exceto parágrafo inteiro de uma
linha. Avisos curtos ficam íntegros; avisos longos seguem regra de parágrafo sem
sumir. Demais seções fluem sem forçar página individual. Não há captions/annex
pages importadas em v1. Nenhuma página em branco automática entre seções.

## 17. Visuais e marca gráfica

Decisão: não embutir nenhum VISUAL_EXHIBIT em qualquer PDF. JPEG/PNG permanecem
anexos contextuais separados exclusivamente no pacote 8B1; não ler pixels/EXIF,
orientar, reencodar, criar thumbnails, OCR ou associar imagem a finding.
Legendas/approval booleans não migram do índice para PDF. O aviso existente
`Legenda contextual fornecida pelo operador — não constitui finding técnico.`
permanece no índice original, sem alteração. Exibir imagens exigiria contrato
posterior de exposição e layout. Sem logo aprovado: somente tipografia, sem
asset decorativo, brasão, selo, badge ou insígnia externa.

## 18. Metadata PDF, XMP e IDs

PDF comum versão 1.4, sem atualização incremental; toda metadata em allowlist:

| Campo | Valor / decisão |
| --- | --- |
| Title | Título exato H1 do documento de origem. |
| Subject | `Apresentação técnica de artefato aprovado; sem nova análise.` |
| Author | Ausente; não inventar pessoa ou organização autora. |
| Creator | `Digital Evidence Engine dossier.pdf_export/1.0.0` |
| Producer | Mesmo valor fixo de Creator; não aceitar default com detalhes do host. |
| CreationDate / ModDate | Ausentes. Defaults de relógio ou data fixa do renderer devem ser desabilitados/removidos de forma determinística e validados. |
| Keywords | Ausente. |
| Catalog Lang | `pt-BR`. |
| Trailer ID | Ausente em v1 sem criptografia/PDF-A; não usar hash de evidência, UUID ou relógio como ID. |
| XMP / Metadata streams | Ausentes, inclusive em objetos aninhados. |

Não usar issued_date como tempo de aquisição ou geração. Não acrescentar campos
livres/ocultos, histórico de aplicativo, usuário, paths, comentários diagnósticos
ou revision history. Se a release escolhida não puder emitir estas ausências,
o gate A falha; não inventar fallback de data/ID. pypdf é validador, não etapa
genérica de reparo ou sanitização silenciosa do output do renderer.

## 19. Segurança, PDF/A e assinaturas

Proibir JavaScript/JS, OpenAction/AA, URI/GoToR/Launch, recursos remotos,
embedded files/Filespec/AF/EmbeddedFiles, anexos de qualquer tipo, forms/AcroForm/XFA,
multimídia, ações automáticas, execução, criptografia/Encrypt e assinaturas.
Permitir somente destinos/ações GoTo internos gerados pelo produto. Nenhum asset
de Markdown é aberto. Nenhuma imagem ou fonte vem de pacote de caso ou rede.

**NO PDF/A COMPLIANCE CLAIM.** PDF/A não foi selecionado; finalidade de revisão
humana não implica requisito de arquivamento certificado. Também não denominar
saída como archival PDF para insinuar conformidade. Assinatura/certificação,
inclusive placeholders visuais que pareçam assinatura efetiva, fora de escopo.

## 20. Acessibilidade e preservação textual

**NO PDF/UA COMPLIANCE CLAIM.** PDF marcado/tagged universalmente acessível não
é promessa v1. Exigir texto selecionável, pesquisável e extraível para todo o
conteúdo, incluindo tabelas/literais/TOC; proibir rasterização de páginas/texto.
Embed de fontes/ToUnicode, pt-BR, ordem de leitura título → TOC → seções, tabelas
por linha e célula, outlines e contraste da seção 12 são gates verificáveis.
Não há imagens que exijam alt text. Registrar a limitação de ausência de
certificação PDF/UA; extração bem-sucedida não demonstra verdade semântica nem
garante a experiência de todo leitor assistivo.

## 21. Validação somente leitura do pacote fonte

Antes do render, exigir directory-v1 conforme metadata e manifesto 1.0.0, os três
arquivos gerados obrigatórios, relatório canônico no path exato, snapshots e
demais itens coerentes com metadata, paths/roles/classes/labels do ADR 0037.
Validar JSON estrito, chaves únicas, tipos, campos e serialização contratados,
budgets e ausência de colisões. Não inferir sucesso anterior pela mera extensão.

Enumerar somente a raiz explicitamente fornecida, sem seguir links: conjunto
de arquivos exato do manifesto mais manifesto/sums, diretórios apenas ancestrais
necessários; nenhuma entry ausente, duplicata, extra ou diretório vazio extra.
Verificar SHA/tamanho reais de todos os payloads; sums deve cobrir exatamente
payloads mais manifesto, no formato/ordem do ADR 0037, sem cobrir a si próprio.
Rejeitar symlink/junction/reparse, hardlink, não regular, ADS, traversal, UNC,
network paths, aliases e paths de áreas proibidas antes de open, como em 8B1.
Não abrir arquivo extra inesperado para descobrir sua natureza.

Validar compatibilidade estrutural da metadata com o manifesto, não regenerar
report/snapshots/modelo, fazer decode de imagens ou interpretar suplementos.
Leitura desses payloads é somente hash limitado. O estado interno íntegro do
pacote não prova autenticidade externa ou que não existam outras janelas.

## 22. Captura estável e mutação concorrente

Capturar baselines da árvore/arquivos antes da leitura, com primitives Foundation:
identidade path/handle, tipo, size/mtime, ctime POSIX, regras Windows W1 e permissões
observáveis. Reter somente os dois Markdown e documentos de integridade/metadata
limitados; hash streaming dos demais. Renderizar só bytes capturados que passaram
integridade, nunca reabrir fonte de narrativa durante render.

Antes de publicar, repetir árvore, identidades, tamanhos e hashes de todos os
arquivos, inclusive manifesto/sums, contra a captura inicial; mudança falha
INPUT_CHANGED. Revalidar diretórios e origem após esse percurso. Não restaurar
metadata/permissões da origem nem prometer atime invariável. Não há snapshot
global atômico ou proteção contra administrador host malicioso. Revalidações
limitam detecção observável; não provam imutabilidade futura.

## 23. Integridade da saída PDF separada

Manifesto novo: `dossier.pdf_export_manifest/1.0.0`, sem estender o manifesto 8B1.
Objeto JSON de campos exatos:

- policy_id e policy_version com os valores acima;
- export_policy_id=`dossier.pdf_export`, export_policy_version=`1.0.0`,
  delivery_profile=`pdf-presentation-v1`;
- render_environment_id conforme seção 9;
- source_package: objeto somente com manifest_sha256 e sha256sums_sha256,
  hashes dos bytes capturados dos dois arquivos de integridade originais;
- entries: exatamente duas entradas, ordenadas por package_path ASCII.

Cada entry contém apenas package_path, source_package_path, source_byte_size,
source_sha256, byte_size, sha256 e page_count. Paths são exatamente os da seção 4;
tamanhos int exato >=0, page_count int >0 (nunca bool), hashes 64 hex minúsculos.
SHA do Markdown vincula bytes, não texto normalizado. Nenhum label, filename do
host, case_reference, issued_date ou dado pessoal adicional nesse manifesto.

Serialização igual à convenção 8B1: JSON ensure_ascii/sort_keys, separadores
compactos, allow_nan=False, UTF-8 sem BOM e LF final único. Manifesto cobre ambos
PDFs. SHA256SUMS cobre ambos PDFs mais pdf-export-manifest.json, exclui a si,
ordena paths ASCII, linhas `<sha256><dois espaços><path relativo POSIX><LF>`.
Sequência acíclica: PDFs validados → manifesto → sums. Rehash dos quatro arquivos
e conferência da árvore exata antes da publicação. Hashes técnicos não migram
para corpo, chrome ou metadata PDF. Nada escreve integridade na origem 8B1.

## 24. Staging, publicação e arquivos temporários

Input/output não podem conter um ao outro ou ser aliases; pai do destino existe,
é seguro e local, destino ausente. Staging exclusivo irmão no mesmo filesystem,
ownership/identidade conferidos, permissões restritas. Material temporário é
sensível, somente em scratch dentro desse staging; nunca Git, cache global ou
diretório reutilizado. Não há HTML/CSS intermediário. Remover scratch comprovadamente
próprio antes de conferir os quatro arquivos finais, sem omitir gate por falha.

Fases: preflight → captura/verificação fonte → gramática/fontes → render isolado →
validação independente → integridade saída → revalidação fonte/saída/staging →
fsync/diretórios → único rename sem substituição. Reusar/adaptar primitives
testadas de packaging, sem expor suas suposições específicas de seleção como API
genérica acidental. Em Linux renameat2(RENAME_NOREPLACE); não usar replace ou merge.
Windows hospeda Linux canônico; filesystem do bind mount deve demonstrar a
garantia de no-replace, caso contrário PUBLICATION_FAILURE, sem fallback.

Destino criado em corrida é preservado. Falha limpa só staging cuja posse seja
comprovada; falha de limpeza tem precedência STAGING_FAILURE. Nunca apagar input,
preexistentes ou resultado já publicado. Nada é lido/escrito após confirmação
do rename. Confirmação ambígua exige inspeção externa; sem retry/rollback automático.
Não prometer durabilidade frente a queda de energia ou transação com stdout.

## 25. CLI futura

```console
dee dossier pdf --input-package <directory-v1> --output-dir <new-presentation-directory>
```

Exatamente duas opções obrigatórias, únicas, paths explícitos locais. Sem seleção
nova, flags de renderer/fontes/limites, force, overwrite, stdout binary, stdin,
URL, --case-root, DB ou configuração ambiental de caso. O comando fixa
dossier.pdf_export/1.0.0 e pdf-presentation-v1; outra versão exigirá revisão explícita.
Somente opera dentro do ambiente canônico validado; execução nativa fora dele
falha ENVIRONMENT_UNSUPPORTED, não baixa/lança container automaticamente.

Operador Windows/Linux inicia imagem aprovada offline, montando exclusivamente
pacote de entrega somente leitura e pai de saída, jamais /case ou diretórios de
caso. Paths internos explícitos não são metadata do documento. Wrapper/launcher
automático de Docker não está autorizado nesta versão.

Sucesso: exit 0, somente `DOSSIER_PDF_OK` + LF em stdout, após publicação.
Falha/sintaxe: exit 2, `ERROR: DOSSIER_PDF_<CODE>` + LF em stderr, sem sucesso
parcial. Bytes ASCII/LF inclusive em host Windows. Help não processa dados.

## 26. API e fronteiras de módulos propostas

| Módulo | Entrada / saída / fronteira |
| --- | --- |
| dossier/pdf_model.py | Bytes de um dos dois Markdown → DTO imutável de apresentação/fluxo textual esperado, por gramática limitada; sem filesystem ou fatos novos. |
| dossier/pdf_renderer.py | DTO, estilos/fontes verificados e ambiente fixo → PDF limitado; sem paths de pacote, modelo canônico ou consultas. |
| dossier/pdf_validation.py | Bytes PDF + DTO esperado → resultado estrutural/textual/page_count ou erro; pypdf independente do backend. |
| dossier/pdf_package.py | Leitor somente leitura de directory-v1, captura/recheck, manifesto/sums PDF e completude; reusa primitives seguras, não finalize_integrity sobre origem. |
| dossier/pdf_service.py | export_dossier_pdf(input_package: Path, output_dir: Path) → DTO imutável de resultado após publicação; orquestra fases/worker/budgets. |
| cli/dossier.py | Adaptador estreito `pdf`, sanitização e exits. assemble permanece igual. |

Imports permitidos limitam-se a stdlib, errors, primitives Foundation/packaging
compatíveis e toolchain aprovada. Model/renderer/validator não importam storage,
ORM, case discovery, ingest services, parsers, queries, correlação ou rede.
Constantes puras de títulos/seções podem ser compartilhadas sem executar modelagem.
Testar grafo nominal/transitivo e sentinelas de execução, distinguindo imports
legados do agregador CLI da ausência de execução DB/rede no comando PDF.

## 27. Budgets operacionais e isolamento

Valores propostos explícitos, sujeitos a revisão humana, sem flags para burlá-los.
Não redefinem validade de directory-v1 nem máximo semântico de janelas/seções.
MiB = 1024 × 1024 bytes.

| Recurso | Limite e ponto de enforcement |
| --- | --- |
| Fonte completa | 1 GiB, 261 arquivos (256 selecionados + 5 gerados), como envelope operacional 8B1; contar durante enumeração/hash. |
| Cada Markdown fonte / total dos dois | 64 MiB / 128 MiB, antes de decode e durante leitura. |
| Cada documento JSON/sums administrativo fonte | 64 MiB; JSON depth 64, 1000000 nós, lexema numérico 128 caracteres, hooks estritos antes de modelo. |
| Blocos de apresentação | 200000 por documento, durante parse; sem recursão ilimitada. |
| Tabelas | 16 colunas, 100000 linhas e 1000000 células acumuladas por documento; contar antes de layout. |
| Página | 1000 por PDF, contando TOC; interromper ao tentar página 1001. |
| Imagens embutidas / pixels / bytes | Zero em todos os três budgets; fonte de imagem não é aberta pelo render. |
| PDF individual / soma | 64 MiB / 128 MiB, writer limitado durante geração, não só após alocar tudo. |
| Manifesto/sums novos | 1 MiB cada; total da saída no máximo 130 MiB. |
| Tempo | 120 s por render; 120 s por validação PDF; 600 s para operação completa antes da publicação. |
| Memória | Worker canônico limitado a 1 GiB de espaço de endereçamento via RLIMIT_AS; container a 2 GiB, swap adicional desabilitada. Incapacidade de impor limites falha antes de processar. |
| Processos / CPU | Container pids-limit 64, 2 CPUs; um documento/worker de cada vez, sem paralelismo de render. |
| Scratch | 256 MiB totais sob staging, contabilizados durante escrita; sem spool global. |

Worker Python subprocess isolado, mesmo sendo renderer de biblioteca: stdin/IPC
limitado aos DTOs, cwd em scratch próprio, rede desabilitada no container,
filesystem base read-only, pacote apenas ro, escrita somente no staging, usuário
sem privilégios, capabilities removidas. Ambiente allowlist da seção 9 e paths
fixos de runtime/scratch, sem herdar variáveis de caso/credenciais. Sem browser,
shell de comandos ou resolução de assets. Parser também executa sob budget.

Capturar stdout/stderr em buffers de até 64 KiB cada; excesso falha RESOURCE_LIMIT,
nunca repassar payload/paths ao operador. Timeout cancela e encerra worker/grupo,
fecha handles e limpa apenas scratch próprio. Sem retry ou fallback. Tempo/memória
são proteção operacional, não limites probatórios nem promessa de conclusão em
todo host; carga do host pode causar falha segura. OOM/timeout não é sucesso parcial.

## 28. Erros e diagnóstico

Prefixo público DOSSIER_PDF_; allowlist de códigos, nunca str(exception), comando
interno, stderr cru, texto de documento, path, host, label, identificador ou hash.

| Código | Condição |
| --- | --- |
| ENVIRONMENT_UNSUPPORTED | Receita/versão/plataforma/isolation indisponível ou divergente. |
| FONT_UNSUPPORTED | Fonte, estilo, glifo ou shaping/extração necessários indisponíveis. |
| INVALID_PACKAGE | Profile/schema/path/tipo/árvore fonte estruturalmente inválidos ou ilegíveis. |
| INTEGRITY_MISMATCH | Bytes, tamanho ou cobertura do manifesto/sums divergentes. |
| INPUT_CHANGED | Mudança observada em fonte durante captura/recheck. |
| UNSUPPORTED_MARKDOWN | Gramática/títulos/estrutura de apresentação não contratados. |
| UNSUPPORTED_LAYOUT | Conteúdo indivisível não cabe sem violar legibilidade/completude. |
| RENDER_FAILURE | Renderer/passagens de paginação falham dentro dos budgets. |
| PDF_VALIDATION_FAILURE | Parser independente, conteúdo, metadata ou segurança falham. |
| RESOURCE_LIMIT | Bytes/nós/páginas/tempo/memória/scratch ou diagnóstico excedem budget. |
| OUTPUT_EXISTS | Destino preexistente ou criado em corrida. |
| STAGING_FAILURE | Escrita/flush/ownership/cleanup não concluídos com segurança. |
| PUBLICATION_FAILURE | Move sem substituição indisponível, falho ou confirmação ambígua. |
| INTERNAL_ERROR | Invariante inesperada, sanitizada. |

Primeira falha pela ordem das fases, documentos por package_path ASCII. Falha de
cleanup prevalece, com no máximo categoria original segura adicional em resultado
interno; CLI mantém uma única linha contratada. Sem logs de payload por padrão.

## 29. Validação independente pós-render

pypdf deve abrir documento inteiro em modo estrito sob budgets; não basta `%PDF-`
ou exit 0. Validar header/EOF, uma única revisão/xref coerente, todos os objetos
e streams referenciados, ausência de bytes extras/anexos, page tree íntegra,
1–1000 páginas, MediaBox/CropBox A4 com tolerância 0,01 pt, Rotate=0 e tamanho.
Warnings de reparo/recovery ou estruturas desconhecidas do perfil falham.
Qualificar em A quais verificações requerem inspeção explícita além do parser;
não alegar que `strict=True` sozinho satisfaz essas condições.

Percorrer grafo de objetos alcançáveis com limites; verificar allowlist de
metadata, ausência de XMP/IDs/datas e estruturas proibidas da seção 19, fontes
embutidas/ToUnicode, outlines/destinos, apenas annotations GoTo internas esperadas.
Proibir objetos órfãos/updates usados para esconder conteúdo; controlar bytes
emitidos pelo renderer e conferir estrutura independente, sem sanitizar PDF.

Comparar extração por bloco/página/célula com fluxo textual esperado do DTO, na
ordem, incluindo conteúdo e repetições. Remover da comparação somente chrome,
TOC e headers de tabela repetidos nas posições previstas; não por substituição
global de strings. Normalização para comparação limita-se a separadores de layout
(espaço/quebra de linha); não case-fold/NFC ou remoção de pontuação/dígitos.
Quebra visual de token longo deve recompor exatamente os mesmos code points.
Exigir todos os 14/20 H2, H3, parágrafos, itens, células e literais, não só headings.
Não ignorar bloco que o extrator não entenda: falhar. Isso verifica preservação
de apresentação, não analisa verdade ou reconstitui modelo de findings.

## 30. Regressão visual e golden policy

Fixtures inteiramente sintéticas renderizadas em ambiente canônico. PDFium
fixado rasteriza a 144 dpi, RGB com fundo branco, uma página por vez, sem OCR
ou reconhecimento de objetos. Fingerprints de pixels decodificados, dimensões
e caixas de layout; não depender de metadata/encoder PNG para comparar.

Testar margens, ausência de clipping/sobreposição corpo/chrome, células completas,
headers repetidos, headings não órfãos, glifos e páginas não vazias. Layout trace
do renderer só é diagnóstico de teste, não prova independente suficiente:
combinar extração pypdf, rasterização e inspeção humana de previews sintéticos.
Rasters não demonstram ausência universal de defeitos ou verdade de conteúdo.

Não commitar goldens PDF/PNG binários em v1. Guardar fixture textual sintética,
hashes esperados dos PDFs, extração estrutural e fingerprints de páginas da
receita fixada. Previews temporários fora do Git, apagados com ownership. Mudança
de golden exige revisar diffs estruturais/visuais e receita, nunca atualizar
automaticamente para acomodar falha.

## 31. Matriz mínima de testes sintéticos

| Área | Casos e resultado exigido |
| --- | --- |
| Origem | Pacote mínimo; completo com 21 snapshots; 14/20 seções preservadas; não executar serviços de caso/modelagem. |
| Gramática | Ambos renderers atuais; H3/listas/bold/code/escapes/entidades/pipe; strings escapadas permanecem literais; HTML/link/image/script desconhecido falha; CRLF em fonte gerada falha, suplemento CRLF não alimenta PDF. |
| Layout | Dossiê longo, oito colunas, tabela multipágina com header repetido, linhas no limiar, célula maior que página falha, token longo recomposto sem perda, mínimos de fonte. |
| Unicode | Acentos pt-BR/travessão/seta/sinais/combinações; fonte/estilo faltante, glifo ausente e shaping não suportado falham, sem tofu/fallback. |
| Paginação | H2/H3 no fim de página, viúvas/órfãs, avisos, título/TOC de uma ou duas páginas sem blank page, bookmarks e destinos ordenados, footer correto. |
| Metadata | Campos exatos, datas/IDs/XMP ausentes, clock/user/path sentinela não vaza, língua pt-BR. |
| Integridade fonte | Extra/ausente/duplicata, JSON não estrito, profile errado, sums errado, tamanho/hash inválidos, link/junction/hardlink/escape; jamais abrir alvo externo. |
| Mutação | Troca path/handle, alteração durante captura e render/recheck; falha preserva origem/destino de terceiros; não alegar atomicidade global. |
| Saída | Quatro paths exatos, dois PDFs validados, vínculo aos dois MD e manifesto/sums originais, hashes acíclicos, nenhum scratch ou input copiado. |
| Publicação | Destino existente/corrida, rename indisponível, write/fsync/worker/cleanup failure, ownership perdido, confirmação ambígua, zero I/O após sucesso. |
| Recursos | Limites N/N+1 para bytes/nós/células/páginas/output, timeout/OOM/stdout/stderr excessivo, worker encerrado, ausência de saída parcial/retry. |
| Segurança PDF | Parser truncado/corrompido, active content/attachment/URI/Launch/form/encryption/XMP oculto injetados sinteticamente devem falhar. Não aceitar só magic/header. |
| Preservação | Extração completa, glifo/palavra/célula removida ou trocada/duplicada detectada; sequência lógica e pontuação preservadas; sem rasterizar texto. |
| Privacidade | Sentinelas só em snapshots/suplementos/captions/paths/ambiente nunca surgem em PDF/chrome/metadata/log; alteração desses payloads não muda PDFs se MD iguais. |
| Determinismo | Repetir bytes idênticos em roots/clocks/enumeração diferentes, SHA integral; render_environment_id divergente falha. |
| Regressão 8B1 | assemble e fingerprint completo anterior byte-idênticos; pacote sem PDF permanece válido; zero dependência de PDF para montar 8B1. |

## 32. Paridade, operação offline e privacidade

Executar testes de invocação da mesma imagem Linux/amd64 em hosts Windows/Linux,
comparar ambos PDFs e quatro arquivos de saída. Confirmar limites/mounts/no-replace
em cada filesystem utilizado. Não chamar isso de render nativo Windows. Sem imagem
disponível localmente, falhar; nenhuma chamada implícita de download/build.

Runtime sem web fonts/CDN/CSS/imagens remotas, navegação, analytics, telemetria,
upload/cloud/API/LLM. Não montar /case ou árvores de evidência. Nenhum hostname,
data atual, username, path de origem, cookie/token, mensagem, IP/device ID/email/
telefone ou SHA é acrescentado à apresentação. Conteúdo já aprovado nos Markdown
é preservado; não anunciar sanitização/anonymização universal. Vínculos SHA
exclusivamente técnicos no manifesto novo. Revisão humana de exposição continua
necessária, inclusive texto selecionável/metadata/objetos ocultos do PDF.

## 33. Sequência de implementação após aceitação

| Slice | Entrada → saída / testes / exclusão / checkpoint humano |
| --- | --- |
| 8B2-A — fundação | ADR aceito + aprovação de dependências → receita fixada, bundle licenciado, DTO/gramática e qualificação mínima da toolchain. Testar metadata/ID/fontes/ToUnicode/outlines/parser/limites. Sem CLI/pacote real. Revisão dos pins, licenças e provas antes de B; parar se inviável. |
| 8B2-B — dossiê | Markdown sintético 8B1 → dossier.pdf em memória/staging de teste; 14 seções, TOC, fontes e extração. Sem snapshots, visuais ou publicação. Revisão humana de layout/privacidade. |
| 8B2-C — consolidado | Markdown sintético canônico → segundo PDF, 20 seções, H3/listas/bold/literais/tabelas; testes completos de layout e perda textual. Sem reconstruir report. Revisão conjunta dos dois documentos. |
| 8B2-D — vínculo técnico | Pacote sintético directory-v1 → captura/verificação read-only e manifesto/sums do perfil separado; corrupção/mutação/acyclicidade. Sem CLI/publicação final. Revisão de fronteiras e compatibilidade 8B1. |
| 8B2-E — serviço/CLI | Fluxo anterior → quatro arquivos publicados uma vez, comando estreito e worker isolado; falhas, budgets, no-replace/cleanup/diagnóstico. Sem descoberta/build automático. Revisão adversarial antes de fechamento. |
| 8B2-F — apresentação | Casos sintéticos extremos → validação textual/estrutural/raster e fingerprints aprovados. Sem OCR/goldens reais; sem mudança de narrativa. Revisão visual humana de todas as páginas dos cenários de referência. |
| 8B2-G — fechamento | Receita/pipeline fixos → gates repetidos Windows-host/Linux-host, hashes/limites/privacidade e regressões pytest/Ruff/mypy futuras. Sem execução real. Revisão humana final, sem promoção automática a entrega jurídica. |

Cada slice é revisável separadamente, não autoriza concluir todos sem os
checkpoints definidos. Nenhum foi iniciado por este documento. Falhas de
qualificação pedem revisão da proposta, nunca ampliar escopo ou instalar
dependência adicional implicitamente.

## 34. Consequências, revisão humana e fronteira 8B3

Saída separada preserva a imutabilidade 8B1 e exige guardar conjuntamente seu
vínculo técnico para entrega futura. Ambiente único reduz variabilidade, mas
adiciona build/fontes/licenças e Docker para Windows. Gramática fechada e falha
em overflow/glifo protegem completude, podendo recusar apresentação de pacote
tecnicamente válido. Sem render nativo Windows, PDF/A, PDF/UA, visuais ou assinatura
nesta primeira versão. Não esconder esses limites com fallback/truncamento.

Revisão humana do ADR precede implementação; pins/licenças e qualificação precedem
dependências/avanço de A. Antes de qualquer entrega, revisar layout, privacidade,
texto/captions e exposições contextuais no pacote separado, além da apresentação
voltada à leitura jurídica. Aprovação técnica de PDF não codifica aprovação
jurídica. 8B3 permanece futura para execução real controlada e eventual vínculo
de entrega; este ADR não autoriza abrir artefatos reais, gerar PDFs de caso,
transportar, assinar, arquivar ZIP ou declarar certificação.

## 35. Validação documental da proposta e da promoção

Na criação original da proposta 8B2.0, somente este ADR foi criado, com status
Proposed. Nenhum código, teste, fixture, schema, dependência, lockfile, Dockerfile,
ADR aceito ou documento de promoção foi modificado. Não houve geração de PDF
ou execução de caso real.

Na promoção posterior à revisão humana, este ADR passou a Accepted; AGENTS.md,
README.md e docs/architecture.md foram atualizados somente para registrar o
status aceito e o roadmap atual. Nenhum código de produto, teste, dependência,
lockfile ou Dockerfile mudou. Nenhum PDF foi gerado ou validado, e nenhum caso
real ou artefato de caso foi acessado.

Ambas as etapas foram exclusivamente documentais, sem acesso a CASE_ROOT, DB
ou originais; sem rede, instalação, execução do renderer, stage, commit ou push.
Revisão de diff/whitespace/status e privacidade foram os gates documentais.
Pytest, Ruff e mypy não foram reexecutados; os gates funcionais permanecem os
anteriormente aceitos de 8B1-G, sem alegação de testes PDF.
