# Milestone 8B2-A — PDF Toolchain Qualification & Foundation

Estado: COMPLETE — HUMAN REVIEW APPROVED. Qualificação sintética sob
[ADR 0038 Accepted](adr/0038-human-pdf-export-contract.md) e
[ADR 0039 Accepted](adr/0039-controlled-reportlab-adapter-private-coupling.md),
sem alterar suas decisões. A extensão 8B2-B foi implementada e qualificada
sinteticamente: COMPLETE — HUMAN REVIEW APPROVED; ver seu fechamento abaixo.
8B2-C: COMPLETE — HUMAN REVIEW APPROVED, qualificação sintética registrada abaixo.
8B2-D: COMPLETE — HUMAN REVIEW APPROVED, captura/binding/integridade qualificados abaixo.
8B2-E: COMPLETE — HUMAN REVIEW APPROVED; fechamento sintético e gates abaixo.
8B2-F: COMPLETE — HUMAN REVIEW APPROVED; qualificação test-only e fechamento abaixo.
8B2-G concluiu o fechamento sintético de integração. A série 8B3 posterior preserva
dados e artefatos de caso fora do Git; este documento registra somente contratos,
limites, inventários e evidência de qualificação apropriada ao repositório.

Revisão técnica humana final: PASS. Foram verificados o inventário do ambiente
canônico, o render_environment_id, o escopo do adaptador controlado ReportLab,
a documentação de qualificação e os gates finais.

## Retomada e endurecimentos finais

A execução interrompida por quota foi concluída pelo operador: **1964 passed,
3 skipped, 1967 collected, 229.67 s**, exit 0. Esse gate anterior é PASS.
A implementação existente foi preservada, sem reset/recriação. O fechamento
acrescentou dois endurecimentos e repetiu os gates sobre o estado resultante:

- Toda distribuição Python tem seus `License-File` declarados resolvidos no
  diretório de metadata instalado: `dist-info/licenses/` para metadata 2.4+;
  `dist-info/` para metadata anterior. Payload ausente falha fechado, sem busca
  por basename. A heurística LICENSE/COPYING/COPYRIGHT/NOTICE permanece adicional.
  Bytes originais são preservados; destino repetido com bytes iguais é idempotente,
  com bytes diferentes falha. PDFium exige 19 declarações distintas e os 19 payloads.
- O inventário mantém os seis `src/evidence_engine/dossier/pdf_*.py` e acrescenta
  uma lista explícita: `src/evidence_engine/errors.py` (tipo de erro importado),
  `src/evidence_engine/__init__.py` e `src/evidence_engine/dossier/__init__.py`
  (executados na importação). Sem scanner recursivo ou hashing de todo `src/`.
  Os módulos de suporte não foram alterados.

Os 29 testes novos usam somente fontes/distribuições temporárias sintéticas;
cobrem declarações modernas/legadas, ausência, heurística, 19 licenças, colisões,
bytes, ordem, paths relativos e alteração do ID para cada módulo coberto.
Não modificam fontes reais do projeto.

## Ambiente e artefatos qualificados

Render canônico: Linux/amd64 (x86_64), Python **3.12.14**, uv **0.8.22**.
Imagem: `digital-evidence-engine:pdf-foundation`, receita `Dockerfile.pdf`.
Base fixada:

```text
python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
```

Imagem da segunda construção limpa:
`sha256:083985e367d602c315239c05f213d87e5cca69e509cbfbd32080d43793bdbe5a`.
O ID Docker das camadas não é promessa de build binariamente reproduzível;
o inventário canônico foi idêntico byte a byte nas duas construções,
incluindo a segunda com `--no-cache`.

Artefatos exatos em [pdf-qualified-inputs.json](../tools/pdf-qualified-inputs.json);
downloads somente no build, conferidos por SHA-256 e comparados com os payloads
instalados (executável uv em wheel .data é identificado pelo hash do wheel).

| Distribuição | Artefato | SHA-256 |
| --- | --- | --- |
| ReportLab 5.0.1 | reportlab-5.0.1-py3-none-any.whl | `1c36e6bb0e71780c72331eba60da7f602e8d4389a8723825af71342e49d791e8` |
| pypdf 6.19.0 | pypdf-6.19.0-py3-none-any.whl | `7e5d6e730e7dae87d560a2cee218b852f6498c8be61966f3cd02ead971e48d14` |
| pypdfium2 5.13.0 | pypdfium2-5.13.0-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl | `81df25c1ab4c13ff773102d3cbea1967511d079123b067fc077bd0c4d57d91d8` |
| Pillow 12.3.0, já existente | pillow-12.3.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl | `78cb2c6865a35ab8ff8b75fd122f6033b92a62c82801110e48ddd6c936a45d91` |
| charset-normalizer 3.5.1 | charset_normalizer-3.5.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl | `b9af956078716df40d985fb0dfeb2c2120c5ca92ba4ff4b388acfd01cdc14d08` |
| uv 0.8.22 | uv-0.8.22-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl | `8efec4ef5acddc35f0867998c44e0b15fc4dace1e4c26d01443871a2fbb04bf6` |

Lockfile revisado semanticamente contra HEAD: adições diretas ReportLab/pypdf,
pypdfium2 somente dev; única adição transitiva charset-normalizer. Nenhum pacote
anterior atualizado/removido; somente referências do projeto mudaram além das
quatro novas entradas. Sem instalação de Python nativo Windows nesta etapa.

## Licenças preservadas

Qualificação técnica de materiais, não parecer jurídico. Decisão humana existente:
**PDFIUM LICENSE ARTIFACT REVIEW: PASS**, para o wheel exato acima, PDFium
**153.0.7999.0** e seus **19 License-File** completos. O artefato não mudou;
a ambiguidade de recursos de teste REUSE já revista não foi reaberta.

A imagem preserva **204 payloads** em `/opt/digital-evidence-engine/licenses/`,
com hashes em [pdf-render-environment.json](pdf-render-environment.json):

| Origem | Payloads |
| --- | ---: |
| Distribuições Python | 96 |
| Desses, pypdfium2 | 19 |
| Fontes: copyrights dos três pacotes Debian | 3 |
| Copyrights dos 87 pacotes do sistema | 87 |
| Licenças comuns Debian | 17 |
| Licença do runtime Python | 1 |
| Total (PDFium já incluído em Python) | 204 |

A verificação final conferiu 78 declarações License-File na imagem instalada,
sem ausências ou colisões. O único payload adicional frente aos 203 anteriores é
`python/pip/pip-25.0.1.dist-info/AUTHORS.txt` (lista de atribuição, 11018 bytes),
SHA-256 `1eace90552df4f5941b61a907e20e555e16483ae6127b650bef5a1a2af8102c0`.
A metadata de pip 25.0.1 declara MIT e LICENSE.txt/AUTHORS.txt; ambos preservados.
Nenhum payload anterior mudou e nenhuma nova ambiguidade de licença ficou pendente.
ReportLab mantém sua licença BSD; pypdf BSD-3-Clause; charset-normalizer MIT.
Materiais completos das demais distribuições e do sistema permanecem no inventário,
incluindo licenças transitivas e textos/atribuições, sem normalização ou síntese.

## Fontes e texto

Estratégia B: seis arquivos DejaVu **2.37-8** empacotados na imagem, extraídos dos
pacotes Debian core/extra/mono fixados por SHA-256 no arquivo de inputs. Origem:
`https://deb.debian.org/debian/pool/main/f/fonts-dejavu/`. Sem descoberta de fontes
do host, fallback ou instalação apt adicional. Os três copyrights originais e
licenças comuns são preservados: Bitstream Vera, alterações DejaVu em domínio
público e termos de empacotamento Debian, inclusive GPL-2+.

