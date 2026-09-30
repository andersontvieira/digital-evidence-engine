# Milestone 8B2-A — PDF Toolchain Qualification & Foundation

Estado: COMPLETE — HUMAN REVIEW APPROVED. Qualificação sintética sob
[ADR 0038 Accepted](adr/0038-human-pdf-export-contract.md) e
[ADR 0039 Accepted](adr/0039-controlled-reportlab-adapter-private-coupling.md),
sem alterar suas decisões. 8B2-B não iniciada; 8B3 permanece futura.

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

Inventário: **35 distribuições identificadas**, **6093 hashes de payloads de
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
renderers finais não fazem parte desta qualificação.

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

## Limitações e fronteira

This is technical toolchain qualification, not legal advice.
No legal compliance certification. No PDF/A claim. No PDF/UA claim.
No digital-signature claim. No forensic certification. No real case used.

8B2-B has not started. Final dossier PDF has not been implemented.
Final consolidated-report PDF has not been implemented.
Sem serviço/CLI PDF, publicação de pdf-presentation-v1, pacote real, ZIP ou
execução 8B3. directory-v1 e schema v5 preservados. A qualificação é do perfil
sintético fechado e da imagem canônica; futuros slices devem qualificar suas
extensões de layout/validação. Sem promessa de rendering nativo multiplataforma.
