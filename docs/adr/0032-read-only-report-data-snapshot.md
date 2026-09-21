# ADR 0032 — Read-only Report Data Snapshot

Status: aceito; implementação 8A1.

## Contexto e auditoria das APIs

O contrato epistemológico permanece no ADR 0031, sem alteração histórica. A 8A1
fornece dados técnicos estruturados ao futuro consumidor 8A2. Não seleciona
achados relevantes, gera prosa, decide identidade/autoria ou classifica lacunas
A–F. O envelope DERIVED não altera a classificação dos objetos subjacentes.

Auditoria anterior à composição:

| API/camada | Acesso e projeção existente | Decisão 8A1 |
| --- | --- | --- |
| query.catalog.read_catalog | mode=ro, query_only, BEGIN, schema v5 | Um contexto para todos os componentes diretamente compostos de banco. |
| timeline | Wrapper próprio e timeline_in_snapshot; campos técnicos explícitos | Reutilizar predicate current e primitive existente. |
| incident window | Wrapper próprio; provenance e contexto do mesmo ParsedRecord | Extrair incident_window_in_snapshot, preservando validação e API pública. |
| incident candidate matrix | Wrapper próprio; memberships persistidas, eventos e support links | Extrair incident_candidates_in_snapshot, preservando algoritmo e ordenação. |
| technical search | Wrappers próprios; colunas técnicas e candidate_ids reutilizáveis | Reutilizadas pelas camadas incident; nenhuma busca nova por valor pessoal. |
| provenance | record_origin/observation/candidate aceitam conexão; wrapper próprio | Usar record_origin; excluir paths. Não usar candidate, que inclui key_digest. |
| exact correlation | Algoritmo e serviço de escrita; candidates persistidos v5 | Não executar serviço/algoritmo. Resumir linhas elegíveis por versões explícitas e run concluída. |
| temporal 6A | Wrapper próprio e temporal_candidates_in_snapshot | Executar primitive uma vez, sob a mesma conexão. |
| overlap 6B | Wrapper próprio compõe 6A e memberships | Extrair overlap_in_snapshot(connection, temporal), consumindo exatamente o prefixo 6A já calculado. |
| media inventory | Catálogo próprio + filesystem; SHA/tamanho/stable reader | Manter API e verificações sem alteração. |
| exact media contents | project_contents puro sobre inventory verificado | Reutilizar a projeção; sem novo algoritmo de igualdade. |
| perceptual hash | inventory/contents e catálogo próprios; releitura verificada do representante | Manter API; resumir statuses, sem serializar pHash ou decodificar por outro algoritmo. |
| manifest | Leitura própria, nome do caso/paths; writer cria arquivo | Não invocar; inventário do report é uma projeção própria de contagens explícitas. |
| verify | Catálogo próprio e SHA dos originais | Gate externo de validação, sem incorporar resultados de execução ao JSON. |
| models/entities.py | Tabelas v5, raw fields e runs históricos | SELECTs explícitos; nunca carregar payload/annotations para compor o report. |
| CLI | Typer, CaseRoot, fail; serialização temporal em ASCII/LF | Novo cli/report.py registrado no app, sem dependências. |

Os três wrappers extraídos mantêm validações, defaults e comportamento público.
As primitives internas exigem argumentos já validados. Não houve mudança nos
algoritmos de normalização, exact correlation, pHash, pares temporais ou overlap.

## Comando e escopo

```console
dee report snapshot --case-root /case
dee report snapshot --case-root /case --start 2026-01-01T00:00:00Z --end 2026-01-01T01:00:00Z --max-delta-seconds 300 --platform meta --event-kind content.activity
```

Exemplos inteiramente sintéticos. start/end/max-delta-seconds formam um trio
opcional indivisível. platform/event-kind exigem o trio completo. A validação
reutiliza temporal_bounds: UTC Z estrito, início anterior ao fim, intervalo
[start,end), raio inteiro 1–86400. Erros são exit 2 antes de abrir o catálogo.
Existe zero ou uma janela por execução; não há DSL, lista de janelas ou arquivo
de configuração de query. Filtros afetam somente a janela; resumos continuam
case-wide. Ausência de janela produz analysis_window=null e não executa consultas
incident/temporal. Policies temporais continuam identificadas como disponíveis.

