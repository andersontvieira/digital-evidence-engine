# ADR 0033 — First Consolidated Technical Report

Status: aceito; implementação 8A2.

## Contratos e auditoria 8A1

A 8A2 consolida snapshots e renderiza o Relatório Técnico Consolidado de Análise
e Organização de Evidências Digitais. ADRs 0031/0032 permanecem inalterados.
Policy: report.consolidated / 1.0.0, feature_class DERIVED. Isso não reclassifica
as fontes: ParsedRecord permanece OBSERVED; eventos normalizados e candidates
técnicos permanecem DERIVED. Sem achados REPORTED/HYPOTHESIS automáticos.

A auditoria de reports/snapshot.py confirmou seções case-wide, uma janela opcional,
finding_candidates, gap_inputs e provenance_index suficientes para a consolidação.
Pares, deltas, memberships e conteúdos exatos já estão projetados; não cabe
recalculá-los. Arrays JSON substituem tuples do DTO Python. IDs/hashes/locators
estão no dataset externo; sua impressão não é necessária à prosa. Verify não
faz parte do snapshot: resultado de validação externa não entra automaticamente
no relatório. cli/report.py pode registrar consolidated sem mudar snapshot.

## Comando e input

```console
dee report consolidated --snapshot /synthetic/anchor.json
dee report consolidated --snapshot /synthetic/anchor.json --snapshot /synthetic/window.json
```

Caminhos sintéticos. --snapshot é obrigatório e repetível: 1–20 arquivos, com
exatamente um anchor sem analysis_window e zero a 19 janelas. Não há case-root.
O renderer não executa 8A1, consulta DB ou acessa originals, working, mídia,
parsers, observers ou correlators. O módulo usa somente stdlib e EvidenceError.

Loader limitado a 64 MiB por arquivo; UTF-8/JSON estrito, sem chaves duplicadas
ou NaN/Infinity. Rejeita estruturas incompatíveis e campos consumidos ausentes,
sem dependência JSON Schema ou reparo silencioso. Falha é exit 2 com código
técnico; mensagens não reproduzem paths ou conteúdo do input. Saída de sucesso:
Markdown UTF-8, LF explícito, stdout somente. Arquivos são criados apenas por
redirecionamento explícito do operador, fora do Git.

## Validação e consistência do conjunto

Exige snapshot_id=report.data_snapshot, snapshot_version=1.0.0,
feature_class=DERIVED e evidence_schema_version=5. Tipos são estritos: bool não
é count. A validação explícita cobre unidades, contagens não negativas,
total/returned/truncated, coverage, mídia, gaps, referências de eventos aos
ParsedRecords e policies consumidas. Confere findings contra componentes
fornecidos e o mesmo prefixo 6A/6B, sem reexecutar os algoritmos.

Rótulos exibidos aceitam tokens ASCII técnicos limitados, sem whitespace,
path/markup, UUID ou hexadecimal opaco longo; versões exibidas seguem N.N.N.
Filtro de janela fora dessa forma segura é rejeitado por REPORT_UNSAFE_DISPLAY_VALUE.
Campos pessoais, payloads e nomes dos arquivos de input não são interpolados.

Todos os inputs devem compartilhar case_id, engine_version, snapshot_version
e evidence_schema_version. Exige igualdade semântica de policies, inventory,
coverage, current_events, exact_candidates e media. Chaves de objetos não
dependem de ordem; arrays mantêm a ordem técnica da 8A1. Todos os gap inputs
case-wide devem coincidir; apenas truncated_components pode variar. Cópias de
exact_media_duplicate e global_limitations também precisam coincidir.
Divergência gera REPORT_SNAPSHOT_SET_CHANGED.

analysis_window, findings windowed e provenance_index.parsed_records variam
naturalmente. A chave de janela é start/end/platform/event_kind/max_delta_seconds;
bounds UTC Z são canonicalizados com microssegundos para comparação/ordenação,
com null distinto de filtro. Duplicatas semânticas geram
REPORT_DUPLICATE_ANALYSIS_WINDOW. Anchor ausente/múltiplo gera REPORT_ANCHOR_COUNT.

## Modelo consolidado

| Estrutura explícita | Campos conceituais |
| --- | --- |
| ConsolidatedReportModel | Metadata, methodology, evidence_scope, coverage, technical_counts, media_summary, windows, findings, limitations, gaps, technical_reference_map. |
| ReportWindow | W-ID, escopo canônico, counts por componente, distribuição do prefixo e truncamentos. |
| ReportFinding | F-ID, candidate_type, classification, statement, technical_basis, provenance_basis, limitations. |
| TechnicalGap | G-ID, category, statement, technical_basis, scope, limitation. |
| TechnicalReference | ID local, Anchor/W-ID, ponteiro lógico no snapshot. |

Modelo apenas em memória; input não é modificado. Metadata não publica case_id,
paths, clock, generated_at ou ID aleatório. A escolha dos snapshots pertence ao
operador. Todos os finding candidates retornados entram, sem heurística de
importância. Duplicatas case-wide são apresentadas uma vez pelo anchor após
conferir igualdade das cópias. Seguem janelas em ordem canônica, cada uma com
window_exact_candidate, temporal_pair_candidate, temporal_exact_overlap_candidate.
Dentro do tipo, preserva-se a ordem recebida.

F-001 etc. são atribuídos após ordenar; W-001 etc. às janelas; G-001 etc. às
categorias sustentadas B/C/D nessa ordem. IDs locais de apresentação não são
evidence/candidate/pair IDs ou entidades persistidas. A ordem dos argumentos
não altera modelo, IDs ou Markdown.

