# ADR 0022 — Read-only incident candidate matrix

Status: aceita. Entrega: Milestone 4B2.

`dee query incident-candidates` exige start/end UTC Z, intervalo [start,end),
start anterior a end. platform/event-kind selecionam primeiro os eventos atuais;
candidate-kind aceita somente device ou network, omitido inclui ambos. Limit
default 100, intervalo 1–1000, aplica-se exclusivamente aos candidates retornados.

Reutiliza read_catalog, current_event_policy, timeline_in_snapshot e
same_record_context da 4B1, incluindo lookup de memberships da 4A2. Toda a consulta
usa um único snapshot mode=ro/query_only. Timeline aceita internamente limit=None
para esta composição completa; os limites públicos da 4A1/4B1 não mudam.
Schema v5, sem tabela, view, índice, cache, migration, backup ou runs novos.

Um candidate só está presente pela cadeia persistida: current NormalizedEvent
datado na janela → ParsedRecord → observation do mesmo ParsedRecord, dos observers
device.observer/network.observer 1.0.0 → CorrelationSupport → CorrelationCandidate.
Não se recalculam grupos por valores. Candidate ausente ou support incompatível
falha tecnicamente. Não se consulta provenance automaticamente: IDs permitem
drill-down pelos comandos incident-window/provenance existentes da 4A2/4B1.

Cada item projeta candidate ID/kind, correlator/rule ID/version, support_count
global como candidate_support_count, window_event_count (eventos distintos),
window_support_occurrences (links evento/support), window_platforms,
window_event_kinds e events. As duas listas DISTINCT vêm somente dos eventos
da janela, ordenadas ASC, nunca dos supports globais externos.

Events contêm event_id, parsed_record_id, occurred_at_utc, platform, event_kind
e observation_links. Cada link preserva observation_id, support_id/ordinal,
source_field_locator e fact_kind/namespace ou source_role/ip_version. Múltiplas
observations do mesmo evento não são colapsadas. Se vários eventos compartilham
ParsedRecord, cada par evento/support é uma ocorrência: esse total pode exceder
o número de supports globais distintos. Não implica novos fatos ou relações.

Ordem de candidates: window_event_count DESC, window_support_occurrences DESC,
candidate_kind ASC, candidate_id ASC. Contagens não são scores ou força probatória.
Events preservam UTC/platform/event_kind/event_id ASC da timeline; links ordenam
support_ordinal/observation_id ASC. matched_candidates conta todos após filtros;
returned_candidates/truncated descrevem o prefixo. Todos os eventos dos candidates
selecionados são retornados, sem cursor ou limite interno silencioso. A composição
em memória é deliberada para o catálogo atual; janelas grandes ampliam custo e saída.

Sem payload, raw device/model, IP, annotations, timestamp_raw ou key_digest.
JSON determinístico, sem relógio operacional. Outputs reais ficam fora do Git.
Sem propagação entre ParsedRecords, edges temporais, candidates novos, clusters,
sessões, inferência de dispositivo/pessoa/local/autoria/ownership ou scoring.
