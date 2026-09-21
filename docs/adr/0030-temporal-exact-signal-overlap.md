# ADR 0030 — Read-only Temporal + Exact Signal Overlap

Status: aceito; implementação 6B do contrato histórico ADR 0029.

## Comando e contrato

`dee correlate temporal-exact-overlap` enriquece somente o prefixo de pares
retornado pela 6A com interseções de memberships exatas persistidas pela 3C1.
Schema permanece v5. DTOs imutáveis são transitórios e não herdam do ORM
CorrelationCandidate. Não há persistência, table, view, index, migration, run,
cache, output automático ou dependência nova. ADR 0029 permanece inalterado.

Policy `temporal_exact_overlap` / `1.0.0`, relation
`temporal.exact_signal_overlap_candidate`, feature class `DERIVED`.
O envelope identifica `temporal.proximity` / `1.0.0`,
`exact_match.correlator` / `1.0.0` e o max_delta_seconds informado pelo operador.
Não estabelece força, identidade, sessão, autoria, localização ou causalidade.

## Composição no mesmo snapshot

`temporal_candidates_in_snapshot` recebe a conexão já aberta e reutiliza
`_sweep_pairs` sem alteração. O wrapper público 6A continua validando argumentos,
abrindo `read_catalog` e delegando à primitive. A 6B faz a mesma validação via
`temporal_bounds` e abre exatamente um `read_catalog` para toda a composição.
Timeline, pares, observations, supports, candidates e validação usam a mesma
conexão/transação SQLite mode=ro/query_only; não há sessão ORM gravável.

A semântica 6A permanece integral: current_event_policy 1.0.0 (Meta 1.0.0,
Google 1.1.0, Apple 1.0.0), apenas UTC conhecido, parser UTC estrito com Z,
janela `[start,end)`, platform/event-kind exatos antes dos pares, raio inteiro
obrigatório 1–86400 segundos e delta em microssegundos inteiros. Limit tem default
1000, faixa 1–10000. A/B e pares seguem a chave completa da timeline para A,
depois B: UTC, plataforma, event_kind e event_id.

eligible_events e matched_pairs descrevem todo o universo temporal;
returned_pairs, truncated e items preservam exatamente o prefixo 6A. Somente
esse prefixo recebe overlap. Não há filtro por overlap, candidate-kind filter,
reordenação ou promoção de par externo ao prefixo. Prefixo vazio não consulta
memberships. A serialização compartilhada usa ensure_ascii, chaves ordenadas,
separadores compactos e LF explícito, preservando também os bytes da CLI 6A.

## Associação e allowlists

`same_record_predicate`, compartilhado com `same_record_context` da 4B1, fixa
ParsedRecord e versão do observer; o comportamento 4B1 permanece preservado.
Somente observations do próprio registro do endpoint contribuem. Não há
propagação por fonte, arquivo, tempo, evento vizinho ou candidate compartilhado.

| Tipo | Observer elegível | Regra elegível |
| --- | --- | --- |
| device | device.observer / 1.0.0 | device.exact_namespace_value / 1.0.0 |
| network | network.observer / 1.0.0 | network.exact_canonical_ip / 1.0.0 |

Ambos exigem candidate de `exact_match.correlator` / `1.0.0` e run coerente.
Não selecionar versões históricas/futuras automaticamente. Candidates válidos
fora dessa policy não entram, sem erro. A 6B não recalcula igualdade device,
canonicalização IP, agrupamento ou digest: navega apenas supports persistidos.

## Carga em lote e IDs tipados

Coletar os event IDs e ParsedRecord IDs distintos do prefixo. Carregar projections
explícitas de IDs e metadados técnicos em lotes determinísticos de até 400 IDs,
sem raw device, IP, digest/key, payload ou annotations. A carga mantém mapas
registro → conjunto device e registro → conjunto network; não há SQL por par,
endpoint ou observation. O número de consultas depende das fases e dos lotes.