## Consistência

Um read_catalog engloba identificação do caso, contagens, coverage, resumo current,
resumo exact, quatro componentes da janela e índice de provenance. BEGIN mantém
o snapshot SQLite; o opener defensivo exige v5 e impede escrita.
Preserva a restrição Foundation a journal mode DELETE; não habilita WAL nem altera
configuração. A validação defensiva do opener precede a transação de composição.

Após encerrar esse contexto, media inventory e perceptual_hashes usam os próprios
read snapshots e leitores verificados. Há três aberturas de catálogo de mídia:
inventory externo, inventory interno de pHash e resolução dos representantes.
project_contents é puro. Isso repete uma inspeção de inventory, preservando as
APIs de segurança existentes sem refactor amplo. Divergência entre conteúdos,
tamanhos ou ocorrências dessas leituras causa REPORT_MEDIA_COMPONENTS_CHANGED.
Falha de integridade não emite JSON parcial. Falhas de decode/unsupported já
controladas por pHash são dados de status e não invalidam o snapshot.

O envelope declara:

```json
{
  "database_consistency": "single_read_snapshot",
  "database_scope": "direct_db_components_and_provenance_index",
  "media_consistency": "verified_read_only_components",
  "media_catalogs": "separate_read_snapshots",
  "atomic_database_filesystem": false
}
```

Não existe atomicidade global SQLite/filesystem. O índice tem a baseline do
snapshot DB; mídia registra ocorrências verificadas em seu próprio escopo.
Operação sobre caso estável é condição para repetibilidade entre execuções.

## Schema JSON 1.0.0

ReportSnapshot é um dataclass explícito em reports/snapshot.py. As projeções
internas seguem os dicionários técnicos já utilizados em query/. Top-level:

| Campo | Forma e significado |
| --- | --- |
| snapshot | snapshot_id=report.data_snapshot, snapshot_version=1.0.0, feature_class=DERIVED, evidence_schema_version=5, case_id existente e engine_version determinística. |
| consistency | Objeto acima, com escopos distintos. |
| scope | case_wide_summaries, executed_components, limites separados e underlying_classifications. |
| policies | availability=known_policies_not_execution_claims; current_event_policy, eligible_normalizers, observers, exact_correlator, exact_rules, perceptual_hash, temporal_proximity, temporal_exact_overlap. |
| inventory | unit=physical_rows; tables mapeia cada tabela v5 para COUNT físico. Inclui runs, observations, supports e normalized_events históricos. |
| coverage | Por tabela: unit=physical_rows e items ordenados pelas dimensões, cada item com count. Não aplica filtro current a histórico. |
| current_events | unit=current_events, policy_id/version, total/dated/undated, by_platform_event_kind com mesmas contagens por grupo. |
| exact_candidates | unit=eligible_persisted_candidates, total/device/network; supports com unit=persisted_support_rows e total; eligibility explícita. |
| media | inventory, contents e perceptual, descritos abaixo. |
| analysis_window | null ou window/start/end/platform/event_kind, max_delta_seconds e quatro componentes técnicos. |
| finding_candidates | global_limitations e seções por candidate_type com unit/total/returned/truncated/items. |
| gap_inputs | Contagens de parser runs FAILED/UNSUPPORTED, eventos atuais sem UTC, mídia não reconhecida, pHash failed/unsupported, truncated_components, capability flags e known_capability_limits. |
| provenance_index | Mapas parsed_records e evidence_files, indexados por IDs existentes em seus respectivos domínios. |

Não há generated_at, clock, UUID de execução, path absoluto, nome do caso,
summary_text, conclusion, assessment, confidence, score ou recommendation.
snapshot_version versiona o contrato de saída e não o evidence database.

Policies: current_event_policy 1.0.0; normalizers Meta 1.0.0, Google 1.1.0,
Apple 1.0.0; device/network observer 1.0.0; exact_match.correlator 1.0.0;
device.exact_namespace_value e network.exact_canonical_ip 1.0.0; image.phash
1.0.0 com parâmetros e versões de bibliotecas existentes; temporal.proximity
e temporal_exact_overlap 1.0.0. Sem janela, nenhuma policy temporal inclui um
raio fictício. O raio efetivo consta na janela/policy executada.

