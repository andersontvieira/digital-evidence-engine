# ADR 0037 — Deterministic Dossier Assembly

Status: Accepted.

Milestone: 8B1 implementation contract (8B1.0, somente documentação).
Base do contrato: c39a757; implementação A–G concluída e validada sinteticamente.
Este ADR traduz o [ADR 0036 aceito](0036-final-legal-technical-dossier-export-contract.md) em contrato
de implementação aceito após revisão humana; não altera esse contrato nem autoriza
acesso a caso real. A fase contratual 8B1.0 está concluída, com promoção de README,
AGENTS e architecture. O fechamento de implementação 8B1-G e seus gates estão
registrados na seção 20. Execução real permanece reservada à futura 8B3, PDF à
8B2 e ZIP/archive a escopo separado. Esta tarefa não executa commit.

## 1. Escopo e auditoria do reuso

A 8B1 implementada monta localmente human/dossier.md, human/annex-index.md,
technical/selection-metadata.json, cópias de artefatos selecionados, JPEG/PNG
contextuais, integrity/manifest.json e integrity/SHA256SUMS.txt. As camadas
HUMAN LEGAL-TECHNICAL DOSSIER e TECHNICAL SUPPORT PACKAGE são organização e
apresentação acima do relatório consolidado; este permanece canônico.

Foram inspecionados AGENTS.md, README.md, docs/architecture.md, ADRs
[0032](0032-read-only-report-data-snapshot.md),
[0033](0033-first-consolidated-technical-report.md),
[0034](0034-exact-source-media-provenance-link.md),
[0035](0035-consolidated-report-media-link-integration.md) e 0036, além dos módulos
abaixo. A tabela preserva a auditoria histórica do contrato 8B1.0; as adaptações
foram implementadas nos slices A–F, com fechamento sintético em G.

| Implementação na base contratual | Decisão de implementação 8B1 |
| --- | --- |
| reports/consolidated.py: validate_snapshot, ConsolidatedReportModel, ReportWindow/Finding/Gap, render_markdown | Reusar validação e renderer puros; somente stdlib/EvidenceError. Não reconstruir fatos a partir de Markdown. |
| load_snapshots e consolidate_snapshots | Ambos aplicam MAX_SNAPSHOTS=20; loader também limita 64 MiB por arquivo. Separar guard operacional e núcleo puro conforme seção 5, sem copiar algoritmo nem alterar bytes legados. |
| JSON em reports/consolidated.py e ingest/parsing/framework.py | O primeiro usa json.loads com object_pairs_hook/parse_constant após cap de bytes; strict_json do segundo usa stdlib e checagens posteriores, admite BOM e não oferece todos os guards requeridos durante decode. Nenhum exige parser streaming próprio. Reusar primitives puras compatíveis, preservando rejeição de BOM e fronteiras de imports; estratégia da seção 8. |
| reports/snapshot.py | Produz snapshots acessando banco e mídia; não importar nem executar no dossiê. Consumir somente seus JSONs aprovados. |
| cli/report.py | Serializa JSON com ensure_ascii/sort_keys/separadores compactos e LF. Reusar a convenção, não importar o módulo, que também importa snapshot/SQLAlchemy/CaseRoot. |
| ingest/generic/hashing.py | original_reader, file_identity, read_stability e sha256_stream são primitives de filesystem sem DB. Reusar com escopo de artefatos, não CasePaths ou evidências. |
| ingest/generic/paths.py | check_path valida componentes, links/junctions e hardlinks; sync_directory é utilitário. Não chamar CasePaths.load ou discover. Reparse genérico/containment exigem checks adicionais explícitos. |
| ingest/generic/archives.py: validate_name | Policy de nome de membro ZIP permite dois-pontos lógicos. Não usar diretamente para destinos; dossiê recusa colon/ADS e não depende de ingestão ZIP. |
| media/signatures.py: identify | Primitive pura de prefixo limitado; útil como hint JPEG/PNG, insuficiente para validar bitstream completo. |
| media/perceptual.py: decode_hash | Importa catálogo/ORM e calcula pHash, portanto proibido. Usar Pillow já instalado apenas para validação limitada de formato/decode, sem chamar essa função. |
| reports/manifest.py | Acoplado a CasePaths/DB e usa replace; não reutilizar writer/modelo de manifesto de evidências para pacote. |
| errors.py: EvidenceError; cli/evidence.py: fail | Preservar formato ERROR e exit 2. Não importar cli.evidence para obter fail, pois traz serviços/DB; adaptador pequeno em cli/dossier.py. |
| cli/__init__.py | Agregador Typer carrega comandos existentes. Registrar futuro subcomando sem invocar os serviços desses comandos; separar teste de dependências do pacote e teste de execução da CLI. |

Não aceita --case-root nem lê CASE_ROOT; não abre evidence.db/SQLite,
originals/working, parsers, normalizers, observers, correlators, queries temporais
ou source-media. Sem novos F/W/G, findings, pHash, OCR, análise visual, identidade,
autoria, sessão ou causalidade. Sem rede/cloud/API/LLM. Somente seleção e arquivos
explicitamente referidos são lidos, além da releitura do próprio staging para
integridade. Não se consulta provenance externa para completar dado ausente.

## 2. CLI e resultado operacional

Comando contratado e implementado:

```console
dee dossier assemble --selection <selection.json> --output-dir <new-output-directory>
```

Exatamente essas duas opções de execução, obrigatórias e de ocorrência única;
--help segue Typer. Não há opção CASE_ROOT, variável de ambiente equivalente,
stdin (inclusive selection `-`), stdout-package, force/overwrite, recursive,
perfil por flag ou configuração implícita. Argumentos CLI de filesystem podem
ser locais absolutos ou relativos ao cwd; URI/rede/UNC são recusados. Isso não
autoriza paths absolutos dentro de input_reference ou do pacote.

selection deve ser arquivo regular existente; seu pai resolvido é a única base
de inputs, preparada pelo operador somente com artefatos de entrega e nunca
CASE_ROOT/originals/working. output-dir deve estar ausente, com pai existente e seguro. A base de
inputs e o output/staging não podem conter um ao outro. Cwd só resolve argumentos
explícitos, nunca descobre artefatos. Nenhum diretório do caso é montado/descoberto.

Sucesso: exit 0 e somente `DOSSIER_ASSEMBLY_OK` seguido de LF no stdout, após
publicação. Falha: exit 2 e `ERROR: DOSSIER_<CODE>` seguido de LF no stderr,
sem pacote stdout ou sucesso parcial; erros de sintaxe CLI também exit 2, com
diagnóstico sanitizado. Sem traceback, payload, valores de argumentos, paths,
hashes ou identificadores no diagnóstico padrão. Não usar mensagens str(OSError).

## 3. JSON exato de dossier.selection/1.0.0

Objeto JSON UTF-8 sem BOM, chaves únicas, sem NaN/Infinity. Tipos estritos:
não converter string em bool/número, nem bool em inteiro. Campos desconhecidos
falham em qualquer objeto de seleção; opcionais são omitidos, nunca null.
Não aparar, case-foldar ou normalizar silenciosamente valores. Ordem de chaves
JSON e ordem de listas de seleção não têm semântica. Listas opcionais omitidas
equivalem a vazias; ambas produzem a mesma metadata normalizada.

| Campo top-level | Tipo e regra exatos |
| --- | --- |
| policy_id | string obrigatória, exatamente dossier.selection. |
| policy_version | string obrigatória, exatamente 1.0.0. |
| delivery_profile | string obrigatória, exatamente directory-v1. |
| issued_date | string opcional, regex ASCII YYYY-MM-DD e data gregoriana válida, ano 0001–9999; sem timezone/default. Não é tempo de evidência nem de geração. |
| case_reference | string opcional, token opaco conforme regra de label abaixo; não é requisito de geração ou identificador de pessoa/parte/CPF/documento/processo/tribunal. |
| canonical_inputs | array obrigatório de itens canônicos: exatamente um consolidated_report e um ou mais report_snapshot. Sem máximo semântico de snapshots/janelas. |
| supplemental_inputs | array opcional de itens SUPPLEMENTAL_TECHNICAL. |
| validation_artifacts | array opcional de itens VALIDATION_ARTIFACT. |
| visual_exhibits | array opcional de itens VISUAL_EXHIBIT. |

