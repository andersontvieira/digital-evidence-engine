# Modelo de evidências

## Schema implementado (v2)

| Entidade | Campos principais e papel |
| --- | --- |
| Case | UUID, name (nome da pasta), created_at UTC, case_root operacional, inventory_updated_at |
| EvidenceFile | UUID, case_id, ingestion_run_id, relative_path, filename, extension, size_bytes, sha256, mime_type opcional, is_archive, created_at, first_seen_at |
| ArchiveMember | UUID, evidence_file_id, ingestion_run_id, member_path, filename, extension, size_bytes, compressed_size, crc32, sha256, working_relative_path |
| SourceRecord | UUID, ingestion_run_id, exatamente um evidence_file_id ou archive_member_id, location, parser_id, parser_version |
| IngestionRun | UUID, case_id, started_at, finished_at opcional, engine_version, status, files_seen, files_added, errors JSON, zip_limits JSON |
| ParserRun | UUID, source_record_id de inventário, parser_id/version, status, records_parsed, warnings_json, error_code, created_at, finished_at |
| ParsedRecord | UUID, case_id, source_record_id preciso, parser_run_id, parser_id/version, record_type, source_locator, record_index nullable, timestamp_raw nullable, payload_json, annotations_json, created_at |

Um banco por caso, em database/evidence.db. UUIDv4 dispensa sequências locais.
Case.case_root registra localização inicial, sem ser usado para resolver originais
após mover o caso. created_at/first_seen_at são horários de catalogação, nunca
datas de criação do conteúdo. Datas de filesystem não são armazenadas.
MIME é application/zip quando determinado pela estrutura; outros ficam NULL.

## Proveniência

```text
SourceRecord -> EvidenceFile -> original + SHA-256
SourceRecord -> ArchiveMember -> EvidenceFile -> ZIP original + SHA-256
                    |
                    +-> SHA-256 próprio + path relativo em working
```

EvidenceFile representa somente originais nesta milestone. ArchiveMember distingue
extrações e preserva o container. Ambos apontam para a execução produtora.
Constraints SQLite exigem origem existente e exatamente uma referência por
SourceRecord, nunca duas ou nenhuma.

Ingest cria referências estruturais com location=whole-file,
parser_id=evidence_engine.inventory e parser_version igual à versão do motor.
Identificam arquivos completos, **não fingem registros de uma plataforma** e não
carregam payload. Futuros parsers inserirão SourceRecords com localização real
(linha, JSON pointer etc.), identificador e versão próprios.
NormalizedRecord ainda não existe; futuramente apontará para todos os suportes.

Na Milestone 2A, ParsedRecord aponta para um SourceRecord de parsing com locator
preciso e parser_id/version. Este referencia a mesma EvidenceFile ou ArchiveMember;
não há sistema paralelo de origem. SourceRecord.ingestion_run_id conserva a ingestão
produtora da fonte; a execução de parsing é identificada por ParsedRecord.parser_run_id.
ParserRun.source_record_id referencia o inventário original, inclusive em erro ou
fonte não suportada. Nenhum Event, Person, Device ou NetworkEvent foi criado.

Locators usam $ para raiz e tokens JSON Pointer separados por /, com ~0 para tilde
e ~1 para barra. Exemplo: $/messages/17. Não dependem de nome de pasta nem de horário.
Metadata de conversa usa $ e exclui messages; cada mensagem possui seu próprio
payload. Payload mantém apenas o objeto/subconjunto extraído daquele registro,
com valores JSON preservados. Campos extras recebem warning; não são descartados.

timestamp_raw é TEXT contendo escalar JSON (número ou string), ou NULL. Isso conserva
tipo/valor, sem afirmar unidade/timezone. A representação lexical dos bytes originais
permanece na evidência; o parser não preserva espaços/escapes do JSON serializado.
Múltiplos candidatos a timestamp permanecem no payload sem escolha silenciosa.
annotations_json contém somente classificação sintática de IP e códigos explícitos
extraídos de user agent com locator; nenhum nome comercial ou vínculo entre fontes.