## Templates, contagens e provenance

O título fixo segue ADR 0031, sem apresentação como laudo certificado. As 20
seções são renderizadas, inclusive lacunas na seção 18. Não há LLM/API remota,
prosa livre a partir de conteúdo pessoal ou novas inferências.

- Duplicata: conteúdo byte a byte idêntico verificado em N ocorrências catalogadas
  no snapshot; não identifica upload, envio ou origem histórica.
- Candidate windowed: tipo device/network e quantidade de current events na
  projeção retornada, sem resolver entidade física ou pessoa.
- Par temporal: delta inteiro em microssegundos dentro do limite de consulta;
  delta menor não representa maior força.
- Overlap: memberships técnicas compartilhadas em candidates exatos device/network
  separadamente, no prefixo retornado. Arrays vazios recebem declaração explícita
  de ausência de membership retornada sob policy 6B naquela consulta; o par
  continua incluído. Mesmo ParsedRecord é declarado sem contar duas fontes
  independentes.

Cada finding mantém policy/version, referência e limitações. Se sua seção foi
truncada, a limitação e o escopo da janela indicam total/returned/truncated com
unidade. Distribuições device/network/both/neither descrevem somente os pares
retornados; matched_pairs e returned_pairs ficam explícitos. Não há ranking
probatório ou conclusão automática de identidade/autoria/sessão/causalidade.

Linhas físicas normalized_events e current events sob policy são distintas.
Coverage histórica não demonstra completude. Mídia apresenta inventário,
conteúdos exatos e statuses/policy pHash, sem SHA/pHash, pixels, distância ou
inferência de similaridade. Metodologia explica SHA/verify sem afirmar nova
verificação ou autenticidade anterior à aquisição.

Apêndice mapeia F-IDs para posições como
`Anchor: finding_candidates.exact_media_duplicate.items[0]` e
`W-001: finding_candidates.temporal_pair_candidate.items[2]`.
O snapshot é o dataset de suporte para resolver o ponteiro até a provenance.
Não se imprimem UUID/hash ou paths de input; bounds/filtros das janelas são
escopo autorizado do relatório externo. Dados de caso não entram no Git.

## Gap analysis e WhatsApp

| Categoria | Condição estrita | Limitação |
| --- | --- | --- |
| B | gap_inputs.parser_runs.UNSUPPORTED > 0 | Registra linhas físicas de execuções UNSUPPORTED históricas; não identifica conteúdo ausente ou prova falta atual de parsing. |
| C | gap_inputs.undated_current_events.count > 0 | Current events sem UTC suficiente; não demonstra ausência de atividade. |
| D | Conteúdos exatos de mídia > 0, current events > 0 e media_event_link_available=false | Ausência de vínculo aprovado no motor; não associa mídia a evento específico. |

Um gap por categoria sustentada, com base, escopo e limitação. A/E/F não são
automatizadas: ausência no snapshot não demonstra inexistência; pergunta
investigativa e hipótese externas são necessárias para E/F. FAILED permanece
fato de cobertura. whatsapp_parser_available=false permanece limitação de
capacidade e não gera gap por si só.

Próximas análises são condicionais: aprofundar provenance, revisar unsupported,
ampliar janela mediante pergunta documentada ou considerar fonte nova quando
uma pergunta concreta exigir. WhatsApp continua futuro/condicionado; nenhuma
regra automática desta versão recomenda implementação.

## Consistência, segurança e fronteiras

Igualdade entre snapshots demonstra coerência dos inputs, não autenticidade
criptográfica nem instantaneidade global. Preserva-se a declaração 8A1: DB single
read snapshot, mídia em verified read-only components separados, sem atomicidade
DB/filesystem. A 8A2 não acessa essas camadas para renovar essa afirmação.

Mesmo conjunto de inputs produz UTF-8/LF idêntico, sem clock/random/paths ou
metadados de filesystem. Não há DB rows/runs/cache/outputs automáticos. Custódia
dos JSONs permanece externa: validação estrutural não detecta fabricação coerente
de todos os campos. Muitos candidates podem gerar documento extenso, apesar dos
limites de arquivos/bytes; inclusão integral é decisão explícita desta versão.

Schema v5, pyproject.toml e uv.lock permanecem inalterados. Sem WhatsApp,
PDF/DOCX/HTML, dashboard, OCR, nova análise ou entidade persistida. A 8B poderá
tratar packaging/dossier/export sob novo escopo, sem ampliar conclusões por
rendering ou dispensar revisão humana.

## Validação

Baseline Linux: 886 collected, 886 passed, exit 0. Testes focados 8A2/8A1/CLI:
104 PASS, incluindo 64 novos testes sintéticos 8A2. Suíte final Linux: 950
collected, 950 passed, exit 0. Ruff check/format: PASS; mypy Linux: PASS em
69 módulos. Helps raiz, report, snapshot e consolidated: exit 0.

Validação real: PASS. Anchor reutilizado; snapshots de janelas ausentes foram
gerados externamente com os mesmos contextos já validados. Helper independente
confirmou conjunto, seções, counts, seleção/IDs, pointers, gaps e distribuições.
Repetição, inversão de inputs e Windows/Linux: BYTE_IDENTICAL. DB SHA/bytes,
schema, counts, evidências e snapshots preservados; sem arquivos automáticos.
Renderer Linux recebeu somente mounts de snapshots e repositório, sem DB,
originals ou working. Markdown revisado quanto a linguagem, escopo e legibilidade.
Artefatos, resultados agregados e helpers reais permanecem fora do Git.