Exemplo mínimo inteiramente sintético; os arquivos referidos não são criados
por este ADR. A versão/papel declarados não dispensam validar seus bytes:

```json
{
  "policy_id": "dossier.selection",
  "policy_version": "1.0.0",
  "delivery_profile": "directory-v1",
  "canonical_inputs": [
    {
      "input_reference": "inputs/synthetic-report.md",
      "local_label": "report",
      "source_class": "CANONICAL_TECHNICAL",
      "role": "consolidated_report"
    },
    {
      "input_reference": "inputs/synthetic-anchor.json",
      "local_label": "anchor",
      "source_class": "CANONICAL_TECHNICAL",
      "role": "report_snapshot"
    }
  ]
}
```

Cada item de qualquer lista tem exatamente quatro campos obrigatórios string:
input_reference, local_label, source_class, role; e somente expected_sha256
opcional, string com regex `[0-9a-f]{64}`. Hash declarado aplica-se a qualquer
papel permitido, sempre aos bytes originais selecionados; maiúscula/hash malformado
é INVALID_SELECTION, divergência é HASH_MISMATCH. Não há coerção ou hash de texto
normalizado. O visual acrescenta exatamente os três campos obrigatórios abaixo;
eles são proibidos nos outros papéis.

```json
{
  "input_reference": "inputs/synthetic-exhibit.png",
  "local_label": "visual-a",
  "source_class": "VISUAL_EXHIBIT",
  "role": "contextual_visual",
  "display_caption": "Imagem sintética para contexto.",
  "operator_selected": true,
  "display_approved": true
}
```

local_label e case_reference: fullmatch ASCII `[a-z][a-z0-9-]{0,47}`. Rejeitar
também fullmatch `[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}`
(forma textual completa de UUID) e qualquer substring que corresponda a
`[0-9a-f]{32,}` (32 ou mais caracteres hexadecimais minúsculos consecutivos).
Esses padrões são literais, sem case-fold, normalização ou heurística adicional.
Não derivar tokens de filename, pessoa, relógio ou UUID. Validação sintática não
estabelece ausência de significado pessoal: a revisão de privacidade do operador
continua responsável pela exposição semântica e pelas restrições do ADR 0036.
Não implementar detector de nomes/pessoas/partes nem inferência heurística de
identidade ou de significado pessoal de tokens.
case_reference não permite person_name/client_name/party_name/CPF/process_number/
court/jurisdiction como novos campos. Sem ele e sem issued_date, seção 1 continua
completa com título, contrato, perfil e policies canônicas, sem substituto inventado.

display_caption: string NFC, 1–500 code points Unicode, pelo menos um caractere
não whitespace, sem whitespace inicial/final, newline/controles/surrogates/bidi
controls, HTML, Markdown ativo ou links/URIs. Validar e rejeitar, não reparar.
operator_selected e display_approved são bool literal true, nunca 1 ou "true".
A aprovação indica revisão humana da exposição, não veracidade da legenda.
Campo de aprovação ausente ou bool false é PRIVACY_CONTRACT_VIOLATION; tipo
diferente de bool (inclusive null) é INVALID_SELECTION. Não aplicar heurística
semântica à legenda para decidir se uma afirmação é verdadeira.

## 4. Classes, papéis, duplicatas e ordem

| Lista | source_class | role | Formato validado | Destino relativo |
| --- | --- | --- | --- | --- |
| canonical_inputs | CANONICAL_TECHNICAL | consolidated_report | Markdown UTF-8 canônico 1.1.0 | technical/canonical/consolidated-report.md |
| canonical_inputs | CANONICAL_TECHNICAL | report_snapshot | JSON report.data_snapshot/1.1.0 | technical/canonical/snapshots/<local_label>.json |
| supplemental_inputs | SUPPLEMENTAL_TECHNICAL | technical_review | Markdown UTF-8 opaco | technical/supplemental/<local_label>.md |
| supplemental_inputs | SUPPLEMENTAL_TECHNICAL | structured_support | JSON estrito, sem mineração semântica | technical/structured/<local_label>.json |
| validation_artifacts | VALIDATION_ARTIFACT | validation_report | Markdown UTF-8 opaco | technical/validation/<local_label>.md |
| visual_exhibits | VISUAL_EXHIBIT | contextual_visual | JPEG ou PNG | exhibits/visual/<local_label>.jpg ou .png |

Combinação diferente, inclusive item na lista errada, é INVALID_ROLE_CLASS.
ORIGINAL_EVIDENCE e LEGACY_MANUAL_WORK_PRODUCT são recusados em v1, mesmo com
seleção explícita. Não reclassificar pela extensão. Nenhum item pode ter classes
múltiplas; generated classes são exclusivas de outputs gerados, não inputs.

Labels são únicos globalmente; input_reference duplicado, colisão case-fold de
referências, alias por identidade de arquivo e conflitos de papel falham.
Mesmos bytes em arquivos distintos com labels distintos não são deduplicados;
preservam ambas as fontes de entrega, sem afirmar independência probatória.

Seleção normalizada/metadata: ordem lexicográfica ASCII por (role, local_label),
como ADR 0036. Índice de anexos agrupa classes nesta ordem fixa:
CANONICAL_TECHNICAL, SUPPLEMENTAL_TECHNICAL, VALIDATION_ARTIFACT, VISUAL_EXHIBIT;
dentro de cada grupo ordena (role, local_label). Manifesto e sums ordenam por
package_path ASCII. Janelas/findings mantêm a ordem canônica do renderer,
independente dessas ordens administrativas. Arrays internos de inputs não mudam.

## 5. Conjunto canônico e comparação obrigatória do relatório

Exatamente um report.consolidated/1.1.0 Markdown e o conjunto completo compatível
de report.data_snapshot/1.1.0: um anchor analysis_window=null e zero ou mais
snapshots com janela. Não há máximo semântico de janelas ou omissão silenciosa.
Todos os snapshots selecionados entram na validação, no modelo e no pacote.
Não particionar conjuntos para burlar budgets ou concatenar relatórios parciais.

Normativamente, conjunto completo compatível significa todos os inputs
report.data_snapshot/1.1.0 declarados/selecionados como suporte canônico do
report.consolidated/1.1.0 selecionado: um anchor e zero ou mais analysis_window
únicas e compatíveis, cuja renderização pura coincide byte a byte com o relatório
fornecido. A montagem estabelece somente completude interna e compatibilidade
desse pacote selecionado. Não afirma que inexistam outras janelas fora dos
artefatos fornecidos, que todas as janelas possíveis do caso foram geradas ou
que o pacote seja completo em relação ao caso real. Omissão de janela necessária
ao relatório fornecido deve falhar na validação canônica ou comparação de bytes.
Nenhuma janela canônica selecionada pode ser descartada silenciosamente; não há
CASE_ROOT, DB ou descoberta para buscar um universo externo de janelas.

Reutilizar validate_snapshot e todas as validações de conjunto ADRs 0033/0035:
versões homogêneas, schema v5, case_id/engine_version iguais, igualdade case-wide
de policies/inventory/coverage/current_events/exact_candidates/media/gap inputs
aplicáveis, cópias de duplicatas e limitações, um anchor, janelas únicas e ordem
canônica start/end/platform/event_kind/max_delta_seconds. Não avaliar igualdade
pelo nome do arquivo. Versão 1.0.0 ou futura é rejeitada no dossiê, sem alterar
suporte histórico dos outros comandos. Ausência de capacidade não é fallback.

Adaptação implementada em reports/consolidated.py, conforme contrato: extrair
build_consolidated_model(snapshots) com o corpo atual de validação/modelagem,
sem o guard MAX_SNAPSHOTS; validar não vazio e todo o restante integralmente.
consolidate_snapshots mantém o guard operacional público atual e delega ao
mesmo núcleo. load_snapshots/consolidated_report e a CLI report conservam seus
limites e bytes legados. Extrair também decode_snapshot(content: bytes), que
reutiliza JSON estrito/validate_snapshot; loader antigo e dossiê compartilham
essa primitive. Dossiê usa leitura estável própria de artefatos e budgets da
seção 8, nunca o loader de paths limitado a 20 nem monkeypatch de constantes.
Essa separação foi implementada em 8B1-B sob este contrato aceito.
Testes de paridade do núcleo antigo/novo permanecem obrigatórios.

