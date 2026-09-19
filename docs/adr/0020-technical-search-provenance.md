# ADR 0020 — Technical search and provenance

Status: aceita. Entrega: Milestone 4A2.

As consultas reutilizam `storage.database.open_database(read_only=True)` da 4A1:
mode=ro, query_only, recusa de WAL/recovery e nenhuma criação de banco. O pequeno
context manager `query.catalog.read_catalog` exige schema v5 e mantém contagens,
items, memberships e proveniência no mesmo snapshot explícito de leitura.
Sem migration, backup, tabela, view, índice, cache, FTS ou run adicional.

Device search exige namespace e string literal. O argumento é serializado com
`json_text` e comparado exatamente com value_raw: string não equivale a número ou
booleano, sem ajustes de case, espaços ou pontuação. Namespace permanece parte da
chave. Somente device.observer 1.0.0 é elegível; fact_kind/platform são filtros exatos.

Network search valida a entrada com `ipaddress.ip_address`, comparando sua versão
e representação canônica com ip_version/ip_canonical persistidos. Não reinterpreta
ip_raw, não faz DNS ou enriquecimento. Somente network.observer 1.0.0 é elegível;
platform/source_role são filtros exatos. Versões futuras não entram automaticamente.

Buscas retornam matched_total, returned, truncated e items; limit default 100,
intervalo 1–10000. Ordem crescente: platform, parsed_record_id, observation_ordinal,
observation_id. Items contêm IDs, metadados técnicos/locators e candidate_ids,
ordenados por candidate_id e obtidos somente de CorrelationSupport persistido.
Singletons não recebem candidatos inferidos.

`provenance --kind` aceita exatamente event, parsed-record, device-observation,
network-observation ou candidate; `--id` exige UUID. Lookup direto não filtra versões:
eventos históricos são acessíveis, com current_policy_match informativo conforme
current_event_policy 1.0.0. Event não ganha links heurísticos para sibling observations.

A projeção reutilizável segue ParsedRecord → SourceRecord → EvidenceFile ou
ArchiveMember → EvidenceFile, somente por FKs. Retorna IDs, locator do ParsedRecord,
origem, paths relativos e SHA-256 catalogados, sem abrir originals/working.
Origem ausente, ambígua ou quebrada falha tecnicamente, sem resultado parcial.
Candidate retorna metadados, key_digest e supports ordenados por support_ordinal
autoritativo, cada qual com observation metadata e proveniência. support_count é
conferido contra os supports persistidos. Limit default 100, intervalo 1–1000;
returned_supports/supports_truncated descrevem o prefixo. Sem offset ou cursor.

JSON usa apenas projeções explícitas, com chaves ordenadas, sem relógio operacional,
payloads, annotations, timestamps raw, device values ou IPs. IDs, paths, locators e
hashes autorizados ainda são dados de caso e devem permanecer fora do Git.
Objeto ausente retorna `{"status":"NOT_FOUND"}` e exit 2; entradas inválidas e
falhas técnicas usam exit 2 sem traceback nem eco de --value/--ip. Sucesso: exit 0.
O histórico de argumentos do shell é uma limitação operacional externa ao engine.

Search não é correlation; lookup não é identity; provenance não é authorship.
Não há inferência de aparelho, pessoa, sessão, local ou autoria. Busca textual,
timeline composta, correlação temporal, resolução de identidade e export ficam futuros.
