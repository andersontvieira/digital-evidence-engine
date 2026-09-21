# ADR 0029 — Temporal + Exact Signal Overlap contract

Status: aceito como contrato; implementação 6B futura.

## Contexto e escopo

A Milestone 6B0 é exclusivamente documental. A 6A está concluída; o Milestone 6
como um todo não está completo. A futura 6B — Temporal + Exact Signal Overlap —
responderá: para um par temporal, observations dos ParsedRecords dos dois
endpoints suportam o mesmo candidate exato persistido?

A relation futura será `temporal.exact_signal_overlap_candidate`, sob policy
`temporal_exact_overlap` / `1.0.0`, feature class `DERIVED`. Não é resolução de
identidade, ator ou sessão. Schema continua v5; não se propõe schema v6.

## Unidade base e políticas elegíveis

A entrada é exclusivamente `TemporalPairCandidate` da 6A, cuja policy permanece
`temporal.proximity` / `1.0.0`, relation `temporal.proximity_candidate`, DERIVED.
Reutilizar `temporal_candidates` ou primitive interna apropriada; não implementar
outro algoritmo de proximidade. Preservar janela UTC `[start,end)`, precisão
inteira em microssegundos, filtros exatos platform/event-kind e regras A/B da 6A.
`max_delta_seconds` continua obrigatório e somente um retrieval bound.

Reutilizar `current_event_policy` / `1.0.0`: `meta.event_normalizer` / `1.0.0`,
`google.event_normalizer` / `1.1.0`, `apple.event_normalizer` / `1.0.0`.
Somente eventos current com UTC conhecido participam.

As memberships vêm exclusivamente de `CorrelationSupport` →
`CorrelationCandidate` já persistidos pela 3C1, com allowlist explícita:

| Candidate kind | Observer | Correlator | Regra |
| --- | --- | --- | --- |
| device | device.observer / 1.0.0 | exact_match.correlator / 1.0.0 | device.exact_namespace_value / 1.0.0 |
| network | network.observer / 1.0.0 | exact_match.correlator / 1.0.0 | network.exact_canonical_ip / 1.0.0 |

Na 3C1, device significa igualdade de fact_kind + namespace + raw persistido;
network significa igualdade de IP canonical + versão. Candidates exigem pelo
menos dois supports. São propriedades do contrato persistido, sem estabelecer
identidade. A 6B não recalcula igualdade, não compara raw, não recanonicaliza IP,
não agrupa observations novamente e não executa o correlator. Versões históricas
ou futuras fora da allowlist não entram automaticamente, mesmo que seus IDs
apareçam em outras projeções. Não usar latest/MAX(version).

## Associação e interseções

Para cada endpoint, somente observations com `parsed_record_id` igual ao seu
próprio `parsed_record_id` podem contribuir. Reutilizar a regra de associação
same-record da 4B1 (`same_record_context`), com adaptação bulk compartilhada quando
necessária; não criar uma segunda regra event → observation. Não propagar
observations por evento vizinho, fonte, arquivo, timestamp ou por transitividade
de candidate membership para outro ParsedRecord.

Construir dois conjuntos de candidate IDs por ParsedRecord, passando pelos
supports e pelos filtros de política acima. Para cada par:

```text
shared_device_candidate_ids = device_candidates(A) ∩ device_candidates(B)
shared_network_candidate_ids = network_candidates(A) ∩ network_candidates(B)
```

Um ID compartilhado significa apenas que pelo menos uma observation do registro
de A e pelo menos uma do registro de B suportam o mesmo candidate exato persistido.
É interseção de conjuntos por ID, sem fuzzy match ou similarity. Device e network
não são intercambiáveis nem somáveis como medida de força.

Múltiplas observations/supports de um endpoint para o mesmo candidate geram uma
única membership. Multiplicidade de supports ou occurrences não é peso.
Events distintos do mesmo ParsedRecord continuam presentes; nesse caso,
`same_parsed_record=true` é DERIVED da igualdade dos IDs. As memberships podem
ser as mesmas e até usar a mesma observation: não constituem duas fontes
independentes. O mínimo de dois supports do candidate não implica dois registros
independentes, nem deve ser reinterpretado pela 6B.

