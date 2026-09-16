# Arquitetura

## Milestone 1

Motor local sem rede, sem parsers de plataformas e sem certificação pericial.
Typer coordena a CLI; SQLAlchemy 2.x persiste SQLite; Pydantic 2.x valida limites
de ZIP e DTOs de manifesto, sem duplicar cada entidade ORM.

| Módulo | Responsabilidade |
| --- | --- |
| cli/evidence.py | Opções, mensagens técnicas e exit codes |
| config.py | Limites validados e imutáveis de ZIP |
| ingest/generic/paths.py | Áreas do caso, exclusão de links e descoberta |
| ingest/generic/hashing.py | SHA-256 streaming e verificação de estabilidade |
| ingest/generic/archives.py | Inventário validado e extração ZIP |
| ingest/generic/service.py | Coordenação transacional e proveniência |
| ingest/generic/verification.py | Comparação de originais com baseline |
| models/entities.py | As cinco entidades do catálogo |
| storage/database.py | SQLite, foreign keys e schema v1 |
| reports/manifest.py | Snapshot determinístico e escrita atômica |

Adaptadores de plataformas, correlation, search e media continuam reservados.
Normalização, timezone de eventos e relatórios de dossier são futuros.

## Fluxo e transações

1. Validar raiz externa ao projeto/Git e originals existente; recusar links,
   junctions, hard links e áreas sobrepostas; criar somente áreas graváveis ausentes.
2. Abrir database/evidence.db; inicializar schema vazio com user_version=1
   ou exigir schema reconhecido. Ativar foreign_keys em toda conexão.
3. Persistir IngestionRun RUNNING com UUID, versão, início UTC e limites usados.
4. Adquirir BEGIN IMMEDIATE; descobrir arquivos ordenados e verificar a baseline.
   Escritores SQLite concorrentes são serializados, com timeout de 30 s.
5. Calcular SHA-256 em blocos de 1 MiB, abrindo originais exclusivamente para leitura.
   Comparar identidade, tamanho, mtime e ctime antes/depois; atime fica fora da
   comparação. Esses metadados não são armazenados como datas do conteúdo.
6. Originais idênticos não geram registros repetidos; ausência/alteração aborta
   sem atualizar baseline.
7. Inserir EvidenceFiles novos, extrair ZIPs validados em staging exclusivo,
   criar ArchiveMembers e referências SourceRecord whole-file.
8. Conferir tamanho/hash de todos os membros materializados, inclusive anteriores;
   sincronizar arquivos extraídos e, no POSIX, os diretórios até a raiz do caso.
   Commit dos novos registros, contagens e status COMPLETED. Atualizar instante
   do catálogo somente quando arquivos forem adicionados.
9. Em falha normal, rollback dos novos registros e limpeza do staging próprio.
   Persistir FAILED e erro técnico em transação separada.

Nenhuma execução apaga ocorrências anteriores. Falha de limpeza também é registrada.
Falhas de infraestrutura que impeçam escrever no SQLite podem impedir atualização
final do run. Crash/kill pode deixar RUNNING e staging órfão: não existe transação
conjunta entre banco e filesystem, nem limpeza automática de runs anteriores.
Reingestão recusa extrações ausentes/alteradas, sem restaurá-las; verify se limita
a originais. Após erro de commit, consultar o status persistido antes da limpeza:
se o resultado é incerto ou já comprometido, preservar staging e exigir revisão.

## Caso e isolamento

/case/originals é somente leitura; working, database e output recebem derivados.
Compose monta originals e código read-only, usa usuário não-root e desativa rede
em execução. Não há paths Windows hardcoded. CASE_ROOT fornece default explícito,
sobrescrito por --case-root; somente Compose lê .env.

CasePaths verifica caminhos visíveis e check_path percorre ancestrais. O operador
assegura mounts sem aliases ocultos, originais estáveis e isolamento de processos
hostis. Checagens antes/depois não eliminam todas as corridas de filesystem.
Mount read-only/noatime é necessário quando atime do host deve ser preservado.

## ZIP

Somente primeiro nível, com ZIP aninhado opaco. Validação de todos os nomes, tipos,
duplicatas, conflitos e limites declarados precede a escrita. Durante a extração,
descomprimir o intervalo comprimido inteiro, contar bytes reais e validar CRC/tamanho,
sem o truncamento de ZipExtFile pelo tamanho declarado. Destinos usam nomes gerados:
working/ingest-<run>-<sufixo>/<evidence-id>/<índice>.bin.
Nome de membro e path extraído ficam separados no banco.

Defaults por ZIP: 512 MiB/membro, 2 GiB total, 10000 entradas, razão 200.
STORE/DEFLATE apenas; sem symlinks, criptografia ou extractall. Decoding segue
UTF-8/CP437 do ZIP; erros e nomes não NFC são recusados, sem reparo silencioso.
Diretórios são validados mas não persistidos como arquivos. Colisões por casefold
incluem todos os prefixos implícitos. Leituras de metadados são limitadas a 32 MiB;
entradas reais da central directory são contadas antes da alocação de ZipInfo.
Não há quota global de memória, CPU ou disco.

## Schema e contratos

IDs externos são UUIDv4. Paths relativos distinguem ocorrências; hashes distinguem
conteúdo. EvidenceFile tem unicidade (case_id, relative_path); ArchiveMember,
(evidence_file_id, member_path). SourceRecord exige exatamente uma origem.
Entidades produzidas apontam para IngestionRun. FKs não usam cascade destrutivo.

A baseline v1 é criada transacionalmente em storage/database.py. Como não havia
banco na Milestone 0, não há migração de dados anterior. Versões desconhecidas e
bancos não versionados com tabelas são recusados. Evoluções seguintes exigem
migration explícita testada; Alembic não é necessário nesta baseline.

## Manifesto, verificação e logs

Manifesto exporta a baseline, não afirma integridade atual: execute verify.
Ordenação por relative_path/member_path e serialização estável.
generated_at=inventory_updated_at garante repetibilidade no mesmo catálogo/versão;
UUIDs e horários diferem entre aquisições independentes.
Escrita usa temporário em output, fsync e replace, nunca paths de originals.

Verify compara SQLite e hashes atuais: OK, MISSING, MODIFIED, UNTRACKED.
Exit 1 para divergência/ausência; 2 para erro operacional.
Verify e manifesto leem SQLite com mode=ro e query_only, sem inicialização/migração.
Banco ausente gera erro; hot journal não é recuperado. WAL é recusado antes da
conexão para evitar efeitos colaterais de shared memory. Leituras ainda podem
atualizar atime do host conforme o mount; não há promessa contrária.
Logs registram IDs, contagens e erros técnicos; não incluem payloads, SQL com
parâmetros, tracebacks ou paths absolutos nas mensagens da CLI.

## Dependências e validação

uv 0.8.22 sincroniza uv.lock; setuptools fixado continua backend.
Docker fixa base por digest. Windows/Linux usam o mesmo lockfile; Python 3.12 é
baseline validada. Downloads servem às ferramentas, não à execução do motor.
Pillow/imagehash/BeautifulSoup/lxml/python-dateutil só entram quando utilizados.

Testes sintéticos cobrem integridade, proveniência, idempotência, rollback, CLI,
manifesto e ZIPs adversariais. ADRs 0007–0010 documentam as decisões novas; os seis
princípios originais continuam válidos.