| Arquivo | SHA-256 |
| --- | --- |
| DejaVuSans.ttf | `57f73e11f51999432bf7ab22ce55b6f945d5eca1bf824404cfa9ec2e3718c84e` |
| DejaVuSans-Bold.ttf | `a4c5bc453ca281d90ea079e596da7ae0dfeb5777497c29ec254e76d97ff6f890` |
| DejaVuSans-Oblique.ttf | `e2f09289f4276309a36b9a93e5a0ac64957ef3eb7158151b243d41f667151ee4` |
| DejaVuSans-BoldOblique.ttf | `c35383d5e56add5cc9cdc9f4e4a899f9e540f7c7e49f1901074c2d03af194eff` |
| DejaVuSansMono.ttf | `54bf827eb99404e8f430c330ad30f063334f637eba0109b6a18d4f566a8e9dd8` |
| DejaVuSansMono-Bold.ttf | `0d3c03d1b667192f91223660a3163325cf83132662fe4d9f7d6e596bf7a995c2` |

Embedding TrueType, ToUnicode e extração de acentos/sinais do probe: PASS.
Glifo ausente, combining não qualificado, controles e bidi falham fechado:
`DOSSIER_PDF_FONT_UNSUPPORTED`. Subsets reproduzidos nos renders independentes
e A/B/A. Isso qualifica o repertório sintético exercitado, não shaping universal.

## Adaptador controlado e validação

Superfície privada usada, estritamente a do ADR 0039:
`Canvas._doc`, `PDFDocument.info`, `PDFInfo`, `PDFDocument`,
`PDFDocument.ID`, `PDFDictionary`, `PDFString` e comportamento de
`PDFTrailer.__init__`. O Canvas original executa integralmente; descriptor
intercepta somente a primeira atribuição de _doc, antes do uso dependente.
ContractInfo emite a allowlist; ContractDocument.ID retorna None. Serialização
central e PDFDocument.format permanecem herdados. Guardas de versão 5.0.1,
hashes dos seis métodos revisados, assinaturas e ciclo de vida falham fechadas.

Sem monkeypatch global/de instância, patch do vendor, cópia substancial de
Canvas.__init__, override de PDFDocument.format, superfície privada adicional,
writer/rewrite pypdf ou pós-processamento. pypdf é validador independente read-only.

Probe sintético: **2 páginas A4**, **230822 bytes**, PDF **1.4**, Catalog Lang
**pt-BR**. Info contém exatamente Title/Subject/Creator/Producer.
**Author, Keywords, CreationDate, ModDate, trailer ID e XMP ausentes.**
Validação estrita de objetos/xref/Root/Info/startxref/EOF, ausência de órfãos,
budgets e profile fechado: PASS. Rejeição de metadata extra, estruturas
desconhecidas, ações externas/JavaScript, anexos, formulários, criptografia e
demais conteúdo ativo proibido: PASS. Outlines hierárquicos e destino/link
interno sintético: PASS. Não é ainda validador de qualquer PDF arbitrário.

SHA-256 do PDF (preservado, sem atualização dos goldens):

```text
06fadb2a60e76c78a836ec1e118e3986941a17e803e0e81d727a0b47b59102d8
```

## Determinismo, PDFium e isolamento

Dez processos independentes em diretórios temporários distintos: PDF integral
idêntico. A/B/A no mesmo processo: A reproduzido. Container limpo iniciado e
reiniciado: mesmo PDF/ID; variação de hostname e UID/GID 1001:1001: mesmos bytes.
Render habitual UID/GID 1000:1000. Execuções offline e non-root: PASS.

pypdfium2 5.13.0, PDFium 153.0.7999.0: duas rasterizações independentes, duas
páginas de **1191 × 1684**, **144 DPI**, RGB sobre branco, sem PNG persistido.
SHA-256 dos pixels decodificados, preservados:

```text
page 1: 55f00567696521e8343129534163d19cd02b9bc6d30e9291da7a8f172cc9fcde
page 2: 11c346f985bc3ba2d23792accdeec9ab5a0c33648850ff479a6a30518c898e86
```

PDFium é dependência de desenvolvimento para validação visual; não render de
produção nem alegação de paridade nativa Windows/Linux.

No fechamento de A, inventário: **35 distribuições identificadas**, **6093 hashes de payloads de
pacotes**, 87 pacotes OS, seis fontes, 204 licenças e nove fontes de implementação.
Paths absolutos existentes são somente internos fixos do container; não há paths
do host. JSON canônico UTF-8/LF, chaves ordenadas. ID SHA-256:

```text
afc096a426ccdcafb3e9d0c7be3a0110be7e0c15c8e968daae3c9a05007af8a6
```

O ID anterior `7ad7c1ce086300a7c9aec782e58c26ad580afaf6e6ab5a0a4b1ec5df239e2952`
mudou apenas por licenças e cobertura de implementação. Fontes, artefatos de
renderer, PDF e pixels não mudaram. Código/lógicas cobertos alteram o ID;
arquivos de projeto não relacionados não entram implicitamente.

LANG/LC_ALL=C.UTF-8, TZ=UTC, PYTHONHASHSEED=0, PYTHONDONTWRITEBYTECODE=1.
Runtime com network none, filesystem read-only, tmpfs /tmp 256 MiB,
2 GiB de memória/swap total, 2 CPU, 64 PIDs, capabilities removidas e
no-new-privileges. Worker isolado impõe RLIMIT_AS 1 GiB e CPU 120 s;
excesso de memória foi exercitado sinteticamente. Build com rede exclusivamente
para ferramentas/fontes públicas aprovadas, contexto fechado sem casos.

## Fundação de apresentação e limites

DTOs imutáveis e parser de bytes Markdown estrito, com posições de origem:
headings H1/H2/H3, parágrafos, listas simples, tabelas, spans de texto/literal/
negrito e índice contratual. Preserva escapes/espaços, decodifica entidades
permitidas uma vez e rejeita gramática desconhecida. Compatibilidade com os dois
renderers existentes testada com inputs sintéticos, sem importar serviços de
caso na fundação PDF.

Budgets: Markdown/PDF 64 MiB, 200000 blocos, 16 colunas, 100000 linhas,
1000000 células/objetos e 1000 páginas; profundidade PDF 64. Falhas são códigos
sanitizados, sem captura de arquivos de caso. Paginação de tabelas, TOC e
renderer final não fizeram parte da qualificação original de A; a extensão B segue abaixo.

## Gates finais e reprodução

| Gate | Resultado |
| --- | --- |
| PDF dirigido | 108 coletados, 108 passed, 0 skipped/failed/errors; 52.04 s |
| Regressão 8B1 | 795 coletados, 792 passed, 3 skipped, 0 failed/errors; 46.12 s |
| Pytest completo final | 1996 coletados, 1993 passed, 3 skipped, 0 failed/errors; 243.34 s |
| Ruff check --no-cache . | PASS |
| Ruff format --check --no-cache . | PASS, 193 arquivos |
| mypy --cache-dir=/tmp/dee-mypy src | PASS, 85 arquivos |
| git diff --check | PASS |

Todos os comandos concluíram com exit 0. Os três skips Linux são exclusivamente
Windows: junction real em test_dossier_integrity e test_dossier_paths; publicação
real sem substituição Windows em test_dossier_publication. Não foram dispensados
gates PDF. Os números anteriores 79/1964 não representam o estado final:
os 29 testes adicionados elevam os totais para 108/1993.

As execuções usam o working tree read-only e PYTHONPATH=/app/src. Exemplo
a partir da raiz do checkout em shell POSIX, sem paths de operador:

```sh
docker build --platform linux/amd64 -f Dockerfile.pdf -t digital-evidence-engine:pdf-foundation .
docker run --rm --network none --platform linux/amd64 --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=268435456 \
  --memory 2g --memory-swap 2g --cpus 2 --pids-limit 64 \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,source=$PWD,target=/app,readonly" -e PYTHONPATH=/app/src \
  --entrypoint python digital-evidence-engine:pdf-foundation \
  -m pytest -p no:cacheprovider -rs
```

Conjuntos adicionais no mesmo runtime restrito:
`tests/test_pdf_build.py tests/test_pdf_model.py tests/test_pdf_foundation.py`;
`tests/test_dossier_*.py` expandido pelo shell. Ruff check/format --no-cache,
mypy --cache-dir=/tmp/dee-mypy src. Qualificação CLI interna de teste:
`python -m evidence_engine.dossier.pdf_probe`; isso não é CLI de exportação.

## Fechamento sintético 8B2-B — revisão humana aprovada

