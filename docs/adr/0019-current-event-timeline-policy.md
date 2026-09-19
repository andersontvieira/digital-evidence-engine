# ADR 0019 — Current-event timeline policy

Status: aceita. Entrega: Milestone 4A1.

A query consulta somente a projeção autorizada de NormalizedEvent, em catálogo
schema v5 aberto com mode=ro/query_only. Uma transação de leitura mantém counts e
items no mesmo snapshot. Não há nova entidade, tabela, view, índice, cache, run,
migração ou backup. Banco ausente, WAL e recovery necessário falham defensivamente.

Política em código `current_event_policy` 1.0.0 seleciona explicitamente:
meta.event_normalizer 1.0.0, google.event_normalizer 1.1.0 e
apple.event_normalizer 1.0.0. Não há MAX(version), último run ou seleção automática
de versões futuras. Alterar a seleção exige versionar a política. Google 1.0.0
histórico permanece no banco e fica fora desta projeção lógica.

Timeline inclui somente occurred_at_utc não NULL. Ordem crescente:
occurred_at_utc, platform, event_kind, event_id. Normalizers aceitos persistem UTC
com seis casas fracionárias; filtros são convertidos para esse mesmo formato,
preservando comparação cronológica e precisão de microssegundos.

Bounds aceitam somente `YYYY-MM-DDTHH:MM:SS[.ffffff]Z` (fração de 1–6 dígitos),
com data válida, sem espaços ou outros offsets. Intervalo [start, end);
start >= end é erro. Não há timezone da máquina ou horário inventado.

Filtros platform/event_kind são igualdade textual, um valor por opção; desconhecidos
retornam zero matches. matched_total conta eventos datados após todos os filtros;
limit (1–10000, default 1000) afeta somente items/returned/truncated.
undated_current_events conta eventos atuais NULL após platform/event_kind,
independentemente de bounds/limit: não é possível posicioná-los numa janela UTC.
timestamp_raw não é consultado ou usado para ordenação.

JSON determinístico inclui policy id/version, contagens e somente event_id,
parsed_record_id, occurred_at_utc, platform, event_kind, normalizer_id/version,
time_status e time_basis. Não há payload, texto pessoal, IP, device, timestamp
operacional da query ou campos extras. IDs/horários são projeção autorizada e
continuam dados de caso; resultados reais não devem entrar no Git.

CLI: `dee query timeline`; erros de entrada/schema/operação retornam exit 2.
Não há paginação por cursor, export, rendering local, busca textual, drilldown,
temporal correlation, score ou resolução de identidade.