Pipeline obrigatório: carregar bytes estáveis → decodificar/validar snapshots →
build_consolidated_model → render_markdown(model).encode("utf-8") → comparar com
os bytes estáveis do relatório selecionado. Qualquer byte diferente, inclusive
BOM, CRLF, espaço ou LF final, é CANONICAL_REPORT_MISMATCH. Copiar o relatório
fornecido preservado, não substituir pela renderização de conferência.

Nunca parsear/minerar o Markdown consolidado para obter fatos. O modelo puro
reproduz os F/W/G já representados pelo relatório aprovado; a montagem não cria
IDs adicionais ou outro conjunto de findings. Modelos ou snapshots não chegam
da seleção como objetos confiáveis: sempre são construídos/validados internamente.
A igualdade prova compatibilidade interna, não autenticidade externa, completude
da custódia ou verdade. Não executa 8A1, verify de evidências ou consultas ao DB.

## 6. Paths seguros e leitura estável

input_reference: caminho POSIX relativo, UTF-8/NFC obrigatório sem normalização.
Recusar absoluto, drive/UNC, barra invertida, dot/dot-dot, componente vazio,
NUL/controles, colon/ADS, caracteres `< > " | ? *`, trailing dot/espaço e nomes
Windows reservados (inclusive variantes numeradas/sobrescritas da Foundation).
Recusar segmentos que colidam por case-fold e prefixos arquivo/diretório.
URL percent-encoding não é decodificado; a entrada nunca é tratada como URI.

Validar todos os componentes antes de resolve, usando check_path mais lstat/
FILE_ATTRIBUTE_REPARSE_POINT onde aplicável. Recusar symlink, junction, todo
reparse point, hardlink de arquivo (st_nlink>1) e tipo não regular. Conferir
containment após resolução e identidade path/handle; parents/output parent
também são verificados antes/depois. Não enumerar inputs nem seguir referências
dentro de JSON/Markdown/imagem; não ler .git/CASE_ROOT para inferir seleção.
Recusar antes de abrir referência cujo componente case-fold seja originals ou
working, ou cujo basename case-fold seja evidence.db; mesma proibição para os
componentes do caminho da seleção/base. Isso é bloqueio estrutural de áreas
proibidas, não descoberta de caso nem detector universal de evidência renomeada.
Seleção não pode selecionar a si própria. Não aceitar input/output/staging
sobrepostos ou aliases físicos. Área de entrega real deve ser preparada fora
do Git pelo operador; isso não exige abrir um caso.

Cada input, inclusive selection.json, passa por original_reader como primitive
genérica da Foundation; seu nome não o classifica como ORIGINAL_EVIDENCE.
Reusar identidade (dev, ino, tipo), size/mtime e ctime POSIX; Windows não usa
ctime/birthtime como invariante de mutação. Conferir path/handle e contagem dos
bytes lidos; rejeitar mudanças de modo/permissões observáveis, sem ajustá-las.
Mapear falhas para códigos dossier seguros. Não registrar mensagens cruas dos
helpers, restaurar timestamps ou prometer atime preservado pelo host.

Ler em chunks limitados, calcular SHA-256 e gravar os mesmos chunks num arquivo
exclusivo do staging. Fechar o contexto estável com sucesso antes de aceitar
essa cópia. A leitura da seleção pode usar buffer limitado antes do staging.
Capturar a baseline de todos os inputs antes da cópia; revalidar identidade/
estabilidade ao final da fase de cópia. Detecção de mudança invalida tudo.
Depois disso, parsing, comparação do report e geração usam somente os bytes
capturados, nunca reabrem a fonte para copiar uma versão diferente. Revalidar
hash/tamanho dos payloads do staging antes da publicação. Não alegar snapshot
atômico de todos os inputs ou imutabilidade futura das fontes.

## 7. Formatos e visuais

Markdown suplementar/validação: UTF-8 estrito sem BOM/NUL; conteúdo opaco, inclusive
se usar CRLF. Não parsear headings, links ou texto para narrativa. JSON de suporte:
UTF-8 estrito sem BOM, sem chaves duplicadas/NaN/Infinity, sujeito aos budgets;
qualquer valor JSON válido é permitido na raiz, mas jamais analisado como fato.
Somente seleção tem o schema fechado aqui definido; snapshot mantém o validador
contratado existente. Todos os payloads copiados conservam bytes e line endings.

VISUAL_EXHIBIT só JPEG/PNG. identify(prefix limitado) deve indicar JPEG/PNG e
Pillow, já presente no lockfile, deve confirmar o mesmo formato, dimensões
válidas e um único frame. Abrir a cópia estável com allowlist JPEG/PNG, executar
verify e reabrir para load completo, mantendo limites da seção 8 e tratamento
de warnings/bombas. APNG/multiframe não é admitido em v1. Truncamento ou assinatura
sem estrutura decodificável é UNSUPPORTED_FORMAT; excesso de tamanho/pixels é
RESOURCE_LIMIT. Extensão do input não decide formato. JPEG mapeia para .jpg e
PNG para .png sem mudar bytes. PDF, ainda que renomeado .jpg, é recusado.

Decode é verificação de formato, não análise visual: não classificar pixels,
extrair pessoas/objetos/texto, orientar, normalizar cores, stripping EXIF,
reescrever imagem ou calcular pHash. Não importar decode_hash nem inventory.
Limites reduzem consumo, não tornam Pillow sandbox ou certificam ausência de
conteúdo malicioso; não há sanitização/garantia de anonimato de metadados.
Nenhuma dependência nova. Revisão humana de exposição continua obrigatória.

## 8. Budgets operacionais da implementação v1

Defaults fixos, não derivados de caso real. Não acrescentar campos de limites
à seleção ou flags v1; mudanças exigem revisão de implementação e testes,
sem mudar a semântica do conjunto canônico. MiB significa 1024 × 1024 bytes.

| Recurso | Limite operacional fixo |
| --- | --- |
| selection.json | 1 MiB |
| Total de itens selecionados, todas as listas | 256 |
| Snapshot individual | 64 MiB, mantendo o budget de bytes do loader atual |
| Soma dos bytes de snapshots | 128 MiB |
| Relatório consolidado selecionado | 64 MiB |
| Arquivo supplemental/validation individual | 16 MiB |
| Total de supplemental_inputs | 64 itens, somando seus dois papéis |
| Total de validation_artifacts | 32 itens |
| Visual individual / total de visuais | 32 MiB / 32 itens |
| Pixels e dimensão de cada imagem | 16 milhões de pixels e 16384 pixels por eixo; ambos aplicáveis |
| Total de bytes de todos os inputs selecionados | 512 MiB, sem contar seleção |
| display_caption | 500 code points Unicode |
| input_reference | 1024 bytes UTF-8, até 32 componentes, até 255 bytes por componente |
| JSON: profundidade / nós | 64 containers aninhados; 1000000 nós por arquivo e 2000000 no conjunto decodificado |
| JSON: número individual | Até 128 caracteres de representação lexical, sem valores não finitos |
| Cada arquivo gerado, inclusive render de conferência | 64 MiB |
| Total final de bytes do pacote | 1 GiB |

Nó JSON é cada valor (inclusive container) e cada chave. Sempre impor o cap de
bytes antes do decode e durante a captura, por stat e stream, inclusive para
detectar crescimento. Reusar primitive JSON estrita existente se satisfizer os
guards de decode sem importar serviços proibidos. Caso contrário, usar json.loads
da stdlib com object_pairs_hook para rejeitar chaves duplicadas, parse_constant
para rejeitar NaN/Infinity e parse_int/parse_float para limitar lexemas a 128
caracteres antes da conversão e rejeitar resultados não finitos, inclusive overflow.
Imediatamente após decode, antes de validação/modelagem/projeção, percorrer a
estrutura com travessia limitada, preferencialmente iterativa, para checar
profundidade e nós por arquivo/agregados, interrompendo no primeiro excesso.
Tudo permanece sob os caps de bytes já impostos. Reusar comportamento mais forte
se disponível e compatível; não adicionar dependência nem escrever parser JSON
streaming/customizado de propósito geral somente para impor esses guards.
Um visual é decodificado por vez; snapshots/modelo podem ficar em memória somente
sob os budgets, liberando buffers redundantes. Limites de geração são verificados
durante montagem de linhas/saída, antes de formar um string ilimitado. Reutilização
do renderer requer guard de saída compartilhado no núcleo puro, preservando
bytes e comportamento público legado quando dentro dos limites.