8B2-A permanece COMPLETE — HUMAN REVIEW APPROVED. 8B2-B: COMPLETE — HUMAN REVIEW
APPROVED. API `render_dossier_pdf(data: bytes) -> bytes`, exclusivamente para o
Markdown de dossiê já fornecido; não chama montagem, snapshots ou serviços de caso.
Medição e paginação explícitas, comparação de duas passagens antes de emitir,
14 H2 no TOC, raiz/H2 nos outlines, H3 somente no corpo. Tabelas usam 170 mm,
colunas iguais, headers repetidos e linhas lógicas indivisíveis. Layout impossível
falha `DOSSIER_PDF_UNSUPPORTED_LAYOUT`; não há redução de fonte ou truncamento.

O validador relaciona fragmentos/páginas/células ao DTO original, conferindo ordem,
conteúdo, ToUnicode, fonte/tamanho e posições. Chrome, TOC e headers repetidos são
verificados em suas posições, sem remoção global de texto. Separadores inferidos
pelo pypdf antes de operadores de texto são distinguidos de espaços efetivamente
emitidos; trocas de subset na mesma matriz são recompostas sem normalização Unicode.
Texto preto e retângulos de tabela anteriores ao texto possuem perfil fechado.
Metadata, xref, objetos, limites e proibições da fundação permanecem aplicáveis.
O link do índice vira `Índice de anexos (annex-index.md)`, sem anotação de arquivo.

Nenhuma dependência, fonte, licença, Dockerfile ou ADR mudou. O adaptador ADR 0039
permanece intacto; layout usa APIs públicas ReportLab, pypdf somente leitura.
Inventário qualificado em B: 35 distribuições, 6093 payloads, seis fontes, 204 licenças e
**dez fontes de implementação** (sete `pdf_*.py` e os três suportes explícitos).
O glob existente inclui `pdf_renderer.py`; o teste de inventário foi atualizado.
Identificadores: `implementation=human-dossier/1.0.0`, `style=dossier-v1/1.0.0`.
O JSON foi regenerado após a implementação; somente esses identificadores e
`implementation_files` diferem do inventário de A. Novo `render_environment_id`:

```text
0c769e56deb824ff8e9c02ab2632159b1c5d6d66bae1dc34c3d1aa71d9fdd5ad
```

Substitui o ID de A `afc096a426ccdcafb3e9d0c7be3a0110be7e0c15c8e968daae3c9a05007af8a6`
por cobertura de implementação/estilo; os goldens PDF/pixels de A continuam idênticos.

| Gate B, no runtime restrito descrito acima | Resultado, exit 0 |
| --- | --- |
| Renderer/layout/validator dirigido | 35 passed, 3 deselected; 124.50 s |
| Fundação PDF + parser + inventário | 109 passed; 73.96 s |
| Regressão 8B1 | 792 passed, 3 skipped; 69.05 s |
| Determinismo do renderer | 1 passed, 37 deselected; 51.99 s |
| PDFium do renderer | 2 passed, 36 deselected; 10.68 s |
| Pytest completo | 2035 coletados: 2032 passed, 3 skipped; 359.89 s |
| Ruff check / format --check | PASS / PASS, 195 arquivos |
| mypy src | PASS, 86 arquivos |
| git diff --check | PASS |

Os três skips permanecem exclusivamente os mesmos gates Windows descritos em A.
Os 38 testes novos de renderer incluem fonte ausente, múltiplos subsets, entidades,
listas, H3, tabelas de 2/7 colunas e sem linhas de corpo, 20 janelas sintéticas,
limites de página/linha, corrupção de texto/navegação/chrome e conteúdo ativo.

Mesmo processo, dez processos independentes com diretórios temporários distintos,
A/B/A, container limpo/reiniciado e hostname/UID-GID 1000:1000 → 1001:1001:
mesmos bytes. Workers isolados exercitados com RLIMIT_AS 1 GiB e CPU 120 s;
esta API não acrescenta orquestração, CLI ou publicação. Dossiê representativo
sintético: 22 páginas, 261481 bytes, SHA-256:

```text
c2365cdf93c11e9ce55347b3a8126036c393befb030e3aa2ce0b7e12cede67f2
```

PDFium: cenário representativo de 22 páginas e cenário extremo de seis páginas,
duas rasterizações independentes, 144 DPI, 1191 × 1684, RGB/branco. Verificação
de glifos/limites de células e inspeção de previews de TOC, tabelas, continuações
e índice sem cortes/sobreposição nas páginas examinadas. SHA-256 da concatenação
ASCII ordenada dos hashes de pixels de cada página, fixados nos testes:

```text
representativo: a3b521279af0383c0593ca11e7ea105aefe35757b5da084090b5b56b20627779
extremo:       4415bc9ea298319c3508bceee51eda0e775a306065247d5b3fc91d87f3528a49
```

Sem PDFs/PNGs no Git; previews temporários fora do checkout foram removidos.
Reprodução dirigida: `tests/test_pdf_renderer.py`, no mesmo container qualificado,
com filtros `-k 'not determinism and not pdfium'`, `-k determinism` e `-k pdfium`.

### Aprovação técnica humana final de 8B2-B

Revisão humana concluída e aprovada pelo operador:

- 8B2-B CODE REVIEW: PASS.
- 8B2-B STRUCTURAL REVIEW: PASS.
- 8B2-B VISUAL HUMAN REVIEW: PASS.
- 8B2-B: COMPLETE — HUMAN REVIEW APPROVED.
- 8B2-A: COMPLETE — HUMAN REVIEW APPROVED.
- 8B2-C: NOT STARTED; consolidated-report.pdf não implementado.
- 8B3: FUTURE.

A revisão humana inspecionou independentemente os dois PDFs inteiramente
sintéticos renderizados a **200 DPI**. A validação PDF independente já havia
passado para ambos. Artefatos revisados:

| PDF sintético | Páginas | Bytes | SHA-256 |
| --- | --- | --- | --- |
| 8B2-B-representative.pdf | 22 | 261481 | c2365cdf93c11e9ce55347b3a8126036c393befb030e3aa2ce0b7e12cede67f2 |
| 8B2-B-extreme.pdf | 6 | 165700 | 1cd66ee78cbac02abc8cbeae7e1d47b3e42675c39f036daab83d12599deedd4a |

Confirmados título e TOC de 14 entradas, numeração de páginas e header/footer
consistentes, hierarquia H1/H2/H3 coerente e parágrafos/bullets legíveis. Tabelas
permanecem nos limites de página/corpo, com headers repetidos nas continuações
e continuidade correta das tabelas finais de provenance. Sem clipping,
sobreposição de texto, páginas vazias acidentais, glifos visivelmente quebrados
ou visual exhibit embutido. A referência ao annex-index permanece texto inerte.

Tabelas técnicas densas de colunas iguais podem quebrar identificadores de forma
acentuada, sem clipping, truncamento ou sobreposição. Esse comportamento foi
aceito como não bloqueante sob o layout atual do ADR 0038.

Esta promoção é exclusivamente documental: não repete testes, build ou rendering,
não regenera inventário nem altera hashes, artefatos ou decisões técnicas.
O render_environment_id permanece
`0c769e56deb824ff8e9c02ab2632159b1c5d6d66bae1dc34c3d1aa71d9fdd5ad`.
A revisão humana a 200 DPI não substitui nem altera os goldens automatizados
a 144 DPI registrados acima. CLI/serviço/pacote/publicação PDF não implementados;
nenhum caso real acessado. A aprovação de B não conclui toda a 8B2 nem inicia C/8B3.

## Fechamento sintético 8B2-C — revisão humana aprovada

8B2-A e 8B2-B permanecem COMPLETE — HUMAN REVIEW APPROVED.
8B2-C: **COMPLETE — HUMAN REVIEW APPROVED**. 8B3: FUTURE.
Isso não conclui toda a 8B2 nem autoriza execução real.