Arrays vazios significam somente “nenhum shared persisted exact candidate foi
encontrado sob esta policy”. Ausência de supporting signal não é evidence of
difference: não prova dispositivos, IPs, pessoas ou sessões diferentes.

Overlap não implica mesmo dispositivo físico, pessoa, conta, sessão, rede física,
localização, autoria ou causalidade. São proibidos score, confidence, weight,
rank, strength, probability, likelihood e classificações low/medium/high ou
weak/strong. Não criar `correlated`, `same_actor`, `same_session` ou `same_device`
como booleanos conclusivos. Delta menor não é mais forte: preservar o inteiro
da 6A sem peso nem categorias very close/close/far.

## Interface e projeção futuras

A primeira 6B manterá o universo temporal da 6A. **Não adicionar
`--require-shared-exact`**, nem filtros any/device/network de overlap. Ausência
de sinais deve permanecer observável. Não há novo comando implementado na 6B0;
o nome CLI será fixado na tarefa de implementação 6B.

Cada item terá os seguintes campos conceituais:

| Campo | Contrato |
| --- | --- |
| delta_microseconds | Inteiro exato da 6A, sem alteração |
| event_a, event_b | Exatamente os nove campos técnicos de cada endpoint da 6A |
| same_parsed_record | Booleano DERIVED da igualdade de parsed_record_id |
| shared_exact_candidates.device_candidate_ids | IDs únicos em ordem lexical crescente |
| shared_exact_candidates.network_candidate_ids | IDs únicos em ordem lexical crescente |

Preferir somente arrays; não adicionar counts redundantes na primeira versão.
Sua cardinalidade, se calculada pelo consumidor, mede memberships, nunca força.
Não produzir signal_count ou shared_signal_score. Não retornar raw device,
IP, candidate digest/key, payload ou proveniência completa.

Candidate IDs permitem drill-down com `dee query provenance --kind candidate`.
Event IDs continuam disponíveis para provenance e incident-window. A nova saída
não duplicará essas projeções.

## Prefixo, ordenação e snapshot

Preservar as opções e limites da 6A: raio inteiro 1–86400 segundos; limit default
1000, faixa 1–10000. `eligible_events` e `matched_pairs` continuam descrevendo
todo o universo temporal; `returned_pairs` e `truncated` mantêm a semântica da 6A.
Contar os K pares temporais e materializar somente seu prefixo limitado, depois
enriquecer esse prefixo. Não avaliar overlap para selecionar pares “mais fortes”.
Não afirmar contagens globais de overlap a partir do prefixo enriquecido.

Manter exatamente a ordem 6A: chave completa de A, seguida da chave completa de B;
cada chave é `(occurred_at_utc, platform, event_kind, event_id)`. A/B não mudam.
Não ordenar por candidate count, presença device/network ou riqueza de sinais.
JSON determinístico para mesmos banco e argumentos, sem timestamps de execução.

Uma única execução deve usar **um único `read_catalog` snapshot**, mode=ro e
query_only, para timeline/pares, observations e supports/candidates persistidos.
A API pública atual da 6A possui seu próprio snapshot: a futura composição deve
reutilizar sua primitive temporal dentro da conexão compartilhada, extraindo
uma interface interna se necessário. Não chamar APIs que abram snapshots
independentes nem implementar um segundo opener ou algoritmo temporal.

Estratégia futura, inteiramente em memória:

1. Obter contagem completa e prefixo de pares pela lógica 6A no snapshot.
2. Coletar os parsed_record_ids distintos dos endpoints desse prefixo.
3. Carregar em lote observations elegíveis e seus supports/candidates, projetando
   somente IDs e metadados técnicos necessários, sem raw values.
4. Construir mapas registro → conjunto device e registro → conjunto network.
5. Intersectar os conjuntos por par e ordenar lexicalmente os IDs de saída.

Não executar consulta individual por endpoint, observation ou par (N+1 SQL).
Lotes por limite de parâmetros SQLite são permitidos no mesmo snapshot. O custo
adicional depende dos registros distintos, memberships carregadas e interseções
do prefixo, incluindo ordenação dos IDs, sem materializar K pares. A contagem
temporal mantém seu custo O(N + K) sobre a entrada ordenada; limit não reduz K.