Esses valores delimitam uma primeira execução local revisável: seleção pequena,
controle de memória na modelagem/deepcopy e de disco nas cópias/staging; não são
limiares probatórios. MemoryError/RecursionError decorrente de exaustão é tratado
como DOSSIER_RESOURCE_LIMIT, inclusive durante decode/travessia, sem traceback ou
saída parcial. O decode stdlib limitado por bytes pode alocar mais memória que o
input bruto antes da checagem estrutural; os limites são guardas operacionais,
não garantia exata de memória do processo. A adaptação dossier não deve converter
RecursionError em erro de JSON inválido como faz o loader legado; preservar o
comportamento público legado e distinguir exaustão na nova fronteira.

Não há teste `windows <= N` de validade semântica. Conjunto compatível que
ultrapasse qualquer budget falha explicitamente com DOSSIER_RESOURCE_LIMIT;
nunca CANONICAL_SET_INVALID, truncamento ou remoção de janela. Após revisão de
budgets, o mesmo conjunto pode ser processado sem mudança de significado.

## 9. Projeção humana e fontes das 14 seções

Título fixo: Dossiê Técnico de Organização de Evidências Digitais. Exatamente
14 headings `## N. Título`, nesta ordem. Subheadings não mudam a contagem.
M significa ConsolidatedReportModel construído a partir dos snapshots; S é o
conjunto validado e ordenado; A é o anchor. Metadata da seleção só identifica
o documento ou indexa material; não é fonte de narrativa técnica. A tabela
abaixo é allowlist de consumo, não licença para percorrer outros campos.

| N | Título fixo | Dados permitidos e apresentação |
| --- | --- | --- |
| 1 | Identificação do documento | Título, perfil/policy de seleção, M.metadata (policies/versões/schema/engine), issued_date/case_reference se presentes. Sem case_id ou identidade inventada. |
| 2 | Finalidade | Template fixo de organização técnica para revisão humana, sem advocacy; nenhuma extração de texto de input. |
| 3 | Escopo e limitações | M.windows.scope, truncated_components, M.limitations e contexto das policies selecionadas. Não buscar fontes para preencher lacunas. |
| 4 | Fontes e materiais técnicos | M.evidence_scope, M.coverage.parser_runs com unidades; labels/classes/roles do índice só para listar materiais, sem resumir prosa suplementar. |
| 5 | Metodologia técnica | M.methodology, policy/version e templates fixos sobre consistência/limites. Disponibilidade de policy não é execução; não alegar verify novo. |
| 6 | Cronologia técnica relevante | Por W-ID canônico, itens existentes de S.analysis_window.incident_window.items: occurred_at_utc, platform, event_kind e posição lógica. M.windows.scope/component_counts preservam limites. Sem corpo de mensagem, ID de evento ou união entre janelas. |
| 7 | Atividades digitais relevantes | M.technical_counts.current_events.by_platform_event_kind, seus total/dated/undated; todos os M.findings já existentes, na ordem aprovada, com F-ID, classe, statement, base, referência e limitações. Não selecionar por força. |
| 8 | Relações técnicas entre fontes e mídias | Referências aos M.findings do tipo source_media_provenance_link já apresentados; M.windows.component_counts.source_media_links e status_counts; M.media_summary e limitações aprovadas. Não gerar segundo finding. |
| 9 | Comunicações e anexos | Somente entradas de current_events.by_platform_event_kind cujo event_kind é literalmente communication.message e seus counts já existentes; limites fixos SOURCE_LIMITATION/WhatsApp. Não ler payloads, sender, thread ou captions. |
| 10 | Contexto técnico de dispositivos | M.coverage.device_observations, M.technical_counts.exact_candidates.device e limitações canônicas associadas, com unidades e escopos preservados. Sem total global de supports ou valores de dispositivos/modelos ausentes dessas projeções. |
| 11 | Contexto técnico de rede | M.coverage.network_observations, M.technical_counts.exact_candidates.network e limitações canônicas associadas; sem total global de supports, IP, geolocalização, sessão ou atribuição. |
| 12 | Atividades e alterações de conta | Entradas já existentes de current_events.by_platform_event_kind e incident items com igualdade literal a account.profile_activity, account.security_activity, account.change ou account.sign_on. Copiar contagens por classe sem somar unidades nem inferir dono/ação além do event kind. |
| 13 | O que os dados estabelecem e o que não estabelecem | Templates da seção 10 deste ADR sobre M.findings/windows/limitations/gaps; nenhuma avaliação probatória nova. |
| 14 | Mapa de provenance e índice de anexos | M.technical_reference_map e mapa Anchor/W-ID → local_label/package_path dos snapshots; ponteiros aos componentes apresentados e link fixo ao annex-index. Nenhum locator/hash/ID persistido impresso. |

exact_candidates.supports.total fica inteiramente fora da projeção humana v1;
permanece disponível nos artefatos técnicos canônicos copiados. Não derivar
contagens de supports por device/network nem interpretar o total como peso
probatório. Isso não remove bases ou referências de findings canônicos existentes.

Quando faltar dado aprovado em uma seção temática, usar exatamente:
“Os artefatos canônicos selecionados não fornecem dados aprovados para esta
seção; isso não demonstra ausência de atividade fora desse escopo.”
O template é uma única frase/linha no output. Seções fixas de identificação,
finalidade e metodologia continuam completas sem opcionais. Sem janela, não
inventar cronologia. Undated permanece contagem/limitação, nunca data estimada.

Cronologia conserva agrupamento por janela e ordem dos itens do snapshot,
com desempate implícito pela posição original; não calcula pares ou uma timeline
global, não deduplica eventos repetidos em janelas sobrepostas, não cria row_id
ou F-ID. Referência de linha é W-ID mais
`analysis_window.incident_window.items[N]`, posição já existente. F/W/G do modelo
são reusados literalmente; não gerados ou renumerados pelo projeto do dossiê.
Não há conversão temporal nova: UTC/timezone/raw ambíguos mantêm os limites do
artefato de origem e acesso via suporte, sem renderizar campos pessoais raw.

Campos técnicos de evento agora apresentados devem passar pelas mesmas regras
de display seguro do renderer (_technical/_utc ou primitives puras extraídas),
antes de interpolação. validate_snapshot sozinho não garante que todo campo
interno seja seguro para nova superfície humana. Strings statement/limitations
só podem vir do modelo recém-construído pelos templates aprovados, não de texto
livre no JSON ou relatório Markdown. Source locators, observation IDs, UUIDs e
hashes servem internamente para validar referências; jamais viram display.

Suplementos/validações/visuais/captions não entram na projeção técnica. Alterar
seus bytes, mantendo seleção e validade, não muda dossier.md; mudar sua seleção
pode mudar somente a listagem administrativa da seção 4/índice, não F/W/G,
cronologia, contagens, relações source-media ou classificação epistemológica.
Caption aparece somente no índice em v1, nunca no dossier.md ou seção 13.

## 10. Seção 13 e limites das afirmações

Projeção determinística, não nova avaliação de evidência. Renderizar referências
aos findings e classes de evento já apresentados, com wording fixo como:
“Os artefatos canônicos selecionados representam os achados referenciados neste
dossiê, dentro dos escopos e prefixos declarados.” Para source-media, reproduzir
o estado/limitação já aprovado do modelo (inclusive Gap D parcial), sem concluir
vínculo fora do conjunto. Não transformar zero returned em ausência na realidade.

Sempre manter limites fixos: dados não estabelecem identidade humana, autoria,
propriedade de conta/dispositivo, sessão, causalidade ou conclusão jurídica;
attachments não resolvidos permanecem SOURCE_LIMITATION. WhatsApp está fora do
dataset representado e condicional a futura aquisição/parser/análise aprovada.
Não inferir WhatsApp por Meta/Instagram, datas, contatos ou mídia, nem criar
SPECIFIC_TECHNICAL_BASIS. REPORTED/HYPOTHESIS não são promovidos a fato.