Identidade técnica: fonte de inventário + parser_id + parser_version + locator.
Índice único parcial protege o sucesso por fonte/parser/versão; unique(run, locator)
protege os registros. Não foi adicionado record_fingerprint: não é necessário à
idempotência e não deve eliminar observações iguais de exports distintos.

ParserRun FAILED/UNSUPPORTED preserva códigos técnicos/warnings e não possui novos
ParsedRecords válidos. Repetição de uma falha gera tentativa auditável; repetição
de sucesso intacto reutiliza observações. Nova versão pode produzir novo conjunto.
Migração v1 -> v2 é aditiva, explícita e transacional via dee evidence migrate.

## Identidade, idempotência e falhas

Baseline única por (case_id, relative_path). Reingestão recalcula hashes e mantém
IDs, referências e extrações quando nada muda; somente um novo run é gravado.
Tamanho/hash dos membros materializados também são conferidos; derivados ausentes
ou alterados causam falha explícita sem recriação nem alteração da baseline.
Conteúdo igual em paths diferentes mantém EvidenceFiles distintos: hash igual
não elimina ocorrências.

Original alterado/removido causa erro sem substituir o hash anterior. Novos
arquivos processados na mesma execução sofrem rollback. Runs FAILED guardam erro
técnico; files_added=0 significa nenhum registro novo comprometido.
files_seen conta arquivos descobertos, não necessariamente processados até a falha.
RUNNING sem término pode indicar interrupção; não é promovido a sucesso.

ArchiveMember é único por (evidence_file_id, member_path); working_relative_path
também é único. ZIP recusado não deixa inventário parcialmente catalogado.
Diretórios ZIP não geram ArchiveMember. ZIP aninhado é membro opaco.

## Manifesto e verify

JSON v1 inclui schema_version, engine_version, generated_at, case e files.
Arquivos contêm relative_path, size_bytes, sha256 e membros ordenados por member_path
com hash, tamanho, tamanho comprimido e CRC32. Paths absolutos, localização temporária
de extração e payload não são exportados.

generated_at é o instante da atualização do catálogo. Exportações e reingestões
sem mudanças produzem bytes iguais para a mesma versão do motor. Aquisições
independentes têm UUIDs/horários próprios, sem promessa de manifestos idênticos.
Exportação representa a baseline; verify compara SQLite e filesystem atuais,
sem reparar ambos nem importar manifestos externos. SQLite é aberto em modo somente
leitura; bancos ausentes, recovery pendente e WAL provocam erro. O sistema operacional
pode atualizar atime ao ler, dependendo do mount.

## Fatos e interpretação futura

| Nível | Significado | Exemplo sintético |
| --- | --- | --- |
| OBSERVED | Valor encontrado na fonte | Campo contém SYNTHETIC-DEVICE-X |
| DERIVED | Transformação explícita | Conversão de horário com offset conhecido para UTC |
| REPORTED | Afirmação atribuída | Relato sintético associa equipamento a ator de teste |
| HYPOTHESIS | Interpretação a verificar | Dois registros podem corresponder à mesma sessão |

Categorias pertencem às afirmações, inclusive por campo; não são escala de verdade.
Derivações exigem método/versão e entradas; relatos, atribuição; hipóteses,
justificativa e incerteza. Contradições serão preservadas. Entidades de afirmação
ainda não são implementadas. Não inventar dados para preencher contratos.

## Tempo e normalização futura

Preservar timestamp original, precisão, formato, timezone/offset original quando
existente, UTC determinável e horário local derivado com zona. Não usar zona da
máquina para preencher ausência silenciosamente. Horários ambíguos/inexistentes
em mudanças de horário de verão ficam explícitos, sem UTC inventado.

Somente horários operacionais do motor são persistidos agora, como texto UTC com Z.
Deduplicação futura conservará suportes N:N, critérios e versões das regras.
Similaridade incerta será candidata a correlação, não fusão destrutiva.
Hash perceptual futuro não substituirá SHA-256.

## Limites de garantia

SHA-256 verifica consistência com a baseline; não prova autoria, autenticidade
anterior à aquisição ou validade jurídica. Rastreabilidade técnica não certifica
cadeia de custódia. O motor não é software pericial certificado.