Não há escrita, run, cache, view, index, table, migration ou novo candidate
persistido. O resultado é uma projeção read-only transitória, não ORM 3C1.

## Integridade e erros

Ausência de observations, memberships ou overlap é resultado normal, com arrays
vazios. Política não elegível é exclusão explícita, não promoção automática.
Relação persistida referencialmente inconsistente é erro técnico global: não
retornar JSON de sucesso parcial nem ignorar orphan silenciosamente. A carga
bulk deve permitir detectar links inválidos, sem eliminá-los em inner joins.

Validar no caminho consultado as referências support → candidate/observation,
coerência de candidate_kind, braço device/network, caso e vínculo ao registro.
Para candidates elegíveis alcançados, verificar o contrato de supports (mínimo
de dois e consistência da contagem persistida), sem reconstruir sua igualdade.
Isso pode consultar supports de validação fora dos endpoints; tais supports
nunca propagam membership ao par. A consulta não substitui auditoria global de
partes do catálogo que não foram alcançadas.

## Exclusão de pHash

A camada perceptual liga EvidenceFile / ArchiveMember → ExactMediaContent.
Os pares temporais ligam NormalizedEvent → ParsedRecord. Não existe vínculo
aprovado NormalizedEvent → ExactMediaContent. Portanto pHash fica fora da 6B
inicial. Não inventar associação por filename, time ou path similarity.
Qualquer uso futuro exige milestone explícita de media-event provenance/linking,
com suporte documentado para o vínculo; não inferência silenciosa.

## Plano de testes sintéticos para a futura 6B

Fixtures inteiramente sintéticas deverão cobrir:

- A/B temporalmente próximos sem candidates: dois arrays vazios.
- Candidate device compartilhado: um ID no array device; network vazio.
- Candidate network compartilhado: um ID no array network; device vazio.
- Ambos compartilhados: arrays separados, sem combinação numérica.
- Candidates diferentes: arrays vazios; candidates adicionais não compartilhados
  não entram na interseção.
- Múltiplas observations/supports para o mesmo candidate: ID aparece uma vez.
- Mesmo ParsedRecord: par preservado, same_parsed_record=true, sem alegar
  independência; registros distintos produzem false.
- Observation de outro registro, ainda que vizinho ou na mesma fonte: não propaga.
- Candidate fora da política; versões históricas/futuras de observers,
  correlator e regras: excluídos, sem seleção automática.
- Links órfãos/inconsistentes e contagens de supports inválidas: erro global.
- Nenhum raw, IP, digest/key ou payload na saída; somente campos permitidos.
- Prefixo, contagens e ordem exatamente iguais à 6A, inclusive arrays vazios,
  empates e truncamento; não promover pares com overlap fora do prefixo.
- Snapshot único, read-only, carga bulk sem N+1 e comportamento em lotes.
- JSON determinístico e mesmo contrato de bytes Windows/Linux.

## Plano de validação real futura e questões abertas

Não executar caso real nesta 6B0. Na futura 6B, usar externamente a janela já
validada das seis publicações Meta e os pares da 6A. Comparar por SQL independente
os endpoints, memberships elegíveis, interseções, deltas e ordenação. Não exigir
overlap antecipadamente: ausência é válida. Incluir segunda janela cross-platform,
caso de mesmo ParsedRecord quando existente (cobertura sintética obrigatória,
sem fabricar eventos no catálogo real), prefixo/limit, zero-write e JSON
determinístico Windows/Linux. Relatório e quaisquer dados reais ficam fora do Git.

Não há questão semântica bloqueante neste contrato. Permanecem para a tarefa 6B
o nome exato do comando e a forma concreta da primitive compartilhada/bulk, sem
alterar estas decisões. Próximo passo: implementar uma composição read-only da
primitive 6A com memberships 3C1 no mesmo snapshot, acompanhada dos testes acima;
só depois executar a validação real sob autorização e escopo da milestone 6B.