Coverage agrupa parser runs por parser_id/version/status, normalização por
normalizer_id/version/status, observação por observer_id/version/status e
correlation runs por correlator_id/version/status. Candidates adicionam
rule_id/version/kind; eventos físicos adicionam platform/event_kind; observations
adicionam platform. Coverage histórica não é completude da realidade.

Current usa exclusivamente current_event_predicate. COUNT(normalized_events)
permanece físico e separado. Exact summary seleciona versões/rules aprovadas,
kind correspondente e correlation run COMPLETED com caso/correlator/version
correspondentes. Confere soma de support_count contra linhas de support elegíveis;
não recalcula grupos nem oferece auditoria exaustiva de objetos não alcançados.
O resumo não expõe key_digest ou valores usados para correlação.

## Mídia, unidades e proveniência

media.inventory tem unit=cataloged_occurrences, scanned_occurrences,
recognized_media, verified_media, unrecognized_occurrences, format_counts e
kind_counts. media.contents tem unit=exact_contents, exact_content_count,
singleton_content_count, duplicate_content_count, format_counts_by_content e
kind_counts_by_content. occurrences separa total/in_duplicate_contents com
unit=verified_media_occurrences. duplicates expõe todos os grupos: conteúdo SHA,
formato/kind, tamanho, occurrence_count e todas as referências source_kind,
evidence_file_id/archive_member_id. Sem path ou escolha de fonte superior.

media.perceptual tem unit=exact_contents, policy, exact_content_count,
success_count, failed_count, unsupported_count e by_status_format. Não publica
pixels, bytes, imagem, thumbnail, base64, hash perceptual, distância, threshold
ou similaridade. pHash não recebe vínculo com eventos.

provenance_index.parsed_records contém apenas registros referenciados pela
união dos componentes retornados, inclusive os que ultrapassam o limite do
incident. Cada entrada preserva parsed_record_id, source_record_id,
source_locator, origin_kind, evidence_file_id/evidence_sha256,
archive_member_id/archive_member_sha256 e classification=OBSERVED. Paths são
omitidos. evidence_files mapeia IDs do catálogo para cataloged_sha256, permitindo
alcançar o container original de duplicatas. Para mídia arquivada, content_sha256
é a baseline do conteúdo do membro, e evidence_files fornece a do container.
Nenhum novo ID é criado; IDs de observation são tipados pelo contexto device/network.

Eventos mantêm ID, ParsedRecord, UTC/time_status/time_basis, platform/event_kind
e normalizer/version. Contextos incident mantêm observation IDs, locators e
candidate IDs existentes. A matrix inclui support IDs/ordinais, vínculos por
evento e contagens globais versus ocorrências na janela. Esses dados permitem
drill-down pelas APIs existentes, sem abrir payload arbitrário. O índice não
duplica cadeias completas para cada par/finding.

## Janela, limites e candidates a achados

incident_window preserva policy, matched_total/returned/truncated,
undated_current_events e items; a provenance inline é movida ao índice sem paths.
incident_candidates preserva integralmente a projeção técnica 4B2 e sua ordem.
A matrix continua seguindo memberships persistidas da 4B2, que podem ter versões
históricas; não recebe silenciosamente a allowlist do resumo exact ou da 6B.
temporal_proximity e temporal_exact_overlap preservam seus DTOs, contagens,
janela, policy, endpoints, deltas inteiros e prefixo. Device/network shared IDs
e same_parsed_record permanecem separados. Não existe pair_id artificial.

Limites internos: 500 incident events, 100 matrix candidates, 1000 pares 6A
e os mesmos 1000 pares 6B. Os defaults/max das APIs públicas permanecem intactos.
Não há limite global misturando unidades nem novas flags de limite na CLI 8A1.
Os totais são calculados pelas APIs antes de truncar. Cada seção limitada informa
total/returned/truncated (ou matched_total/matched_candidates/matched_pairs e
seu returned correspondente). Findings herdam a cobertura/truncamento da origem;
totais podem exceder o prefixo projetado. Seções case-wide agregadas e mídia
não têm corte. Arrays potencialmente grandes continuam uma limitação operacional.