Preservar SOURCE_MEDIA_LIMITATION: occurrence_count significa ocorrências
catalogadas do conteúdo, não envios/publicações/destinatários/ações; member-only
significa membro verificado sem correspondente na policy de ExactMediaContent,
não formato/vídeo/invalidade. Link não estabelece upload/envio/exclusão/autoria.
Não resolver message attachments por tempo, thread, sender, device, rede, ordem,
basename, pHash, visual ou filename. Não somar supports como força probatória.

Proibidos forte/fraco, score/ranking/confidence, culpa/inocência, intenção,
responsabilidade, suficiência jurídica, admissibilidade, autoria provável ou
“pessoa operou dispositivo”. Revisão civil/criminal usa o mesmo núcleo neutro.
Jurista combina documentos externos e argumentos fora do motor. O resumo de
integridade só explica o mecanismo do pacote; não lê prosa de validação para
afirmar integridade de originais ou autenticidade antes da aquisição.

## 11. Índice de anexos e metadata da seleção

annex-index.md lista cada artefato selecionado copiado exatamente uma vez:
local_label, role, source_class, package_path relativo e descrição fixa por role.
Grupos/ordem seguem seção 4. Descrições congeladas:

| role | Descrição de finalidade limitada |
| --- | --- |
| consolidated_report | Relatório técnico canônico detalhado. |
| report_snapshot | Snapshot canônico de suporte ao relatório. |
| technical_review | Revisão técnica suplementar separada, sem alimentar a narrativa canônica. |
| structured_support | Suporte estruturado suplementar separado, sem alimentar a narrativa canônica. |
| validation_report | Artefato de validação separado; sua inclusão não cria conclusão técnica. |
| contextual_visual | Imagem selecionada para visualização contextual, sem vínculo automático com evento ou finding. |

Visuais têm display_caption somente em bloco contextual adjacente a este aviso
fixo, separado das tabelas técnicas e obrigatório a cada legenda exibida:
“Legenda contextual fornecida pelo operador — não constitui finding técnico.”
Não avaliar semanticamente a verdade da legenda nem transformá-la em provenance.
Não incluir imagens inline automaticamente; o índice referencia o arquivo local.
Nunca imprimir input_reference, nome original, host path, hash ou ID sensível.
Uma lista administrativa separada referencia os outputs gerados e integrity/,
sem lhes inventar local_label de seleção ou confundi-los com fontes canônicas.

technical/selection-metadata.json é objeto de campos exatos:

| Campo | Tipo/regra |
| --- | --- |
| policy_id | string dossier.selection. |
| policy_version | string 1.0.0. |
| delivery_profile | string directory-v1. |
| issued_date / case_reference | Mesmas strings opcionais validadas, presentes somente se fornecidas. |
| items | Array obrigatório de todos os selecionados, ordenado por (role, local_label). |

Cada item de metadata contém exatamente local_label, source_class, role e
package_path (strings); itens visuais acrescentam exatamente display_caption,
operator_selected=true e display_approved=true. Não há outro display_options bag.
expected_sha256 não é copiado: foi pré-condição conferida; SHA dos bytes finais
fica no manifesto. Sem input_reference, filename original, identidade pessoal,
clock, UUID, generated_at ou path operacional. Não copiar a seleção original.
Essa metadata é projeção administrativa, não finding ou novo contrato de evidência.

## 12. Layout, serialização e manifesto exatos

Raiz é o output-dir explícito; `package` abaixo é placeholder neutro, não um
diretório adicional obrigatório. Labels do operador são a única parte variável
dos nomes de payloads; somente extensão é derivada do formato visual validado.

```text
package/
  human/dossier.md
  human/annex-index.md
  technical/canonical/consolidated-report.md
  technical/canonical/snapshots/<local_label>.json
  technical/supplemental/<local_label>.md
  technical/structured/<local_label>.json
  technical/validation/<local_label>.md
  technical/selection-metadata.json
  exhibits/visual/<local_label>.jpg|png
  integrity/manifest.json
  integrity/SHA256SUMS.txt
```

Nenhum diretório vazio opcional é exigido. Rejeitar path duplicado/case-fold/
prefixo arquivo-diretório antes de criar arquivos. Nunca usar filename de origem.
Extensão .jpg para JPEG e .png para PNG só muda o destino, não bytes/metadados.
Sem PDF gerado, ZIP, logs extras ou selection.json original dentro do pacote.

Textos gerados: UTF-8 sem BOM, LF e exatamente um LF final, templates pt-BR
fixos. Datas/inteiros em representação contratada, sem locale ou data atual.
Escaping por contexto de célula/texto: primeiro `&`, `<`, `>` para entidades;
backslash, backtick, asterisco, underscore, chaves, colchetes, parênteses, hash,
pipe e exclamation recebem escape Markdown literal. Não permitir quebra de
linha, controle/bidi ou links ativos em valores livres; captions com sintaxe
de link/HTML/URI são rejeitadas, não interpretadas. Links internos são construídos
somente dos package_paths gerados, relativos à localização do documento humano.
Statements do modelo são tratados como texto, não template executável. O renderer
canônico de conferência mantém seu escaping próprio, sem alterar bytes legados.

JSON gerado, tanto metadata quanto manifesto: bytes de
`json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)`
mais LF, UTF-8 (ASCII subset), sem BOM. Arrays seguem suas ordens contratadas;
inteiros de tamanho/contagem são int exato não negativo, nunca bool/float.
Nenhum relógio, UUID ou metadata do filesystem contribui para bytes gerados.

Manifesto exato: objeto com somente policy_id="dossier.package_manifest",
policy_version="1.0.0" e entries (array ordenado por package_path).
Cada entry tem somente package_path, role, source_class, byte_size, sha256 e,
quando copiada de item selecionado, local_label. Os primeiros três e sha256 são
strings; sha256 é 64 dígitos hexadecimais minúsculos; byte_size é int exato >=0.
local_label é obrigatório nas cópias selecionadas e ausente nos gerados.

| Arquivo gerado | role | source_class |
| --- | --- | --- |
| human/dossier.md | human_dossier | GENERATED_PRESENTATION |
| human/annex-index.md | annex_index | GENERATED_PRESENTATION |
| technical/selection-metadata.json | selection_metadata | GENERATED_METADATA |

Copiados usam exatamente a classe/papel/label da seleção aprovada. Generated
classes descrevem origem de entrega, não classificação epistemológica.
Não criar campos opcionais além de local_label, nem engine_version/host/date
extras. O manifesto não certifica autenticidade, autoria ou validade jurídica.

P é todo arquivo final exceto integrity/manifest.json e integrity/SHA256SUMS.txt.
Manifesto contém exatamente uma entry por arquivo de P. SHA256SUMS cobre P mais
integrity/manifest.json, excluindo somente a si próprio. Linhas exatas:

```text
<lowercase_sha256><two ASCII spaces><package_path><LF>
```

Ordenação ASCII por package_path; UTF-8/LF/final LF; sem paths absolutos, linhas
extras ou escapes dependentes de host. Hashes sempre sobre bytes empacotados.
Gerar payloads → manifesto → sums, nunca ciclo recursivo. Modificação coordenada
de conteúdo/manifesto/sums exige baseline externa para detecção; consistência
interna não é assinatura jurídica, custódia completa ou autenticidade anterior.

## 13. Staging, completude e publicação sem substituição

Fases fixas: validar seleção/paths/budgets e ausência do destino; criar staging
irmão no mesmo pai/filesystem; capturar/copiar inputs; validar formatos/conjunto/
report; projetar/renderizar; gerar metadata/manifesto/sums; verificar completude;
publicar uma única vez. Staging é diretório exclusivo criado pela execução com
permissões restritas, sem usar nomes de caso. Sufixo aleatório de tempfile é
apenas detalhe operacional anti-colisão, não UUID/identidade da seleção nem
conteúdo do pacote; não aparece em outputs ou diagnósticos.

Antes da publicação, verificar cumulativamente:

- cada input permitido foi copiado uma vez, SHA/tamanho e expected_sha256
  conferem; conjunto completo declarado/selecionado de snapshots e relatório
  compatível preservados conforme seção 5, sem omissão de janela selecionada;
