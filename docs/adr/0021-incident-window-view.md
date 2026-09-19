# ADR 0021 — Read-only incident window view

Status: aceita. Entrega: Milestone 4B1.

`dee query incident-window` exige start/end UTC Z, intervalo [start,end), start
anterior a end. Filtros platform/event_kind são exatos. Limit default 500, máximo
5000, mínimo 1, sem cursor. Schema v5, sem migration, backup, tabela, view SQLite,
índice, cache ou QueryRun/IncidentRun.

`query.catalog.read_catalog` abre um snapshot read-only coerente com mode=ro,
query_only e defesas existentes de WAL/recovery. A execução SQL da timeline 4A1
foi extraída para `timeline_in_snapshot`, sem alterar seu contrato ou política.
Nenhum banco é reaberto por item. As consultas anteriores permanecem disponíveis.

Somente eventos datados de current_event_policy 1.0.0: Meta 1.0.0, Google 1.1.0,
Apple 1.0.0. Ordem: occurred_at_utc, platform, event_kind, event_id ASC. Cada item
preserva os nove campos da timeline e acrescenta provenance, device_context e
network_context. Proveniência reutiliza `record_origin` da 4A2, seguindo FKs até
EvidenceFile ou ArchiveMember/container e hashes catalogados, sem abrir evidência.
Falhas de integridade não retornam composição parcial.

Contextos incluem exclusivamente observations do mesmo parsed_record_id do evento,
de device.observer/network.observer 1.0.0. Ordem: observation_ordinal, observation_id
ASC. Projeções reutilizam colunas restritas da 4A2, omitindo platform/parsed_record_id
redundantes. candidate_ids reutiliza lookup de CorrelationSupport persistido, ASC.

Ausência de observations próprias produz lista vazia. Não há propagação por valor,
candidate, modelo, IP ou proximidade temporal. Eventos do mesmo ParsedRecord podem
apresentar o mesmo contexto de origem, sem inferência de identidade. Lookup histórico
continua disponível na 4A2, mas históricos não entram nesta lista.

Resumo deliberadamente essencial: matched_total considera todos os matches da
janela; returned/truncated descrevem o prefixo. undated_current_events reutiliza a
semântica 4A1, sob platform/event_kind e independente de start/end. Não se calculam
agregados de contexto sobre eventos fora do prefixo, evitando expandir a composição
para todos os matches. Eventos sem UTC não recebem posição temporal inventada.

JSON determinístico não inclui relógio operacional, payload, annotations,
timestamp_raw, device values, IPs ou mensagens. IDs, locators, paths relativos e
SHA-256 autorizados continuam dados de caso e ficam fora do Git.

Origem comum não afirma mesmo dispositivo ou pessoa. Proximidade não é correlação;
membership não é identidade; incident view não é autoria. Sem edges temporais,
sessões, incident entity, score, confidence, identity, export ou busca textual.