Cada finding possui candidate_type, classification=DERIVED, technical_basis,
references e limitations_ref apontando para global_limitations. Tipos:

- exact_media_duplicate: igualdade SHA/tamanho verificada e todas as ocorrências;
- window_exact_candidate: candidate existente com kind, rule/version e event IDs;
- temporal_pair_candidate: endpoints e delta de cada par retornado 6A;
- temporal_exact_overlap_candidate: todos os pares do prefixo 6B, inclusive sem
  membership compartilhada, preservando arrays separados e same_parsed_record.

Nenhum candidate é selecionado por interesse, sobreposição, força ou importância.
A ordem existente da matrix por contagens é preservada como ordenação de query,
sem novo ranking probatório. Sem janela, somente o tipo de duplicata de mídia é
projetado. Não há finding final, REPORTED/HYPOTHESIS automático ou gate de
interpretação. A classificação de um futuro achado é trabalho da 8A2 sob ADR 0031.

gap_inputs fornece fatos técnicos com unidades; não conclui inexistência de dado,
atividade ou vínculo no mundo real. media_event_link_available=false e
whatsapp_parser_available=false são capacidades implementadas, não afirmações
sobre o caso. As categorias A–F só podem ser avaliadas posteriormente com escopo,
fontes e incertezas documentados.

## Determinismo, segurança e limites

Serialização ensure_ascii=True, sort_keys=True, separators=(",", ":") e LF
explícito em bytes. Mesmo catálogo, filesystem estável, argumentos e versões de
engine/bibliotecas produzem bytes iguais. Não há relógio ou IDs novos.
stdout somente; não cria run, output, cache, tabela, view, índice ou migration.
Schema v5, pyproject.toml e uv.lock inalterados. Sem integração externa.

As limitações incluem custo de inspecionar mídia mais de uma vez, matrix com
consultas por registro, contagem quadrática de pares em janelas densas e arrays
case-wide sem limite. O report não é certificação pericial nem resolve
identidade/autoria/sessão/causalidade. Ausências são sempre delimitadas pelo
catálogo, policies, janela e truncamento. Mesmo ParsedRecord não constitui duas
fontes independentes. A futura 8A2 consumirá snapshots para seleção auditável,
rendering e gap analysis; WhatsApp permanece futuro e condicionado às lacunas.

## Validação

Baseline prévia: 853 PASS, exit 0. Testes sintéticos cobrem snapshots com/sem
janela, limites independentes, integridade, provenance, privacidade e igualdade
de todos os componentes. Instrumentação comprova uma conexão/transação de
composição e proíbe aberturas adicionais pelos wrappers DB. Teste com writer
concorrente confirma que o commit fica bloqueado durante a leitura em DELETE
mode e passa após seu encerramento. Testes focados iniciais: 360 PASS. Suíte
completa final Linux: 886 coletados, 886 PASS, exit 0, incluindo 33 testes 8A1.
Ruff check/format: PASS; mypy Linux: PASS em 68 módulos. Os cinco helps (raiz,
report, report snapshot e os dois comandos temporais) terminaram com exit 0.
Helper independente local/ignored usa sqlite3 mode=ro/query_only e CLIs existentes,
sem importar reports.snapshot para contagens. Resultados de caso, snapshot JSON
e relatório de validação ficam exclusivamente fora do Git.

Validação real: PASS. Verify antes/depois: PASS. SQL independente confirmou
contagens físicas, current, coverage e candidates elegíveis. Comparações com
inventory/contents/perceptual-hash: EQUAL. Mesmas janelas Meta e cross-platform
da 6A/6B: quatro componentes EQUAL; findings e gap inputs são projeções verificadas.
Repetição e Windows/Linux: BYTE_IDENTICAL tanto sem janela quanto com janela Meta.
DB SHA/bytes, schema v5, table counts, schema objects e metadados de arquivos:
SAME; nenhum output automático da engine. Após esses checks, o helper criou
explicitamente dois artefatos externos: snapshot sem janela e relatório agregado.
Nenhum dado identificável do caso foi incorporado aos exemplos/testes/documentos.