**Observation IDs têm escopo por tabela tipada**, não unicidade global entre
device_observations e network_observations. Supports device são buscados somente
pela FK device_observation_id; supports network somente por network_observation_id.
Igualdade textual de IDs entre tabelas não captura nem invalida o outro braço.
Não usar OR entre os dois braços para resolver uma observation de tipo conhecido.
O teste sintético `test_observation_ids_are_scoped_by_typed_table` fixa esse contrato.

Para cada par, intersectar os conjuntos de candidate IDs de A/B separadamente
por tipo e ordenar lexicalmente os IDs únicos. Múltiplos supports/observations
do mesmo registro não aumentam cardinalidade nem peso. A saída traz somente
delta_microseconds, os nove campos técnicos de cada endpoint, same_parsed_record
e os dois arrays em shared_exact_candidates, sem contagens redundantes.

same_parsed_record é igualdade objetiva dos IDs. Events distintos do mesmo
registro não são excluídos nem têm interseções alteradas; nesse caso o overlap
pode vir da mesma observation, sem duas fontes independentes. Arrays vazios são
normais: ausência de supporting signal não é evidência de diferença.

## Integridade das relações alcançadas

Consultas explícitas sem inner joins evitam ocultar referências ausentes.
Validar casos dos eventos, registros, observations, candidates e runs;
existência/coerência das referências; candidate_kind; braço FK correspondente
e ausência do braço oposto; regra compatível com o tipo; relação correlator/run;
relação observer/run; status COMPLETED dos runs e versões elegíveis.

Para cada candidate elegível alcançado, carregar todos os seus supports e
observations necessários à validação, inclusive fora do prefixo. Conferir mínimo
de dois, igualdade com o campo persistido support_count, unicidade das referências
e ordinais contíguos de zero a count−1, conforme a produção 3C1. Supports externos
não propagam membership: somente observations inicialmente selecionadas pelo
same-record predicate alimentam os mapas dos endpoints.

Versão não elegível é exclusão; candidate da policy elegível com support que
viola seu contrato é inconsistência. Referência ausente ou incoerência alcançada
gera TEMPORAL_OVERLAP_INTEGRITY_ERROR, exit 2 global e nenhuma saída de sucesso
parcial. Constraints/FKs de produção não são enfraquecidas; corrupção controlada
é usada exclusivamente nas fixtures sintéticas.

## Limites e validação

Sem score, confidence, weight, ranking, strength ou booleano correlated/same_actor/
same_device/same_session. Delta menor não recebe peso. pHash não é importado nem
consultado: não há vínculo media-event aprovado. Proveniência detalhada permanece
em `dee query provenance --kind candidate` e nas projeções existentes de eventos.

O custo temporal continua O(N + K) sobre entrada ordenada, mesmo com limit pequeno.
A memória inclui eventos, prefixo e memberships/supports alcançados. Um candidate
com muitos supports pode exigir carregar mais registros que os do prefixo.
A validação não é auditoria global dos objetos não alcançados; snapshots SQLite
não tornam arquivos externos atomicamente imutáveis.

Testes sintéticos cobrem regressão 6A/4B1, presença/ausência de cada tipo de overlap,
deduplicação, mesmo registro, versões, prefixo, erros globais, IDs tipados, chunks,
snapshot único, ausência de leituras raw e número de consultas sem crescimento
por par. A validação real pós-correção compara as mesmas janelas/raios anteriores
com SQL independente read-only, incluindo prefixo, same_parsed_record,
interseções, ordem, determinismo Windows/Linux e integridade pre/post.
Validação real após a correção de IDs tipados: PASS. Endpoints, deltas,
same_parsed_record, interseções e ordem iguais à referência independente;
prefixo preservado, stdout Windows/Linux byte-identical, verify pre/post aprovado
e banco/contagens intactos. Mesmo ParsedRecord não estava presente nas janelas
reais consultadas; esse comportamento possui cobertura sintética específica.
Resultados detalhados e limitações estão no relatório externo ao Git;
nenhum ID, timestamp ou valor real é incluído neste ADR.
