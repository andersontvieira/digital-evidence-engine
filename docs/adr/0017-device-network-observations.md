# ADR 0017 — Device/Network Observations

Status: aceita. Entrega: Milestone 3B.

## Decisão

DeviceObservation e NetworkObservation derivam diretamente de ParsedRecord (OBSERVED).
São representações DERIVED de fatos técnicos atômicos, sem entidades Device/Network,
identidade, autoria, ownership, sessões, scores ou correlação.

Não derivam de NormalizedEvent: versões de normalização coexistem e multiplicariam
as mesmas entradas; inventário Apple não produz eventos; Raw User Agents Google
contém tokens que não foram projetados nos eventos. Nenhum timestamp/payload de
evento é duplicado nesta camada.

Schema v4 adiciona apenas observation_runs, device_observations e network_observations.
Novos bancos nascem v4; `dee evidence migrate` percorre v1 -> v2 -> v3 -> v4 em
uma transação explícita. Nenhuma linha anterior muda. Escritas exigem v4;
verify/manifest continuam lendo v2/v3 sem migrar. Backup consistente é obrigatório
na operação controlada antes de migrar um caso existente.

Dois observers estáticos, `device.observer` e `network.observer`, versão 1.0.0,
selecionam parser_id, parser_version e record_type conhecidos. Mudança nas regras
exige nova versão; resultados anteriores permanecem. Google ChangeHistory é um
contrato reconhecido sem campos device suportados. Mensagens/conversas Meta não
possuem contrato device nesta versão e não recebem observações de IP.

## Regras e ordem

Device facts têm fact_kind identifier/model e namespace específico da fonte:
meta.device_id, meta.user_agent.model_code, google.user_agent.model_code,
apple.device_identifier, apple.serial_number, apple.imei, apple.meid,
apple.hardware_model. Device Identifier Apple não é chamado de UDID.

Meta usa campos raiz device_id/device_identifier e ip/ip_address, os equivalentes
em string_map_data, e observed_field annotations dos parsers 1.0.0/1.1.0.
Ordem: campos raiz na ordem explícita das regras; labels de string_map_data
ordenados; annotations na ordem preservada. A mesma posição de campo representada
em payload e annotation conta uma vez; posições distintas mantêm ocorrências.
Modelos vêm somente de model_code_from_user_agent annotations, após os IDs,
sem nova análise do user agent. Caption/content nunca são escaneados.

Google 1.0.0 extrai somente de SubscriberInfo/google_security_activity/Raw User Agents
tokens `iPhone[0-9]+_[0-9]+`, case-sensitive, sem caracteres de palavra ou vírgula
adjacentes. Tokens distintos seguem a primeira ocorrência; repetição do mesmo token
no mesmo campo conta uma vez. Não há deduplicação entre ParsedRecords. Vírgulas,
nomes comerciais e outros campos/artefatos não são convertidos.

Apple 1.0.0: inventário em ordem serial, IMEI, MEID, model name; sign-on somente
Device Identifier; mídia Device Identifier seguido de Device Hardware Model.
ICCID, telefone e hardware family não são device facts. Para esses campos Apple,
os marcadores vazios, n/a, not available, not applicable, null, none e - são
ausência (comparação casefold/strip apenas para reconhecer o marcador). Valores
úteis mantêm espaços, case, hífens, zeros e representação originais.

Network roles: meta.activity_ip, google.activity_ip, google.change_ip,
apple.heartbeat_ip, apple.signon_ip, apple.media_ip. Cada campo explícito preenchido
gera uma ocorrência, mesmo repetido em outros registros. `ipaddress.ip_address`
classifica somente strings, sem trim: válido guarda canonical e versão 4/6;
inválido conserva raw, canonical/version NULL e aviso INVALID_IP_SYNTAX.
Escalares numéricos não são reinterpretados como IPv4. Ausentes/brancos não geram
fatos; objetos/listas são recusados como campos não escalares com aviso técnico.
Nenhum lookup, geolocalização ou propagação entre registros é realizado.

## Proveniência, persistência e limites

value_raw/ip_raw são escalares JSON em TEXT, como os demais raw fields do catálogo;
decodificar JSON recupera exatamente tipo e valor do ParsedRecord. Não há
value_canonical para devices. source_field_locator reutiliza annotations ou
concatena o locator do registro e o header escapado (~0/~1). Annotations são
validadas contra o próprio payload; modelo anotado deve existir no campo indicado.
Para tokens UA, o locator aponta ao campo textual inteiro.

Cadeia: Observation -> ParsedRecord -> SourceRecord -> ArchiveMember/EvidenceFile
-> original e SHA-256. Observers não abrem originals/working. Confiam no catálogo
preservado; verify é uma operação separada de integridade dos originais.

Identidade: ParsedRecord + observer_id + versão + observation_ordinal (zero-based).
BEGIN IMMEDIATE serializa cada observer; savepoint reverte todas as novas
observações de um run que falhar. FAILED permanece auditável quando persistível;
o outro observer pode continuar. Commit incerto é inspecionado antes de registrar
falha; sucesso já durável é preservado. Não há limpeza automática de runs antigos.

Reexecução deriva novamente e compara os campos de observações existentes, sem
alterá-los; divergência aborta o run. Registros que produzem zero fatos não exigem
outra tabela de controle. Warnings persistem apenas como códigos/contagens.
records_supported conta contratos reconhecidos, mesmo sem campos presentes;
records_skipped conta contratos não suportados. O resumo CLI conta registros uma
vez na união dos observers, e cada run mantém suas próprias contagens.

Fatos iguais em fontes/linhas distintas nunca são fundidos. Um ID repetido não
implica número de aparelhos; IP repetido não implica rede, pessoa ou sessão comum.
Correlação permanece fora desta entrega.