API `render_consolidated_report_pdf(data: bytes) -> bytes` no renderer existente.
Consome somente os bytes fornecidos de `technical/canonical/consolidated-report.md`
para apresentar `human/consolidated-report.pdf`; não lê pacote/snapshots, não chama
build_consolidated_model/render_markdown e não acessa DB, CASE_ROOT ou originals/working.
Layout compartilhado com `render_dossier_pdf`, sem duplicação ou mudança de estilo.
Perfis fechados dossier/consolidated-report; expectativas independentes do validador
por kind, título, H2 ordenados, header e cardinalidades. Relatório: 20 H2,
20 entradas/links GoTo do TOC e 21 destinos/outlines ordinais; H3 somente no corpo.
Header `Relatório técnico consolidado`, footer `Página N`. Tabelas de 2/3/4/5/6/8
colunas com largura igual, wrapping, headers repetidos e linhas indivisíveis.
Linha impossível falha DOSSIER_PDF_UNSUPPORTED_LAYOUT, sem truncamento ou redução de fonte.

### Inventário e preservação de 8B2-B

Imagem desta qualificação: `digital-evidence-engine:pdf-consolidated`, construída
com o mesmo `Dockerfile.pdf`, base, dependências, fontes e artefatos fixados.
Identificadores: `implementation=human-documents/1.0.0`;
`style=dossier-v1/1.0.0` permanece inalterado. Mesmos dez arquivos cobertos pelo
inventário fechado. Frente a B, somente `implementation` e `implementation_files`
diferem; neste último, mudaram apenas pdf_renderer.py e pdf_validation.py.
Distribuições/payloads, fontes, licenças e todos os demais campos são idênticos.
Inventário regenerado após estabilização, com render_environment_id:

```text
1e15c83725d5e5baba7bedc5b3c52465b12612e3f5d173696567635fdc3da671
```

Substitui o ID de B para esta implementação, sem alterar os artefatos qualificados
da toolchain. O SHA representativo aprovado de B permanece exatamente:

```text
c2365cdf93c11e9ce55347b3a8126036c393befb030e3aa2ce0b7e12cede67f2
```

Os dois pixel goldens de B permanecem inalterados:

```text
representativo: a3b521279af0383c0593ca11e7ea105aefe35757b5da084090b5b56b20627779
extremo:       4415bc9ea298319c3508bceee51eda0e775a306065247d5b3fc91d87f3528a49
```

### Fixtures consolidadas sintéticas

Definidas em `tests/test_pdf_consolidated_renderer.py`; nenhuma evidência real.
O produtor Markdown é usado apenas para construir a fixture representativa nos
testes. A fixture extrema exercita H3 W/F/G, listas, spans, escapes, tokens longos
e tabela de oito colunas. Validação PDF independente passou para ambas.

| Fixture | Páginas | Bytes | SHA-256 PDF |
| --- | ---: | ---: | --- |
| representative() | 17 | 229162 | 81a2e238ddde30ab435e2069decf55a973e08058c37f92958489ce1836344227 |
| extreme() | 7 | 219747 | 9df405048a2d11ca992d568ff33d1a014c638a35238f9cf4e0b1a56818b10133 |

PDFium a 144 DPI, RGB/branco, 1191 × 1684 pixels. SHA-256 da concatenação ASCII
ordenada dos hashes dos pixels decodificados por página:

```text
representativo: 194bf73adb3e4111d2a063e6fb2001791957e8bbce5e6c0e2dc6ee340d24e852
extremo:       31495af761544f820fdd2da81de3125665a22a1cb9ba170025854d3f64d60c4b
```

Duas rasterizações por fixture, bounds de glifos/corpo/células, ausência de páginas
vazias e interseções de caixas de texto verificadas automaticamente. Sem substituir
a revisão visual humana, posteriormente aprovada conforme registro abaixo. Dez processos independentes, diretórios
temporários distintos e alternância consolidado/dossiê/consolidado/dossiê preservam
bytes. As duas fixtures também conservaram bytes/pixels após reinício de um
container temporário restrito; container de teste removido após exit 0.
PDFs/PNGs não são adicionados ao Git.

### Gates finais de C

Mesmo runtime Linux/amd64 restrito: rede none, raiz e checkout read-only, usuário
não root, cap-drop ALL/no-new-privileges e tmpfs; sem mounts de caso. Reproduzir com
os comandos acima usando a imagem `digital-evidence-engine:pdf-consolidated`.

| Gate | Resultado | Tempo | Exit |
| --- | --- | ---: | ---: |
| C: estrutura/layout/validação/determinismo | 42 passed, 2 deselected | 105.26 s | 0 |
| C: PDF/PDFium goldens | 2 passed, 42 deselected | 15.30 s | 0 |
| B: todos os testes, SHA/pixels originais | 38 passed | 151.83 s | 0 |
| Fundação PDF / parser / inventário | 109 passed | 80.86 s | 0 |
| Regressão 8B1 | 792 passed, 3 skipped | 66.81 s | 0 |
| Pytest completo | 2079 coletados; 2076 passed, 3 skipped, 0 failed/errors | 514.34 s | 0 |
| Ruff check --no-cache . | PASS | — | 0 |
| Ruff format --check --no-cache . | PASS, 196 arquivos | — | 0 |
| mypy --cache-dir=/tmp/dee-mypy src | PASS, 86 arquivos | — | 0 |
| git diff --check | PASS | — | 0 |

Os 44 testes novos incluem corrupção de fonte/plano/PDF, troca de perfil,
navegação/chrome, gramática proibida, conteúdo ativo e limites de página/linha.
Os três skips permanecem os mesmos testes exclusivos de Windows registrados em A.
A saída completa do pytest iniciado antes da interrupção foi recuperada com exit 0;
não se repetiu a suíte completa nem os gates dirigidos na retomada. Ruff/format/mypy
foram executados uma vez após confirmar esse resultado. Nenhum gate PDF dispensado.

Sem alteração de dependências, lockfile, Dockerfile, schema, ADRs, adapter ou
superfície privada ReportLab. pypdf somente leitura, sem reescrita/pós-processamento.
Sem CLI/serviço PDF, descoberta, binding manifesto/SHA256SUMS ou publicação de pacote.
Nenhum caso real acessado. A qualificação continua limitada às fixtures sintéticas
e ao ambiente canônico; tabelas densas podem quebrar identificadores em várias linhas.

### Aprovação técnica e visual humana final de 8B2-C

Revisão humana concluída e aprovada pelo operador:

- 8B2-C CODE REVIEW: PASS.
- 8B2-C STRUCTURAL REVIEW: PASS.
- 8B2-C AUTOMATED QUALIFICATION: PASS.
- 8B2-C VISUAL HUMAN REVIEW: PASS.
- 8B2-C: COMPLETE — HUMAN REVIEW APPROVED.
- 8B2-A e 8B2-B: COMPLETE — HUMAN REVIEW APPROVED.
- 8B3: FUTURE.

A revisão humana renderizou e inspecionou independentemente todas as **24 páginas**
dos dois PDFs sintéticos a **200 DPI**. A validação PDF independente já havia
passado para ambos. Artefatos revisados:

| PDF sintético | Páginas | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| 8B2-C-representative.pdf | 17 | 229162 | 81a2e238ddde30ab435e2069decf55a973e08058c37f92958489ce1836344227 |
| 8B2-C-extreme.pdf | 7 | 219747 | 9df405048a2d11ca992d568ff33d1a014c638a35238f9cf4e0b1a56818b10133 |

Confirmados título, TOC de 20 entradas e seus números de página, header/footer
consistentes e hierarquia H1/H2/H3 coerente. Parágrafos, negrito, literais e bullets
legíveis; acentos portugueses e texto especial sintético corretamente apresentados.
Tabelas permanecem nos limites do corpo/página, inclusive a tabela extrema de oito
colunas, sem clipping ou sobreposição. Headers repetidos aparecem nas continuações;
linhas lógicas permanecem visualmente intactas. A tabela final de provenance
continua corretamente entre as páginas 16–17. Sem páginas vazias acidentais,
glifos visivelmente quebrados, visuais embutidos ou colisões entre texto/header/footer.

Tabelas técnicas densas de colunas iguais podem quebrar identificadores longos de
forma acentuada, sem clipping, truncamento ou sobreposição; comportamento aceito
como não bloqueante sob o ADR 0038.

