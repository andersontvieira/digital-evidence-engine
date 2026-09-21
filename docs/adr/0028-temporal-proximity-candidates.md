# ADR 0028 — Read-only temporal proximity candidates

Status: aceito.

## Contexto

A 6A é a primeira etapa funcional do Milestone 6. O operador precisa recuperar
pares de eventos current dentro de uma janela e de um raio explícitos, sem
transformar proximidade temporal em correlação comprovada. Schema permanece v5.

## Decisão

`dee correlate temporal-candidates` exige `case-root`, `start`, `end` e
`max-delta-seconds`. Reutiliza `query.catalog.read_catalog`, seu opener SQLite
`mode=ro`/`query_only` e um único snapshot, além da seleção da timeline sem limite.
Reutiliza `current_event_policy` 1.0.0: Meta 1.0.0, Google 1.1.0 e Apple 1.0.0.
Versões históricas e futuras não são promovidas automaticamente.

Os limites usam o parser UTC estrito da timeline, com `Z`, até seis casas
fracionárias e `start < end`. A janela é `[start,end)`. Somente eventos com UTC
conhecido entram; raw_only e missing ficam fora. `platform` e `event-kind` são
filtros exatos de consulta aplicados antes dos pares, com a semântica da timeline.

`max_delta_seconds` é inteiro obrigatório de 1 a 86400, sem default. É limite
de recuperação escolhido pelo operador, sem significado probatório, score ou
confidence. A policy é `temporal.proximity` 1.0.0, relation kind
`temporal.proximity_candidate`, feature class `DERIVED`.

Cada par não ordenado de eventos distintos aparece uma vez. A/B seguem a chave
canônica da timeline `(occurred_at_utc, platform, event_kind, event_id)`.
Eventos distintos do mesmo ParsedRecord continuam elegíveis. Não há pair_id,
UUID ou digest: os dois event IDs identificam o par nesta projeção.
O DTO imutável `TemporalPairCandidate` é transitório e separado da entidade ORM
`CorrelationCandidate`, que continua exclusiva dos grupos exatos persistidos.

A ordem dos pares é lexicográfica pela **chave completa de A, depois pela chave
completa de B**. Esta é a alternativa explícita que reutiliza a timeline: não
intercala pares pelo horário de B antes dos desempates de A. Testes com timestamps
iguais fixam o contrato. A ordem não representa importância ou força.

A varredura percorre cada A e os B posteriores, interrompendo ao exceder o raio.
O delta é inteiro: `days * 86_400_000_000 + seconds * 1_000_000 + microseconds`.
A inclusão exige `delta_microseconds <= max_delta_seconds * 1_000_000`.
Não há float, timestamp numérico, total_seconds ou aritmética SQLite de datas.
Com entrada ordenada, o custo é O(N + K), sendo K o total de pares elegíveis;
a ordenação da seleção pode custar O(N log N). Não há produto cartesiano em
produção. Janelas densas ainda podem gerar K quadrático.

`limit` tem default 1000 e faixa 1–10000. Não limita eventos nem a contagem:
todos os pares elegíveis são contados, mas somente o prefixo é materializado.
Memória O(N + min(K, limit)); a saída distingue eligible_events, matched_pairs,
returned_pairs e truncated. O limite não reduz o custo de contar K.

Cada endpoint contém somente os nove campos da timeline: event_id,
parsed_record_id, occurred_at_utc, platform, event_kind, normalizer_id,
normalizer_version, time_status e time_basis. Proveniência completa permanece
nos comandos `dee query provenance` e `dee query incident-window`, evitando
duplicar paths, hashes e payloads na projeção temporal.

O JSON usa chaves ordenadas, ASCII escapado e LF explícito, sem relógio ou valores
aleatórios. Mesmos banco e argumentos produzem stdout byte-identical, inclusive
entre Windows e Linux. Não há persistência, runs, output automático, cache,
índices, views, migration ou dependência nova.

## Limites e validação

A seleção dos pares consulta somente os tempos UTC dos current events; não
consulta device/network observations, exact candidates/supports ou pHash.
Proximidade não estabelece mesma pessoa, dispositivo, sessão, autoria ou causa.
Não há inferência de identidade, score, confidence, clustering ou multissinal.
A futura 6B poderá combinar sinais sob contrato separado.

Testes inteiramente sintéticos cobrem precisão e fronteiras, política current,
filtros, empates, mesma origem, ausência de sinais adicionais, limite, memória,
snapshot e determinismo. Uma referência cartesiana apenas nos testes compara
pares, deltas e ordem. A validação real usa helper local ignorado e SQL read-only
independente, com relatório externo; dados reais não entram no Git.