- os três outputs gerados e os dois arquivos de integridade estão presentes;
- P real coincide exatamente com entries; não há payload não manifestado,
  entry sem arquivo, duplicata, link ou colisão de path;
- manifesto e sums correspondem aos bytes reais, incluindo hash do manifesto;
- dossiê tem exatamente 14 seções na ordem fixa; índice corresponde aos itens
  selecionados e referências de snapshots/F/W/G são resolvíveis no suporte;
- nenhum arquivo extra de scratch, log ou temporário entra na entrega.

Completude aqui é interna ao pacote selecionado; esses checks não atestam
ausência de janelas externas, geração de todas as janelas possíveis ou completude
do caso real. Janela necessária ao relatório fornecido omitida deve fazer falhar
a validação canônica ou a comparação byte a byte, antes de publicar.

Enumerar o staging controlado para verificar completude não é auto-discovery de
inputs. Abrir apenas caminhos esperados dentro dele, sem seguir links. Flush e
fsync dos arquivos antes de fechar; sincronizar diretórios POSIX quando suportado.
Revalidar identidade/segurança do staging e pai do destino antes de publicar.

Nunca usar replace, merge, cópia recursiva para o destino final, nem a sequência
insegura exists() seguida de rename substitutivo. O contrato requer primitiva
de rename/move de diretório no mesmo filesystem que falhe se o destino existir
no instante da operação. Em Linux, a implementação deverá usar renameat2 com
RENAME_NOREPLACE (wrapper stdlib/ctypes pequeno e testado); em Windows, os.rename
com semântica de destino existente recusado. Se plataforma/filesystem não oferecer
essa garantia, PUBLICATION_FAILURE antes de publicar; sem fallback substitutivo.
POSIX rename genérico pode substituir diretório vazio e não satisfaz sozinho
este contrato. Corrida criando destino deve resultar OUTPUT_EXISTS sem tocá-lo.

Windows pode negar move por handles abertos: fechar todos os handles de staging
antes da tentativa. Não prometer durabilidade de rename perante queda de energia,
nem atomicidade entre vários inputs, nem garantias de filesystem de rede; v1
suporta somente filesystem local com a primitiva contratada. Pai do output deve
ser controlado pelo operador; checks de path não equivalem a sandbox contra
administrador malicioso que reescreva o filesystem.

Falha anterior à publicação mantém final ausente se ele não foi criado por
terceiro; se terceiro criou destino, preservá-lo integralmente. Remover apenas
o staging comprovadamente criado pela execução, com identidade e containment
revalidados; nunca apagar preexistentes, inputs ou diretório publicado. Falha de
cleanup gera STAGING_FAILURE, preserva indicação segura da categoria original
sem path e nunca declara sucesso. Após o rename bem-sucedido não executar novos
gates ou escritas que convertam entrega válida em pacote parcial. Perda de
confirmação após publicação exige inspeção externa; não apagar/repetir/mesclar
automaticamente. Nenhuma promessa de transação distribuída com stdout.

## 14. Erros estáveis e ordem de validação

Todos os códigos abaixo recebem prefixo DOSSIER_ e são EvidenceError seguros.
Não serializar exceptions internas, SQL, input labels, hash ou paths no erro.
Primeira falha na ordem de fases da seção 13 encerra a operação; dentro de uma
fase, ordem administrativa canônica dos itens. Cleanup failure tem precedência
no código final, com categoria original segura opcional no diagnóstico.

| Código | Condição |
| --- | --- |
| INVALID_SELECTION | JSON/shape/tipo/chave desconhecida, data inválida, duplicata de label/reference, campos obrigatórios/opcionais inválidos. |
| UNSUPPORTED_POLICY_VERSION | policy_id/version/profile de seleção não suportados ou versão canônica diferente de 1.1.0. |
| INVALID_ROLE_CLASS | Classe/papel/lista incompatíveis, original/legacy ou generated class como input. |
| INVALID_PATH | Sintaxe não portátil, referência remota, componente de área proibida, conflito case-fold/prefixo/destino lógico. |
| PATH_ESCAPE | Resolução fora da base ou overlap input/output. |
| UNSAFE_FILE_TYPE | Link/junction/reparse/hardlink, tipo não regular ou componente inseguro. |
| UNSUPPORTED_FORMAT | Markdown/JSON não canônico por formato; JPEG/PNG inválido, multiframe ou PDF visual. JSON de seleção usa INVALID_SELECTION; JSON canônico malformado usa CANONICAL_SET_INVALID. |
| RESOURCE_LIMIT | Qualquer budget operacional, exaustão controlada ou tamanho superior ao permitido; não equivale a conjunto semanticamente inválido. |
| INPUT_CHANGED | Identidade, estabilidade ou tamanho lido divergente na captura/revalidação. |
| HASH_MISMATCH | Hash esperado divergente ou bytes copiados/reverificados não coincidem. |
| CANONICAL_SET_INVALID | Anchor ausente/múltiplo, janela duplicada, divergência case-wide, referências/policies/unidades/estrutura incompatíveis. |
| CANONICAL_REPORT_MISMATCH | Markdown selecionado diferente da renderização pura, inclusive versão declarada divergente no texto; não parsear o texto para diagnosticar. |
| PRIVACY_CONTRACT_VIOLATION | Valor de display/caption estruturalmente proibido, aprovação visual ausente/falsa ou tentativa de projetar campo fora da allowlist. |
| OUTPUT_EXISTS | Destino existente inicialmente ou criado antes do rename. |
| STAGING_FAILURE | Criar/escrever/flush/inspecionar/limpar staging falha; filesystem incapaz de manter as condições requeridas. |
| PUBLICATION_FAILURE | Move/rename não realizado, primitiva não suportada ou falha operacional de publicação. |
| INTERNAL_ERROR | Invariante de programação/completude quebrada ou erro inesperado, sem traceback/payload. |

Ausência/permissão de leitura de input exige adicional INPUT_READ_ERROR para
distinguir I/O de mudança detectada. O mesmo exit 2 se aplica. Adaptação de
REPORT_* preserva categoria: falha estrutural → CANONICAL_SET_INVALID;
display inseguro → PRIVACY_CONTRACT_VIOLATION; budgets → RESOURCE_LIMIT.
Versões mistas → CANONICAL_SET_INVALID; versões homogêneas não suportadas →
UNSUPPORTED_POLICY_VERSION. Não inferir versão de report a partir de Markdown;
compatibilidade com 1.1.0 é assegurada pela comparação byte a byte.

## 15. Fronteira de privacidade e determinismo

As projeções técnicas humanas não recebem UUID, SHA completo, IP, device ID,
cookie/token, email, telefone, path de host/member, mensagem raw ou filename
original. Isso vale para dossiê e campos técnicos do índice; a legenda contextual
fornecida/aprovada pelo operador é tratada separadamente abaixo, não como projeção
de campos técnicos. Metadados de seleção/manifesto só têm os campos autorizados.
Valores pessoais permitidos nos artefatos técnicos canônicos
permanecem nos bytes copiados sob seus contratos; não se espalham para prosa.
Não prometer que regex detecta nomes/pessoas ou todo conteúdo sensível.

Caption aprovada continua potencialmente identificável: display_approved=true,
escaping e aviso contextual não certificam anonimato/veracidade. Copiar Markdown
suplementar é preservar bytes, não aprovar sua narrativa ou remover links ativos
para uso por leitor externo. O motor não os resolve/renderiza; revisão de exposição
dos materiais selecionados é humana. Caso real, staging e pacote ficam fora do Git;
.gitignore não é controle de privacidade. Classificação explícita não consegue
detectar universalmente um original disfarçado de material suplementar.

Mesma versão de implementação/bibliotecas suportadas, mesmos bytes e mesma seleção/
configuração produzem dossier.md, annex-index.md, selection-metadata.json,
manifest.json e SHA256SUMS.txt byte-idênticos em Windows/Linux. Permutações das
listas de seleção mantêm resultado; não depende de enumeração, locale, clock,
UUID, paths absolutos ou metadata do host. Copiados são byte-idênticos aos inputs.
Não se promete metadata filesystem igual, determinismo PDF/ZIP, assinatura ou
autenticidade externa. Novas versões exigem comparação/revisão própria.

## 16. Módulos implementados e dependências testáveis

Layout mínimo decidido, sem framework/plugin ou classe genérica de exportação:

```text
src/evidence_engine/dossier/
  __init__.py
  selection.py
  validation.py
  projection.py
  rendering.py
  packaging.py
  integrity.py
  service.py
src/evidence_engine/cli/dossier.py
```

| Módulo | Responsabilidade exclusiva |
| --- | --- |
| selection.py | DTOs dataclass explícitos/imutáveis, JSON estrito e shape fechado, class/role/label/data/caption, ordens e budgets declarados. Sem filesystem/DB. |
| validation.py | Formatos de bytes capturados, limites de JSON/imagem, modelo canônico e comparação report/snapshots; Pillow bounded e pure reports. Sem CASE_ROOT. |
| projection.py | DTO de apresentação de 14 seções, mapeamento allowlist da seção 9; só seleção administrativa e modelo/snapshots validados. Sem I/O. |
| rendering.py | Templates pt-BR, escaping, dossier/index e serialização de metadata; recebe DTO seguro, não bytes de suplemento/visual. Sem I/O. |
| packaging.py | Resolução confinada, stable read/cópia, mapa paths, staging, cleanup e publicação por plataforma. Não interpreta achados. |
| integrity.py | SHA streaming/recheck, manifesto/sums e completude, serialização determinística; só bytes/paths do staging, sem catálogo. |
| service.py | Orquestra fases e budgets; retorna sucesso somente após publicação. Não replica validação/renderer. |
| cli/dossier.py | Typer, dois argumentos, chamada do serviço, erro sanitizado/exit 2; sem CaseRoot/fail importado de cli.evidence. |

Direção: CLI → service → módulos explícitos. selection/projection/rendering não
importam packaging/service; validation reusa reports.consolidated puro; integrity
não importa serviço nem banco. __init__ permanece sem side effects. Dossier não
importa storage, ORM, ingest services, normalization/observation/correlation/query,
reports.snapshot/manifest ou media.inventory/contents/perceptual/source_links.

Exceções de utilitários permitidas, nominais e transitivamente sem banco:
ingest.generic.hashing (original_reader, file_identity, read_stability,
sha256_stream), ingest.generic.paths (check_path, sync_directory),
media.signatures (identify), errors.EvidenceError, reports.consolidated puro,
stdlib e Pillow já instalado. Não acessar CasePaths/discover por essas exceções.
Nenhum import executa serviços ou faz I/O de caso. Não duplicar um leitor de
evidência concorrente: checks adicionais de path/reparse envolvem a primitive
Foundation, com testes adversariais, sem enfraquecer sua lógica por plataforma.

Teste de imports AST e teste de import isolado em subprocess verificam o grafo
de dossier. O agregador cli/__init__.py atualmente importa comandos legados que
dependem de DB; não alegar que o processo CLI inteiro é livre desses imports.
Teste separado do comando instrumenta DB/open/query/network para falhar caso
sejam executados, mesmo que já importados. Isolamento é dependência do pacote
mais ausência de execução proibida, sem refactor geral do bootstrap nesta etapa.

## 17. Matriz contratada de testes sintéticos

Este ADR não implementa testes. A matriz abaixo orientou os slices A–G;
as suítes implementadas cobrem os contratos com materiais inteiramente sintéticos, sem rede
nem fixture real, usando diretórios temporários separados da fonte do projeto.

| Área / arquivo de teste proposto | Casos e resultado obrigatório |
| --- | --- |
| test_dossier_selection.py | Seleção mínima, opcionais ausentes/vazios, unknown fields em todos os níveis, tipos/null/coerções, policy/version/profile, issued_date inválida, case_reference válido/inválido/ausente, permutações, labels/references duplicados e papéis/classes conflitantes. Fullmatch ASCII/UUID e substring hexadecimal nos limites 31/32; tokens sintéticos que satisfazem os padrões não sofrem rejeição heurística por suposto significado pessoal. Exatos códigos; sem descoberta ou detector de nomes. |
| test_dossier_canonical.py | Anchor único sem janela, uma/múltiplas janelas, ausência/múltiplos anchors, versões 1.0/mistas/futuras, duplicatas, metadata/case-wide/policies incoerentes, JSON inválido, report byte diferente e conjunto selecionado completo preservado. Omitir janela necessária mantendo o relatório fornecido falha. Janela sintética externa não selecionada não é descoberta nem permite alegação de completude do caso. Nenhum parsing de Markdown para fatos. |
| Regressão do núcleo puro de reports | Paridade antiga/nova byte a byte para 1.0.0/1.1.0 dentro do guard legado; conjunto sintético com mais que MAX_SNAPSHOTS processado pelo núcleo dossier sob budgets, sem perda/renumeração arbitrária. CLI legada mantém guard. Estourar budget gera RESOURCE_LIMIT, não erro semântico. |
| test_dossier_paths.py | Absoluto/drive/UNC/backslash/traversal/dot/vazio/NFC/controle/ADS/reservados; componentes originals/working e evidence.db recusados antes de open; case-fold/prefixos/aliases, symlink/junction/reparse/hardlink, escape por pai e output/input overlap; destino existente intacto. Windows-specific quando disponível, skips explícitos no outro host. |
| test_dossier_stability.py | Mutação durante abertura/hash/cópia e entre baseline/cópia; troca path/handle, esperado SHA errado, truncamento/crescimento, cópia exata com CRLF, POSIX ctime obrigatório e Windows ctime/atime observacionais. Sem restaurar metadata. |
| test_dossier_formats.py | Markdown/JSON válidos e inválidos, chave duplicada/NaN/BOM, JPEG/PNG íntegros, signature spoof/truncado/fake jpg, PDF visual, APNG/multiframe, bombs/dimensão/pixels e limites N/N+1 para bytes, itens, caption, JSON e saída. Sem pHash ou reescrita. |
| JSON estrito e budgets | Cap de bytes verificado antes de chamar decoder; duplicate keys/NaN/Infinity/overflow rejeitados pelos hooks; lexemas 128/129, profundidade 64/65 e nós individuais/agregados N/N+1. Travessia imediatamente após decode impede modelagem/projeção no excesso. MemoryError/RecursionError simulados no decode/travessia geram DOSSIER_RESOURCE_LIMIT sem publicação. Sem dependência ou parser customizado. |
| test_dossier_rendering.py | 14 headings exatos e ordem ADR 0036, seções vazias com limitação fixa, seção 1 sem opcionais, mapeamento explícito, F/W/G iguais ao modelo; todas as unidades/truncamentos; seção 13 sem avaliação probatória; source-media/member-only/occurrence_count/SOURCE_LIMITATION/WhatsApp preservados. |
| Projeção device/network | Seções 10/11 usam apenas cobertura/candidates respectivos e limitações; exact_candidates.supports.total ausente de toda projeção humana, preservado nos bytes técnicos. Não calcular supports por tipo nem peso probatório; bases de findings existentes preservadas. |
| Canonical-only adversarial | Textos suplementares/validações e captions com alegações sintéticas não mudam dossier.md, cronologia/findings/contagens/classes; mudar captions só altera índice/metadata e hashes correspondentes. Inclusão administrativa de material novo não muda narrativa técnica. LEGACY/ORIGINAL rejeitados. |
| test_dossier_privacy.py | Sentinelas sintéticas UUID/SHA/IP/email/telefone/device/path/member/raw-message não são projetadas dos snapshots em humanos; copied technical bytes preservados. Caption sempre com aprovação/aviso no índice, nunca seção 13/provenance; não prometer detector universal de texto pessoal. HTML/URI/markup ativo bloqueados, sem copiar hash/input_reference/host path para índice/metadata. SHA gerado somente no manifesto/sums técnicos. |
| test_dossier_integrity.py | P e sums completos, sha/tamanho correto, manifesto coberto por sums, regra acíclica, arquivo extra/ausente, entry duplicada/path conflitante, cópia exatamente uma vez, JSON e ordering determinísticos. |
| test_dossier_publication.py | Staging seguro/sucesso, falha de validação/write/fsync/final move/cleanup, destino existente ou criado em corrida (inclusive diretório vazio), primitiva indisponível, nenhum pacote parcial/merge/substituição, inputs/preexistentes intactos. |
| test_dossier_determinism.py | Repetição, permutação de seleção/enumeração, opcionais ausentes, clock/UUID/locale sentinelas, roots absolutos distintos com mesmos labels/bytes; paridade Windows/Linux para cinco outputs gerados e conjunto de paths. Metadata filesystem fora da comparação. |
| test_dossier_architecture.py e integração CLI | Import-boundary nominal/transitivo, comando sem --case-root/CASE_ROOT/stdin/stdout-package, sem DB/open evidence.db/originals/working/services/network/cloud/API/LLM; exits e mensagens sem payload/path/traceback; zero fixtures reais. |