Esta promoção é somente documental, sem requalificação técnica, testes ou rendering.
Permanecem os 2079 testes coletados, 2076 passed e três skips do gate registrado,
os hashes PDF/pixels de B/C e o render_environment_id
`1e15c83725d5e5baba7bedc5b3c52465b12612e3f5d173696567635fdc3da671`.
A revisão humana a 200 DPI não altera os goldens automatizados a 144 DPI.
Sem mudança de código, testes, dependências, ADRs ou inventário; nenhum caso real
acessado. A aprovação de C não conclui toda a 8B2 nem inicia a futura 8B3.

## Fechamento sintético 8B2-D — revisão humana aprovada

8B2-A/B/C permanecem **COMPLETE — HUMAN REVIEW APPROVED**.
Estado naquele fechamento: 8B2-D: **COMPLETE — HUMAN REVIEW APPROVED**.
8B2-E: **NOT STARTED**. 8B3: **FUTURE**. O fechamento posterior E consta abaixo.
A revisão técnica/de integridade humana foi concluída e aprovada; sem execução real.

### Captura e binding

`pdf_package.py` captura explicitamente um directory-v1 publicado, somente leitura.
Valida dossier.selection/1.0.0, dossier.package_manifest/1.0.0, sums, campos fechados,
ordenação, papéis/classes/paths, cardinalidades e árvore exata. Faz streaming de
todos os arquivos para conferir tamanho/SHA-256, reutilizando checks 8B1/Foundation
de path/handle, links/reparse/hardlinks e arquivos regulares. Retém bytes imutáveis
somente dos dois Markdown, metadata de seleção, manifesto e sums. Snapshot/media
são opacos: sem semântica de snapshot, regeneração de relatório, assembly ou decode.

`capture_source_package` conserva baselines de identidade/estabilidade. Recheck
verifica novamente toda a árvore, tipos, identidade, tamanho e hash; o binding
revalida a origem antes e depois. Detecta mudanças observáveis, **sem promessa de
snapshot atômico**. A futura orquestração E deve usar essa fronteira de recheck.

Bindings fixos, sem mapping/profile/expectativa do caller:

- human/dossier.md → human/dossier.pdf;
- technical/canonical/consolidated-report.md → human/consolidated-report.pdf.

`bind_pdf_export` recebe PDFs já produzidos. Deriva a expectativa com parser/layout
existentes sobre os bytes Markdown capturados, valida cada PDF independentemente
e obtém page_count do resultado. Tamanho/hash vêm dos bytes reais; não renderiza
outro PDF, não modifica PDFs nem amplia superfície privada ReportLab.

### Manifesto, sums e limites

Manifesto: policy_id dossier.pdf_export_manifest, policy_version 1.0.0,
export_policy_id dossier.pdf_export, export_policy_version 1.0.0,
delivery_profile pdf-presentation-v1, render_environment_id verificado,
source_package exatamente manifest_sha256/sha256sums_sha256 dos bytes originais,
entries exatamente duas, ordenadas por package_path ASCII. Cada entrada contém
somente package_path, source_package_path, source_byte_size, source_sha256,
byte_size, sha256 e page_count. Inteiros exatos (não bool), tamanhos não negativos,
páginas positivas; hashes lowercase de 64 hex. JSON UTF-8 sem BOM, ensure_ascii=True,
sort_keys=True, separators=(",", ":"), allow_nan=False e exatamente um LF final.

SHA256SUMS contém exatamente três linhas, nesta ordem:

1. human/consolidated-report.pdf;
2. human/dossier.pdf;
3. integrity/pdf-export-manifest.json.

Formato: hash lowercase, dois espaços ASCII, path POSIX e LF, sem CRLF ou
self-entry. Dependência acíclica PDFs → manifesto → sums. `verify_pdf_export`
confere exatamente quatro paths/bytes lógicos e refaz o binding independente.
Mesmos inputs em roots distintos e permutação interna de entradas produzem bytes
iguais; ordem serializada fora do contrato é rejeitada. Nenhum path absoluto,
data, label, case_reference ou metadata de host é acrescentado ao manifesto.

Limites preservados: origem 1 GiB/261 arquivos; Markdown 64 MiB cada/128 MiB total;
administrativos 64 MiB cada; JSON depth 64, 1.000.000 nodes, lexema numérico 128;
PDF 64 MiB cada/128 MiB total/1000 páginas cada; manifesto e sums novos 1 MiB cada;
output de quatro arquivos 130 MiB. Paths: 1024 bytes/32 componentes/255 bytes por
componente. Limites de papel/classe/contagem de 8B1 preservados, sem máximo
semântico de 20 snapshots. Erros sanitizados DOSSIER_PDF_INVALID_PACKAGE,
INTEGRITY_MISMATCH, INPUT_CHANGED, RESOURCE_LIMIT e INTERNAL_ERROR; erros existentes
de parser/ambiente/validador conservados quando aplicáveis. Sem novos códigos.

### Inventário e regressão

render_environment_id de D:

```text
ca80ae373d0edcb42d6616abd5043e45e7b96ec5f7d3dc0ad391d4b71f12fe97
```

Comparação com C: somente implementation_files mudou, pela inclusão de
src/evidence_engine/dossier/pdf_package.py. Hashes de todos os arquivos anteriores,
dependências, fonts, licenças, base e ferramentas permaneceram iguais.
implementation=human-documents/1.0.0 e style=dossier-v1/1.0.0 preservados.
Nenhum renderer/validador/model/limits/adapter existente foi alterado.

SHA dossier B: c2365cdf93c11e9ce55347b3a8126036c393befb030e3aa2ce0b7e12cede67f2.
SHA consolidado representativo C:
81a2e238ddde30ab435e2069decf55a973e08058c37f92958489ce1836344227.
Todos os fingerprints PDF/PDFium existentes de B/C, inclusive extremos, passaram
inalterados nos 82 testes e na suíte completa. As quatro sequências RGB permanecem:

```text
B representative: a3b521279af0383c0593ca11e7ea105aefe35757b5da084090b5b56b20627779
B extreme:        4415bc9ea298319c3508bceee51eda0e775a306065247d5b3fc91d87f3528a49
C representative: 194bf73adb3e4111d2a063e6fb2001791957e8bbce5e6c0e2dc6ee340d24e852
C extreme:        31495af761544f820fdd2da81de3125665a22a1cb9ba170025854d3f64d60c4b
```

### Gates finais de D

Imagem digital-evidence-engine:pdf-integrity, Dockerfile.pdf sem alteração,
Python 3.12.14 Linux/amd64. Runtime sem rede, root/check-out read-only, usuário
não root, cap-drop ALL/no-new-privileges, tmpfs, memória 2 GiB e 2 CPUs; sem mounts
de caso. Pytest com `-p no:cacheprovider`; Ruff sem cache; mypy cache em /tmp.

| Gate | Resultado | Tempo | Exit |
| --- | --- | ---: | ---: |
| 8B2-D dirigido | 156 passed | 60.69 s | 0 |
| B/C renderers, PDFs e PDFium | 82 passed | 191.22 s | 0 |
| Fundação/parser/inventário | 110 passed | 43.31 s | 0 |
| 8B1 completo, incluindo package/integrity/stability | 792 passed, 3 skipped | 35.72 s | 0 |
| Pytest completo | 2236 coletados; 2233 passed, 3 skipped, 0 failures/errors | 501.41 s | 0 |
| Ruff check --no-cache . (retomada) | PASS | — | 0 |
| Ruff format --check --no-cache . (retomada) | PASS, 198 arquivos | — | 0 |
| mypy --cache-dir=/tmp/dee-mypy src (retomada) | PASS, 87 arquivos | — | 0 |
| git diff --check | PASS | — | 0 |

Saída final íntegra do processo pytest anterior recuperada com exit 0 na retomada;
não se repetiu a suíte completa nem os gates dirigidos. Checks Ruff/format/mypy
foram repetidos uma vez, conforme solicitado, após confirmar o pytest completo.
Os três skips são os testes existentes de junctions e publicação nativa Windows;
nenhum teste PDF dispensado. Não se declara validação nativa Windows de D.

