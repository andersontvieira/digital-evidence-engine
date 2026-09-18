# ADR 0015 — Eventos DERIVED e migração explícita v3

Status: aceita. Escopo: Milestone 3A.

## Decisão

Adicionar somente NormalizationRun e NormalizedEvent ao schema v3. Novos bancos
nascem v3. `dee evidence migrate` avança v1 -> v2 -> v3 em uma transação explícita;
qualquer falha desfaz todos os passos dessa execução. A migração v2 -> v3 cria
apenas as duas tabelas/índices e muda user_version, sem atualizar linhas existentes.
Verify/manifest podem ler v2 sem migrar; ingest/parse/normalize exigem a versão atual.
O comportamento de recusa de v1 antes de migração permanece. Fazer backup consistente
antes da migração; validar contagens/IDs/fingerprints e manter o backup fora do Git.
Não há downgrade automático, reconstrução do banco ou Alembic.

Três normalizers estáticos 1.0.0: meta.event_normalizer, google.event_normalizer e
apple.event_normalizer. Seleção exige parser_id, versão conhecida e record_type
exato. O normalizer recebe somente ParsedRecord, nunca lê evidência bruta.

| Origem | Tipo de evento |
| --- | --- |
| Meta profile_activity | account.profile_activity |
| Meta recently_deleted_content | content.activity |
| Instagram message | communication.message |
| Google SubscriberInfo | account.security_activity |
| Google ChangeHistory | account.change |
| Apple sign-on | account.sign_on |
| Apple media | media.activity |

Conversation-level e Apple device_inventory são skips intencionais. Cada registro
elegível gera um evento com event_ordinal=0. Identidade técnica única:
parsed_record_id + normalizer_id + normalizer_version + event_ordinal.
Fontes/exports independentes permanecem eventos distintos. Versões de normalizers
podem coexistir; não há deduplicação de acontecimentos ou resolução de identidade.

Uma transação por normalizer, com savepoint para todos os eventos novos. Falha
reverte os novos eventos do run e preserva NormalizationRun FAILED quando persistível;
outros normalizers continuam. Runs anteriores e seus eventos não são apagados.
Commit incerto exige inspeção de persistência: sucesso durável não é revertido nem
renomeado como falha; a CLI retorna erro operacional para revisão.

## Campos e tempo

ParsedRecord é extração OBSERVED; NormalizedEvent é representação DERIVED. A FK
preserva a cadeia até SourceRecord e EvidenceFile/ArchiveMember e seus hashes.
Não copiar payload completo. Campos *_raw são escalares JSON serializados em texto,
como timestamp_raw do ParsedRecord, preservando tipo, zeros textuais e vazios.
Ausência de campo é NULL. Timestamp_raw é copiado byte a byte do ParsedRecord.

Campos explícitos de payload e annotations observed_field alimentam IP, identifier,
modelo, action e status. string_map_data Meta usa somente nomes equivalentes
explícitos. Conflitos de valores deixam o campo NULL com diagnóstico AMBIGUOUS_FIELD;
dados completos continuam no ParsedRecord. Não atribuir significado a códigos de
status. Códigos de modelo em user agent só são copiados de annotations já produzidas
pelo parser, sem nova extração. Múltiplos modelos diferentes são ambíguos.

Timestamp principal permanece o escolhido pelo parser. Não substituir por horários
aninhados de criação/atualização/login. Inteiros Meta nos campos timestamp e
creation_timestamp são epoch seconds; timestamp_ms é epoch milliseconds, somente
quando corresponde ao timestamp principal e há um único papel identificado.
Não usar magnitude como heurística nem converter texto numérico em epoch.
Demais números e papéis desconhecidos ficam raw_only.

Strings aceitas: data/hora ISO com segundos, fração opcional de até seis dígitos e
Z, offset explícito HH:MM/HHMM ou sufixo literal UTC. Calendário e offset precisam
ser válidos. UTC é escrito com precisão fixa de microssegundos e sufixo Z, sem
dependência do timezone da máquina. Formatos fora do contrato, datas sem timezone,
overflow e ambiguidades ficam raw_only, com occurred_at_utc NULL e warning técnico.
Timestamp principal NULL ou string vazia recebe missing, mantendo timestamp_raw.
time_basis registra somente a base técnica. Não usar timezone do caso, StoreFront,
IP ou sistema. Não há conversão para horário local persistida.

## Limites

Sem Person/Device/Account/Network canônicos, ownership, correlação, extração adicional
de user agent, ASN/geolocation, timeline/search, WhatsApp ou interpretação de autoria.
Normalização não verifica novamente bytes de originais: integridade é um gate
separado via verify. Alteração externa de ParsedRecords após normalização não é
reconciliada automaticamente; os contratos pressupõem observações catalogadas estáveis.
Formatos desconhecidos exigem nova decisão/versionamento, não regras derivadas do
gabarito real para atingir contagens ou horários desejados.