Validar também que a extração do núcleo de reports não muda o comportamento
de snapshot/report antigos nem enfraquece SOURCE_MEDIA ou Foundation. Gates
funcionais de implementação só poderão ser declarados após execução, separados
de validação real futura 8B3.

## 18. Sequência de implementação e consequências

Slices dentro de 8B1, não milestones novas; todos implementados e validados:

1. 8B1-A: DTO/shape de seleção, JSON estrito sob cap de bytes com hooks e travessia
   estrutural limitada, class/role, paths e testes puros; sem parser customizado.
2. 8B1-B: extração mínima de primitives puras de reports, budgets e compatibilidade
   byte a byte; regressões legadas antes de depender do núcleo.
3. 8B1-C: projeção allowlist e templates de 14 seções/índice, privacidade e
   invariância diante de conteúdo suplementar.
4. 8B1-D: captura estável, cópias exatas, validação JPEG/PNG, layout/metadata.
5. 8B1-E: manifesto, sums e completude independente dos bytes efetivos.
6. 8B1-F: staging/cleanup/publicação por plataforma e CLI, sem substituição.
7. 8B1-G: regressões, paridade Windows/Linux, revisão de imports/privacidade e
   fechamento sintético. Promoção do estado de implementação somente após seus gates.

Preserva ADR 0033 como renderer puro/histórico e ADR 0035 como única ampliação
source-media aceita; ADR 0036 governa seleção, duas camadas, 14 seções, classes,
cardinalidade sem máximo semântico e hashes acíclicos. Recursos são guardas
operacionais explícitas. Schema permanece v5, sem tabela/run/migration ou cache
de análise. Há custo de memória do modelo e releitura do staging, além de revisão
manual dos materiais; não escondê-lo com inferência, truncamento ou fonte extra.

Fora de escopo: implementação nesta 8B1.0; PDF renderer/sanitizer/exhibit,
ZIP/archive, assinatura/ICP-Brasil, criptografia/transporte/upload/cloud/web,
dashboard, petições/estratégia/conclusões jurídicas, atribuição pessoa/dispositivo,
identity resolution, WhatsApp ingestion, pacote de originais e execução real.
8B2 e 8B3 continuam futuras e separadas; montagem não é autorização de investigação.

## 19. Validação deste contrato documental

Registro histórico da revisão 8B1.0, limitada a este ADR, código/documentação
existentes e exemplos sintéticos. Nenhum CASE_ROOT ou artefato real foi acessado. Nenhum comando, DTO,
schema, teste, fixture ou helper de produto foi implementado. Não houve mudança
de dependências/lockfiles. No fechamento formal, README, AGENTS e architecture
foram promovidos junto com Status: Accepted. O contrato está concluído; a
implementação ainda não havia começado naquele fechamento documental.
O estado implementado posterior consta na seção 20. Nenhuma aceitação autoriza
execução real nesta etapa.

Os gates funcionais de referência naquela entrega eram: pytest 1093 PASS;
Ruff check PASS; Ruff format PASS; mypy PASS em 70 módulos. Não foram reexecutados
por prosa documental com estado executável/test/config intacto. Whitespace/diff e
revisão de privacidade, compatibilidade e escopo foram os gates daquela entrega;
sem staging, commit ou push.

## 20. Fechamento sintético 8B1-G

Slices A–G implementados. Base de G: 9a06b53, árvore inicialmente limpa.
Sem alteração das decisões, versões de policy/seleção/manifesto, schema v5,
dependências ou lockfile. Status deste contrato permanece Accepted.

| Ambiente | Suíte completa | Tempo | Exit |
| --- | --- | --- | --- |
| Docker/Linux Python 3.12.14 | 1885 passed, 3 skipped | 664.37 s | 0 |
| Windows nativo Python 3.12.11 | 1864 passed, 24 skipped | 666.33 s | 0 |

Gates dirigidos: Linux 233 passed / 3 skipped; Windows 219 passed / 17 skipped.
Ruff check PASS; Ruff format PASS (180 arquivos); mypy PASS (79 arquivos fonte);
git diff --check PASS. Ambiente Windows existente, auditado por uv 0.8.22 contra
o lockfile sem mudanças necessárias; nenhum Python/software de sistema instalado.

Os três skips Linux são os dois testes reais de junction (paths e integrity) e
o teste real de publicação Windows. No Windows, os 24 skips são: seis em
test_case_paths (quatro symlinks sem permissão e dois FIFOs POSIX); cinco em
test_dossier_integrity (dois symlinks sem permissão, FIFO, UNIX socket e traversal
por descritor); cinco em test_dossier_paths (dois symlinks sem permissão, FIFO,
writer e unlink relativos a descritor); sete em test_dossier_publication
(renameat2 Linux, dois symlinks sem permissão, três fsync POSIX e corrida de
cleanup por descritor); um em test_foundation (backslash é separador Windows).
Os dois gates reais de junction Windows executaram e passaram, preservando o
alvo externo sintético. Os casos de symlink sem permissão executaram no Linux;
não se atribui execução nativa Windows a esses skips.

Publicação real Linux renameat2(RENAME_NOREPLACE) e Windows os.rename PASS,
incluindo destino existente preservado e staging movido somente no sucesso.
Não há fallback de replace/cópia. Testes de corrida, ownership/cleanup,
confirmação ambígua, precedência de falhas e ausência de I/O após publicação
permanecem aprovados. Sem promessa de atomicidade da captura ou durabilidade
do rename contra perda de energia.

A fixture de tests/test_dossier_cross_platform.py inclui um relatório, um anchor,
20 janelas, revisão Markdown com CRLF, suporte JSON, validação, PNG sintético de
bytes fixos, issued_date/case_reference explícitos e listas fora da ordem canônica.
São 31 arquivos: 26 payloads copiados e cinco gerados. Comparação independente
Windows/Linux PASS para todo o mapping relativo POSIX → SHA-256, congelado no teste.
Os cinco gerados, todos os payloads e o conjunto de paths coincidem; CRLF copiado
e PNG são preservados, gerados usam UTF-8/LF sem BOM. As 14 seções permanecem fixas.
O mapping não inclui paths do host, metadata de filesystem ou nomes de staging.

O gate nativo revelou CRLF na saída textual da CLI. A correção mínima em
cli/dossier.py emite bytes ASCII/LF tanto em sucesso quanto em erro, preservando
os códigos e exits. Help, montagem completa com 21 snapshots e erros seguros de
seleção inválida/destino existente passaram nas duas plataformas. O primeiro
comparativo também detectou PNGs diferentes gerados pelo encoder da fixture;
fixaram-se os bytes sintéticos de entrada, sem normalizar ou alterar o produto.

Imports nominais/testados e sentinelas de execução preservam a fronteira do
dossiê sem CASE_ROOT, descoberta, DB, queries, rede ou análise nova. O agregador
CLI mantém imports legados, sem executá-los no comando dossier. Saídas humanas
e metadata não expõem paths do host, nomes de origem ou hashes; hashes contratados ficam
na integridade técnica. Payloads selecionados são cópias exatas, não anonimizadas.
Sem inferência automática de identidade/autoria ou conclusão jurídica; nenhuma
alegação de software pericial certificado. A integração aceita
source_media.provenance_link/1.0.0 permanece via report.consolidated/1.1.0 e
report.data_snapshot/1.1.0. Não há máximo semântico de snapshots; budgets continuam.

README, AGENTS e architecture promovidos somente após os gates das duas plataformas.
Nenhum caso real foi acessado; 8B3 continua futura e exclusivamente responsável
pela execução/validação real controlada. 8B2 continua futura para PDF; ZIP,
assinatura e transporte exigem escopo separado. WhatsApp permanece condicional,
não acionado. Sem stage, commit ou push neste fechamento para revisão humana.