Sem caso real, CASE_ROOT/DB/originals/working na camada nova; testes exclusivamente
sintéticos. Sem mudança de dependência, lockfile, Dockerfile, schema/migration,
ADRs ou superfície privada. pypdf somente leitura, sem pós-processamento.
D retorna DTOs/bytes: staging/publicação, ownership/fsync, workers/timeouts e
CLI/serviço PDF pertencem a E, ainda não iniciada. Não conclui toda a 8B2.

### Aprovação humana final de integridade 8B2-D

Revisão humana concluída e aprovada: CODE REVIEW, STRUCTURAL REVIEW,
AUTOMATED QUALIFICATION e INTEGRITY HUMAN REVIEW: **PASS**.
8B2-D: **COMPLETE — HUMAN REVIEW APPROVED**.

Artefatos sintéticos revisados: pdf-export-manifest.json, 1106 bytes, SHA-256
`ff2be0b2aca84511dc9a72366ba041cd5e6f293a860bc4e128425fbb609f9ab1`;
SHA256SUMS.txt, 281 bytes. O resumo de revisão foi conferido e é consistente
com o manifesto.

A revisão confirmou JSON canônico UTF-8 sem BOM, somente LF e exatamente um LF
final; contrato fechado, duas entradas em ordem ASCII, mappings Markdown→PDF
fixos, tamanhos/hashes de origem e PDF, page_count, hashes de integridade do pacote
fonte e render_environment_id esperado. Nos sums: três entradas em ordem ASCII,
delimitador de dois espaços, digests lowercase de 64 hex, sem self-entry ou linha
extra; o digest do manifesto coincide independentemente com o SHA-256 acima.

Promoção exclusivamente documental, sem requalificação ou alteração de código,
testes, dependências, ADRs, inventário, hashes PDF/PDFium ou gates registrados.
Preservado render_environment_id
`ca80ae373d0edcb42d6616abd5043e45e7b96ec5f7d3dc0ad391d4b71f12fe97`.
Naquela promoção, 8B2-A/B/C continuavam COMPLETE — HUMAN REVIEW APPROVED;
8B2-E NOT STARTED e 8B3 FUTURE. Sem acesso real ou implementação de staging/publicação/CLI/serviço
PDF nesta promoção; sem promessa de snapshot atômico ou certificação.

## Fechamento sintético 8B2-E — revisão humana aprovada

8B2-A/B/C/D: **COMPLETE — HUMAN REVIEW APPROVED**.
8B2-E: **COMPLETE — HUMAN REVIEW APPROVED**.
Naquele fechamento de E, 8B2-F/G estavam **NOT STARTED**. 8B3: **FUTURE**.

### Implementação e fronteiras

Arquitetura híbrida: supervisor controla preflight, paths/overlap, staging/scratch,
processos/deadlines e publicação; worker mantém CapturedSourcePackage em memória,
renderiza consolidado antes do dossiê, chama binding D, escreve quatro arquivos
exclusivos/fsynced, relê staging para verificação D e faz recheck final da origem.
Worker nunca publica; supervisor não refaz captura, narrativa ou validação PDF.

IPC usa dois pipes dedicados (eventos/ACK), JSON canônico fechado, 4096 bytes por
mensagem e 64 KiB por direção; stdout/stderr têm limites separados de 64 KiB.
Deadline global monotônico de 600 s desde antes do preflight e 120 s por fase de
render/validação, incluindo chamadas D aninhadas. SIGKILL/reap precede cleanup.
Peer é criado antes do RLIMIT_AS: falha em impor/verificar o limite transmite
ENVIRONMENT_UNSUPPORTED, sem ser reduzida a crash genérico. Worker: AS 1 GiB;
container/cgroup: memória 2 GiB, swap adicional zero, pids 64 e 2 CPUs.

Staging é privado, exclusivo, irmão do destino no mesmo filesystem. Scratch próprio
interno, limite 256 MiB; handshake após worker fechar handles/sair do cwd precede
remoção e verificação dos quatro arquivos. READY exige exit 0 e encerramento dos
processos; supervisor verifica árvore/hashes/ownership, paths, prazo e fsync antes
de uma única renameat2(RENAME_NOREPLACE). Sem replace/merge/copy fallback, retry
após publicação ambígua ou filesystem I/O após sucesso confirmado. Cleanup somente
de staging com ownership provado. Fonte não é snapshot atômico; há corrida residual
após o último recheck. Sem promessa de cleanup após host crash/SIGKILL ou durabilidade
elétrica. Serviço não reentrante no mesmo processo retorna INTERNAL_ERROR; processos
CLI separados disputando o mesmo destino preservam o vencedor e retornam OUTPUT_EXISTS
ao perdedor. Testes cobrem ambos os comportamentos.

`dee dossier pdf --input-package PATH --output-dir PATH`: opções obrigatórias únicas.
Sucesso: exit 0, stdout exato `DOSSIER_PDF_OK\n`, stderr vazio. Falhas inclusive sintaxe:
exit 2, stdout vazio, stderr exato `ERROR: DOSSIER_PDF_<CODE>\n`. Help não abre input
nem verifica ambiente. `dossier assemble` permanece compatível.

### Qualificação de implantação e publicação

Imagem candidata: `sha256:d3f54de75a5e681a82521fddeaf96349fcf3c09efffb869aa3d6cf9f88b8bc75`.
Docker Desktop/WSL2 hospeda Linux/amd64 canônico, Python 3.12.14. Windows pode ser
host do container; isso não é exportação PDF nativa Windows.
Gate positivo utilizou bind Linux/WSL **ext4**, não bind de diretório Windows.
Probe novo: destino ausente PASS; destino existente EEXIST (17), sentinela
preservado; parents/staging/destino compartilham st_dev=2128 naquele runtime.

Pacote 8B1 inteiramente sintético: 11 arquivos, 39805 bytes, assembly exit 0 e
verificação independente 8B1 PASS. Em novo container, pacote exposto em bind próprio
RO e parent da saída em bind próprio ext4 RW. Preflight sem monkeypatch confirmou:
Linux/x86_64; UID 1000; CapEff/CapPrm/CapInh/CapBnd/CapAmb zero; NoNewPrivs=1;
raiz RO; somente interface lo; cgroup v2 `0::/`; memory.max=2147483648,
memory.swap.max=0, pids.max=64 e cpu.max=`200000 100000`. Não inferir controle dos
aliases do host somente de mountinfo; isolamento/controle dos mounts continua
pré-requisito de implantação. O runtime não faz build/download automático.

CLI real sem bypass: exit 0, stdout `DOSSIER_PDF_OK\n`, stderr vazio. Verificação
externa D após retorno confirmou quatro arquivos, manifesto/sums/bindings válidos,
fonte inalterada e nenhum staging remanescente. PDFs desse pacote sintético:
consolidado 7 páginas, dossiê 8 páginas. Inspeção externa não altera a regra de zero
I/O pelo serviço após publicação confirmada.

Limitação negativa observada: bind Windows-backed **9p/drvfs**, no mesmo Docker
Desktop/WSL2, retornou EINVAL (22, Invalid argument) em renameat2 NOREPLACE com
destino ausente; com destino existente retornou EEXIST e preservou o sentinela.
Revalidação e fsync passaram; falha ocorreu na syscall e cleanup passou. Controles
tmpfs, volume Docker ext4 e bind Linux/WSL ext4 passaram. Essa configuração 9p/drvfs
não é alvo qualificado de publicação; não se afirma que toda implementação 9p falhe.
Allowlist e produto não foram alterados para contornar a falha. PUBLICATION_FAILURE
permanece fail-closed (DOSSIER_PDF_PUBLICATION_FAILURE no serviço PDF), sem fallback.

### Inventário e preservação

render_environment_id final:

```text
ce881cc28baf5b8e2328bd1d92979906779241f2af54e6222baf29fbb84bf4ca
```

Comparado a D, somente implementation_files mudou: pdf_limits.py, pdf_renderer.py,
pdf_validation.py e inclusão de pdf_service.py/pdf_worker.py. Dependências, fontes,
font source hashes, base, OS/toolchain, versões, implementation human-documents/1.0.0
e style dossier-v1/1.0.0 permaneceram iguais. Testes não entram no inventário.
O ID provisório do Checkpoint 1 foi substituído pelo candidato final acima.

B/C preservaram bytes PDF e todos os goldens PDFium. SHA-256 representativos:

- B: `c2365cdf93c11e9ce55347b3a8126036c393befb030e3aa2ce0b7e12cede67f2`.
- C: `81a2e238ddde30ab435e2069decf55a973e08058c37f92958489ce1836344227`.

### Gates finais

| Gate | Resultado | Tempo | Exit |
| --- | --- | --- | --- |
| E completo | 112 passed | 94.41 s | 0 |
| D | 156 passed | 81.09 s | 0 |
| B/C + PDFium | 82 passed | 261.15 s | 0 |
| Foundation/model/build/inventário | 112 passed | 57.35 s | 0 |
| 8B1 serviço/publicação | 60 passed, 1 skipped | 9.36 s | 0 |
| 8B1 completo | 792 passed, 3 skipped | 51.39 s | 0 |
| Full pytest, execução única | 2350 collected, 2347 passed, 3 skipped, 0 failures/errors | 693.51 s | 0 |
| test_pdf_service após wrapping | 27 passed, 0 skipped/failures | 57.18 s | 0 |
| Ruff check --no-cache | PASS | — | 0 |
| Ruff format --check --no-cache | 204 files already formatted | — | 0 |
| mypy --cache-dir=/tmp/dee-mypy src | 89 source files, no issues | — | 0 |
| git diff --check | PASS | — | 0 |

Os três skips do full pytest exigem Windows nativo (junctions/no-replace).
Após full pytest, a única alteração Python foi wrapping de dois literais de teste
para corrigir E501 em tests/test_pdf_service.py. AST completa e valores UTF-8 antes/
depois são idênticos; parametrização, erros, timeouts e fixtures não mudaram.
O teste dirigido acima foi repetido; full pytest não foi repetido por estilo.
Nenhum byte de produção/inventário mudou nessa retomada. A promoção posterior
altera somente documentação. Material de revisão é cópia separada fora do Git,
com SHA-256 dos quatro arquivos comparado à publicação ext4 preservada.

### Aprovação humana final 8B2-E

- CODE REVIEW: PASS.
- STRUCTURAL REVIEW: PASS.
- AUTOMATED QUALIFICATION: PASS.
- DEPLOYMENT REVIEW: PASS.
- INTEGRITY HUMAN REVIEW: PASS.
- VISUAL HUMAN REVIEW: PASS.
- 8B2-E: **COMPLETE — HUMAN REVIEW APPROVED**.
- Naquela aprovação de E, 8B2-F e 8B2-G estavam **NOT STARTED**.
- 8B3: **FUTURE**.

Artefatos inteiramente sintéticos revisados:

| Artefato | Bytes | Páginas | SHA-256 |
| --- | ---: | ---: | --- |
| `human/consolidated-report.pdf` | 162656 | 7 | `615786f9bcf2e1e8c31e1dd0c45b209c4fdad9b74b13f76d8ad2637758c39f09` |
| `human/dossier.pdf` | 139523 | 8 | `fd481f1dc589eb705d3f69423ee669c4b6b568ce1385016f407dc707788ad676` |
| `integrity/pdf-export-manifest.json` | 1106 | — | `bd02c02b38f1a586fdff65a0a964afb9ddabe01b385f3ced6e13dcbb2cacaa63` |
| `integrity/SHA256SUMS.txt` | 281 | — | `c19acb2b10c42206f94b50d34dd8f19174ec5c97cdbd706357a265f7c3be6433` |

O `render_environment_id` revisado permanece
`ce881cc28baf5b8e2328bd1d92979906779241f2af54e6222baf29fbb84bf4ca`.
A revisão visual humana inspecionou as 15 páginas a 200 DPI. TOCs e referências
de página estavam corretos; headers, footers e numeração estavam consistentes;
não houve clipping, sobreposição, glifo quebrado ou página em branco acidental.
A página 8 do dossiê é continuação intencional do índice de anexos. O wrapping
agressivo de identificadores técnicos densos permanece comportamento aceito e
não bloqueante, sem clipping, truncamento ou sobreposição.

A revisão de implantação aprovou o alvo canônico Linux/amd64 com bind Linux/WSL
ext4. O bind Windows-backed 9p/drvfs testado retornou EINVAL para
RENAME_NOREPLACE com destino ausente e não é qualificado nessa configuração
observada; isso não é generalização para todas as implementações 9p. Não existe
fallback de publicação nem alegação de exportação PDF nativa Windows.

## Qualificação sintética 8B2-F — revisão humana aprovada

8B2-F: **COMPLETE — HUMAN REVIEW APPROVED**. A classificação permaneceu
**A. TEST/QUALIFICATION ONLY**. Somente
`tests/test_pdf_presentation_extremes.py` foi acrescentado à implementação;
nenhum byte de model/renderer/validator/limits/service/worker, dependência, ADR ou
inventário mudou. O limite do ADR 0038 permanece 16 colunas por documento: tabela
de 16 colunas renderiza e valida; 17 falha `DOSSIER_PDF_RESOURCE_LIMIT`. A cobertura
2/3/4/5/6/8 anterior de C não é máximo semântico de oito colunas.

### Fixtures e limites congelados

`dossier_pagination_extreme()` usa somente as 14 seções e a gramática existentes:
H3 longo, parágrafo e bullet longos, token ASCII não quebrado de 1024 caracteres e
o conjunto exato de escapes `\\`, backtick, `*`, `_`, `{}`, `[]`, `()`, `#`, `|`,
`!`. Quarenta e sete linhas fixas deixam a última baseline da penúltima página em
y=80.046 pt; a seção 14 é deslocada e preservada como página final intencional com
somente seu H2 e uma linha de conteúdo, além do chrome.

`consolidated_table_extreme()` usa as 20 seções existentes, H3 longo, tabela de oito
colunas com headers longos quebrados e repetidos, 48 linhas densas/continuações,
tokens e prosa longos, uma linha lógica limite e tabela válida de 16 colunas. Com
headers de 66 pt, 52 palavras geram linha de 630 pt e total válido de 696 pt;
53 palavras geram linha de 642 pt e total 708 pt, recusado com
`DOSSIER_PDF_UNSUPPORTED_LAYOUT`. No PDF mínimo, budgets reduzidos congelados
801/800 nós e profundidade 19/18 demonstram N/N-1; páginas também usam N/N-1.

| Fixture F | Páginas | Bytes | SHA-256 PDF |
| --- | ---: | ---: | --- |
| `dossier_pagination_extreme()` | 10 | 150026 | `a58f54ad2eff5cf7f142b1979471dfb4ca0bce9f1103527841da98c91fafa3cf` |
| `consolidated_table_extreme()` | 12 | 333859 | `45768275fc7e8a1d2dc223e7889ff01bed46b1feafcd10d56e9c22a8a7cf837d` |

Validação independente passou para os dois PDFs. Repetições locais, A/B/A e dois
processos/roots distintos por perfil produziram bytes e page counts idênticos.

### PDFium F

pypdfium2 5.13.0/PDFium 153.0.7999.0, 144 DPI (`scale=2`), RGB, fundo branco,
1191 × 1684. Todas as páginas foram rasterizadas duas vezes com pixels idênticos;
geometria independente confirmou bounds de glifos/corpo/células, ausência de
overlap e páginas vazias, headers repetidos, TOC, destinos e outlines. Hashes RGB
por página, em ordem:

```text
dossier p01 330788be4b5b295dac19881953fcc31cdff62b83a9c9b7e4b9d5ecda6a29ee73
dossier p02 e4cfa2c661d911b1972d209d4398021914b4c1078a61eebed0073cea338d1d0b
dossier p03 a5c26c53a9fb217a7bd7af0a45f53cb251f600db50276ec4efc9c5c07cf9abec
dossier p04 7600964dd48a82d3f4f9203a194701bac644c1a50e4cc1d2021f8eb17210aca0
dossier p05 c9730ea1526f3338325e35ce5bde649f9158613fb8b15b6d1af653d96ac11a0a
dossier p06 549c1f1f17af24bd9996cbe6fd5b6e5e18b9d937db303208832d741322ecc0df
dossier p07 bb2ad0cf47f0ec67a1b4cec90006665f5781c9187420557035f1a4cef7db5b1a
dossier p08 2e8a62148bfe45105ba8e7eb9eb78d62af4a45024bde79318fea1621405d299a
dossier p09 8d0d842c36ae5018bf4a3ce0b81c202148215530a08562ecf0933c482604fba5
dossier p10 c5cf1b09bc164ba50acaec6e97696b37efae069e19798899b70efbe15af1cf6f
consolidated p01 5aea322d41a57620f5f7d961864b17c59f972d5bd0f466063a5fe0a7c2105a20
consolidated p02 c6cdb8abd5cca2936c27eab5b40303c8f488e38785db92913ac64e383b852391
consolidated p03 2a04a38a46d4f4f74b207149322f9c38d6d0062998b29437a2b51f62246866c3
consolidated p04 d6121e7e16578ca6f1b660b7114fd92766baf604f0737f2dbbbbfd247afcee9c
consolidated p05 e13d00857484108f793204ca53b6a78cc27ee23aefb40a98776c3faed2e1eb77
consolidated p06 5a1e95a5c311ad71ae16a6d3792efa8273612095eb4a962ade8e28b3efa1e64e
consolidated p07 a91cb5373cfc00623a32f3a67619795681b8a02d96a1308411c0f11a657072e0
consolidated p08 175efdd2ed225545918c136fc6d7916b6909530f6d97f391f407d7d7e82ae872
consolidated p09 4d5ea88522187c4f461c0ae48430a8085a58971709b09fdc7124d43f22fc17a9
consolidated p10 84b9722a380005c0bb780e634583c9597f0b4ba978888772e13a6acd6a043ee4
consolidated p11 c89280e5f8d00ae0c893678085fa44b0ea4ac359bd2e5db08cdaf1f5ff571549
consolidated p12 4ae775e5714bab03edc1511315d35a8ec795ac89ed340324b4e95cc36d6a8ff6
```

Fingerprints agregados da concatenação ASCII ordenada:

- dossiê: `d4320a379148a0ee59d9718d9dd1711097b71e216b7f2dbc241f277de5ef2b71`;
- consolidado: `709113ceace2c5ea62d18bc2fa24efb2c7139c8d70cc92beec132082fc64e5da`.

### Gates F

| Gate | Resultado | Tempo | Exit |
| --- | --- | ---: | ---: |
| F estrutural, sem determinismo/PDFium | 5 passed, 3 deselected | 13.71 s | 0 |
| F completo | 8 passed | 48.62 s | 0 |
| Regressão completa B/C | 82 passed | 181.01 s | 0 |
| Pytest completo, execução única | 2358 collected; 2355 passed, 3 skipped | 695.97 s | 0 |
| Ruff check `--no-cache .` | PASS | — | 0 |
| Ruff format `--check --no-cache .` | 205 files already formatted | — | 0 |
| mypy `--cache-dir=/tmp/dee-mypy src` | 89 source files, no issues | — | 0 |

Os três skips exigem Windows nativo e são os mesmos gates de junction/no-replace já
documentados. B/C conservaram seus hashes PDF e pixel fingerprints. O
render_environment_id permanece
`ce881cc28baf5b8e2328bd1d92979906779241f2af54e6222baf29fbb84bf4ca`;
`docs/pdf-render-environment.json` não foi regenerado. PDFs e rasters F para revisão
humana são inteiramente sintéticos e ficam fora do Git. Nenhum caso real foi acessado.
Naquele gate de F, 8B2-G ainda não havia iniciado e 8B3 era futura.

### Fechamento humano final de 8B2-F

A revisão humana externa e independente inspecionou todas as 22 páginas a 200 DPI.
O artefato `8B2-F-dossier-pagination-extreme.pdf` tem 10 páginas, 150026 bytes e
SHA-256 `a58f54ad2eff5cf7f142b1979471dfb4ca0bce9f1103527841da98c91fafa3cf`.
O artefato `8B2-F-consolidated-table-extreme.pdf` tem 12 páginas, 333859 bytes e
SHA-256 `45768275fc7e8a1d2dc223e7889ff01bed46b1feafcd10d56e9c22a8a7cf837d`.

- CODE/TEST REVIEW: **PASS**.
- AUTOMATED QUALIFICATION: **PASS**.
- VISUAL HUMAN REVIEW: **PASS**.
- HUMAN REVIEW: **PASS**.
- 8B2-F: **COMPLETE — HUMAN REVIEW APPROVED**.

Não houve nova execução de testes, rendering ou PDFium nesta promoção exclusivamente
documental. Os goldens automatizados a 144 DPI permanecem os registrados acima. O
render_environment_id permanece
`ce881cc28baf5b8e2328bd1d92979906779241f2af54e6222baf29fbb84bf4ca`.
Nenhum caso real foi acessado. Naquela promoção, 8B2-G permanecia **NOT STARTED**
e 8B3 **FUTURE**.

## Limitações e fronteira

### Requalificação derivada do release candidate público 1.0.0

P3 promoveu somente `evidence_engine.__version__` de 0.1.0 para 1.0.0 no inventário
de implementação qualificado. O inventário canônico foi regenerado pelo mesmo build
de `Dockerfile.pdf`, em Linux/amd64 com Python 3.12.14 e uv 0.8.22. A comparação
estrutural entre inventários encontrou exatamente duas diferenças de conteúdo:

- `packages["digital-evidence-engine"]`: `0.1.0` → `1.0.0`;
- `implementation_files["src/evidence_engine/__init__.py"]`:
  `9908bfdcf3861e0ebd8287edf7a0c3d24dc00563d35433dcbac94324a07b7d1e` →
  `1bb3294af1fa396e0ace117dac83ebfa8613f0fd2670da8cb786a570924a8214`.

O SHA-256 canônico do inventário, usado como `render_environment_id`, mudou de
`dd61d6fcebf3f2234228661bfe2b3dd970918f4685bf221b8dc5c93de2986f52` para
`6cddd9995f9d1758639fc54afe062914153fe95a7fb584adfb689896361f37e8`.
Artefatos, fontes, licenças, toolchain, arquivos de pacote e os demais arquivos de
implementação permaneceram byte a byte iguais.

Os gates direcionados na imagem regenerada aprovaram 145 testes de versão, CLI,
demo, snapshots, relatório consolidado, build e inventário. Dois testes canônicos de
determinismo em processos distintos também passaram e conservaram os hashes PDF já
qualificados; a entrada sintética congelada desses testes preserva sua versão histórica.
Não houve mudança no renderer, validador ou layout, nem atualização de golden PDF ou
pixel. A regressão Linux/amd64 completa imediatamente anterior já havia aprovado
2364 testes e registrado quatro skips contratuais; não foi repetida porque a diferença
de produção posterior é somente a constante de versão e o inventário derivado.

Esta requalificação usa somente dados sintéticos. Ela não publica artefato, não acessa
caso real e não altera as qualificações históricas registradas nas seções anteriores.

This is technical toolchain qualification, not legal advice.
No legal compliance certification. No PDF/A claim. No PDF/UA claim.
No digital-signature claim. No forensic certification. No real case used.

8B2-B dossier renderer: COMPLETE — HUMAN REVIEW APPROVED.
Consolidated-report PDF renderer: COMPLETE — HUMAN REVIEW APPROVED.
Serviço/CLI e publicação PDF: COMPLETE — HUMAN REVIEW APPROVED. 8B2-F COMPLETE —
HUMAN REVIEW APPROVED; 8B2-G concluiu posteriormente o fechamento sintético de
integração. A validação controlada 8B3 não incorpora pacote real ou dados de caso ao Git.
directory-v1 e schema v5 preservados. A qualificação é do perfil
sintético fechado e da imagem canônica; futuros slices devem qualificar suas
extensões de layout/validação. Sem promessa de rendering nativo multiplataforma.
