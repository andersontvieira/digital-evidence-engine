# Auditoria adversarial — Milestone 1

## Conclusão e escopo

Milestone 1 pronta para receber caso real em originals read-only: **SIM**, para
primeiro uso controlado no runtime canônico Docker/Linux, com áreas externas,
originais estáveis e mount somente leitura verificado. Isso não equivale a uma
certificação pericial nem a garantia contra host comprometido ou falha de energia.

Continuação da auditoria interrompida, preservando o working tree. Não houve
reset, restore, stash, commit, push, mudança de schema ou implementação da Milestone 2.
Somente dados sintéticos foram processados. Data da validação: 2026-09-16.

## Estado encontrado e ajustes da retomada

As três correções solicitadas já estavam implementadas parcialmente, sem validação:
descompressão independente do tamanho declarado, conferência de materialização na
reingestão e colisões casefold incluindo diretórios implícitos. Foram preservadas.
A primeira execução confirmou 110 testes passando: os 81 anteriores e 29 da auditoria.

Também já existiam proteção de SQLite read-only, limites de metadados ZIP,
sincronização antes do commit, preservação de staging após commit incerto e saída
binária do manifesto. Nenhuma delas precisou ser reimplementada.

Na retomada, foram necessários formatação de quatro arquivos, remoção de import sem
uso, correção de uma asserção excessivamente específica da mensagem de colisão,
atualização da documentação e dez casos adicionais relevantes. Não foi encontrada
nova falha funcional nas correções durante essa validação.

Um snapshot local da sessão interrompida foi preservado e excluído pelo .gitignore.
Os scripts/ambientes auxiliares ficaram em área ignorada, sem dados reais.

## Achados e severidade

Não foi identificado achado **critical** no escopo examinado.

| Severidade | Problema | Correção e evidência |
| --- | --- | --- |
| high | Tamanho e CRC do prefixo falsificados permitiam ingerir membro ZIP truncado | Descompressão integral limitada de STORE/DEFLATE, EOF, tamanho real e CRC independentes; quatro variantes falsificadas recusadas com rollback e limpeza |
| high | Exceção após commit podia apagar extrações já referenciadas pelo catálogo | Consulta do status persistido antes da limpeza; commit concluído/incerto preserva staging; injeção de falha after_commit confirma arquivos e run COMPLETED preservados |
| medium | Reingestão declarava sucesso com extração anterior ausente ou modificada | Verificação de existência/tamanho/SHA-256 de todos os membros antes do commit; falha explícita, sem rematerialização nem nova baseline |
| medium | Diretórios implícitos com grafias incompatíveis passavam pela validação ZIP | Validação de todos os prefixos por casefold; impede ambiguidade de proveniência, embora nomes de destino gerados já evitassem sobrescrita direta |
| medium | Verify podia executar recovery e modificar SQLite/journal | mode=ro e query_only; hot journal exige erro sem recovery; WAL recusado antes de conectar; banco inexistente não é criado |
| medium | Contagem de membros era verificada depois da alocação do inventário ZIP | Teto de 32 MiB por leitura de metadados e contagem real antes de ZipInfo, inclusive com contagem falsa no EOCD |
| medium | Falta de confirmação dos derivados imediatamente antes do commit | Conferência final de materialização e fsync de arquivos/diretórios POSIX; falhas de disco, constraint e remoção de derivado provocam rollback |
| low | Encoding/newlines do stdout podiam divergir do manifesto em disco no Windows | Emissão binária UTF-8/LF; teste com saída simulada cp1252/CRLF |
| low | Um teste falhava no código antigo apenas por diferença de mensagem | Regex aceita collision/colliding; comportamento já protegido passou a ser identificado corretamente |
| low | Documentação ainda descrevia limites e comportamento anteriores | README, arquitetura, modelo e ADRs atualizados, sem promessas de atomicidade total |

## Prova de regressão e testes

Onze casos selecionados foram executados contra a imagem anterior, sem montar o
código corrigido: **9 falharam, 2 passaram**. As falhas reais foram quatro ZIPs
falsificados, duas colisões de diretórios implícitos, duas extrações danificadas e
um hot journal. Os dois controles já corretos eram colisão arquivo/diretório e
diretórios explícitos com case diferente. Não se atribuiu esses controles à correção.

O arquivo tests/test_adversarial_audit.py contém **39 casos parametrizados**:

- ZIP falsificado com tamanho zero/um e CRC do prefixo em STORE/DEFLATE.
- Diretórios implícitos/ explícitos case-insensitive, UNC, separadores mistos,
  nome vazio e quatro tipos de arquivos especiais.
- Limite de leitura de metadados e contagem anterior à alocação de ZipInfo.
- Extrações antigas ausentes/alteradas e nova extração removida antes do commit.
- Falha de fsync/disco, violação real de FK após extração, exceção após commit
  e processo encerrado antes do commit.
- SQLite hot journal, WAL, duas conexões read-only com FKs ativas e recusa de UPDATE.
- Mesmo filename em diretórios diferentes, UUIDs v4 distintos, remoção/restauração,
  original vazio/grande, rename e diretório extra.
- Manifesto UTF-8/LF, stdout Windows simulado e generated_at estável sem mudança
  efetiva do catálogo, mudando quando um novo original é adicionado.
- Seis ZIPs válidos com payload de vários blocos: STORE/DEFLATE combinados com
  formato clássico, header local ZIP64 e data descriptor.
- Verify/manifest sem catálogo, sem criar arquivos, e SourceRecord com duas
  origens válidas recusado pela constraint de exclusividade.

Os dez casos adicionados nesta retomada são: seis variantes ZIP válidas, uma
colisão explícita de diretórios, duas leituras sem catálogo e uma origem dupla.
Snapshots também passaram a conferir mtime, ctime e modo, além de bytes.
Atime foi excluído deliberadamente, pois depende do filesystem/mount do host.

Os testes da auditoria exercitam comportamento observável. Há injeção de falhas
em fronteiras internas para tornar reproduzíveis disco cheio, interrupção e erro
de commit; o teste de contagem inspeciona a alocação porque essa é a falha de recursos.

## Pontos que já estavam corretos

- Originais são abertos O_RDONLY; destinos de extração e manifesto ficam separados.
  Não há rename, unlink, alteração de permissão ou timestamp de originals no motor.
  Links, junctions, hard links, arquivos especiais e áreas sobrepostas são recusados.
- Chave lógica de idempotência: **(case_id, relative_path)**. Filename ou hash
  isolado não identifica ocorrência. Alteração/ausência nunca troca a baseline.
- SHA-256 streaming em blocos de 1 MiB; teste de stream limita leituras e exige
  múltiplos blocos. Membros extraídos possuem hash próprio e referência ao container.
- SourceRecord exige exatamente EvidenceFile OU ArchiveMember e contém location,
  parser_id e parser_version. A cadeia futura Event -> SourceRecord -> origem
  permanece possível; Event não foi implementado. Inventário usa whole-file.
- UUIDv4 gerado por uuid4, persistido em String(36)/VARCHAR textual e serializado
  como string; igualdade por ID, sem dependência de sequência incremental externa.
- foreign_keys é habilitado no evento connect, para toda conexão; constraints de
  unicidade e origem impedem os órfãos relacionais cobertos. Não há cascades destrutivos.
  Índices explícitos por caso/container e índices únicos atendem ao acesso atual.
- Schema v1 com user_version, criação transacional e recusa de versões desconhecidas.
  Alembic foi conscientemente adiado; evolução futura exige migration explícita.
- Manifesto ordenado, schema_version explícito e generated_at derivado do catálogo,
  sem paths absolutos. Determinismo vale no mesmo catálogo e versão do motor.
- Runtime: Typer, SQLAlchemy e Pydantic têm uso concreto; dev separado. uv.lock é
  realmente consumido por uv sync --locked; Python 3.12, uv e setuptools fixados,
  imagem base por digest. Nenhuma dependência ou versão foi atualizada na auditoria.

## Validação final

Comandos Docker foram executados individualmente, sem orquestrar vários comandos
de validação por subprocess dentro do container. Runtime: Linux, Python 3.12.14.

| Verificação | Resultado |
| --- | --- |
| python -m pytest -p no:cacheprovider | **120 passed in 22.45s**, sem skips; 81 anteriores + 39 da auditoria |
| ruff check --no-cache . | All checks passed! |
| ruff format --check --no-cache . | 52 files already formatted |
| mypy --cache-dir=/tmp/dee-mypy src | Success: no issues found in 26 source files |
| docker build -t digital-evidence-engine:dev . | Sucesso, uv sync --locked no build |
| docker compose config --quiet, com env temporário sintético | Exit 0 |
| docker compose build, mesmo env | Sucesso |
| git diff --check | Sem erros |

E2E Compose com diretórios sintéticos externos: originals montado ro confirmado
por mountinfo; UID não-root e somente interface loopback. Ingest inicial adicionou
dois arquivos, verify retornou OK, reingest adicionou zero, manifesto permaneceu
idêntico. Bytes/hashes, mtime e modo dos originais foram preservados; verify não
alterou o snapshot do banco. Modificação e remoção sintéticas geraram MODIFIED e
MISSING, acompanhados de UNTRACKED para arquivo extra, com exit 1. Remover uma
extração causou falha explícita, run FAILED e baseline preservada, com exit 2 real
confirmado usando exit $LASTEXITCODE no PowerShell.

## Riscos residuais

- Banco e filesystem não são uma transação única. Crash deixa potencial RUNNING
  e staging órfão; não há recovery/limpeza automática. Commit incerto exige revisão.
- fsync reduz janelas de perda, mas não garante persistência física em todos os
  hosts. Diretórios Windows nativos não têm a mesma sincronização implementada.
- Atime depende do host/mount. Read-only no container não prova preservação de
  atime no armazenamento subjacente; use noatime/snapshot apropriado se necessário.
- Não há proteção integral contra processo hostil alterando paths/mounts entre
  checagens. Catálogo e áreas graváveis são confiáveis; não há autenticação da baseline.
- Limites ZIP são locais, sem quota global de disco/memória ou timeout. Alguns ZIPs
  legítimos serão recusados pela política conservadora; não há tentativa de reparo.
- Verify cobre originais. Integridade dos derivados é conferida pela reingestão;
  extrações ausentes não são restauradas automaticamente.
- Windows nativo completo não foi executado: comportamento de encoding foi
  simulado; a suíte completa e o E2E rodaram em Linux no Docker Desktop.
- Lockfile fixa resolução, mas não promete imagem bit a bit idêntica nem auditoria
  de vulnerabilidades das dependências. Atualizações exigem revisão deliberada.

## Privacidade e arquivos

Inspeção dos candidatos rastreados e novos, mais busca por identificadores pessoais,
contatos, IPs, paths de usuário e padrões de segredos, não encontrou dados reais.
Não há SQLite, ZIP ou artefatos de execução entre os candidatos ao Git. O snapshot
local da auditoria foi mantido e ignorado; o contexto Docker permanece em allowlist.

Arquivos da correção: cli/evidence.py; ingest/generic/{archives,paths,service,
verification}.py; reports/manifest.py; storage/database.py; tests/test_adversarial_audit.py.
Na retomada, mudanças de código foram apenas formatação; os ajustes funcionais
adicionais foram nos testes. Documentação: README, architecture, evidence-model,
ADR 0008, nova ADR 0010 e este relatório; .gitignore exclui o snapshot local.

O diff abaixo é contra o último commit, ainda da Milestone 0: inclui a Milestone 1
inteira. git diff --stat não inclui os arquivos novos indicados por ?? no status.

```text
 .dockerignore                                  |   1 +
 .env.example                                   |   2 +
 .gitignore                                     |   3 +
 AGENTS.md                                      |  11 +-
 Dockerfile                                     |  13 +-
 README.md                                      | 266 ++++++++++++++++++-------
 docker-compose.yml                             |   2 +
 docs/architecture.md                           | 207 ++++++++++---------
 docs/evidence-model.md                         | 151 ++++++++------
 pyproject.toml                                 |   4 +-
 src/evidence_engine/cli/__init__.py            |   6 +-
 src/evidence_engine/ingest/__init__.py         |   2 +-
 src/evidence_engine/ingest/generic/__init__.py |   2 +-
 src/evidence_engine/models/__init__.py         |   2 +-
 src/evidence_engine/reports/__init__.py        |   2 +-
 src/evidence_engine/storage/__init__.py        |   2 +-
 16 files changed, 435 insertions(+), 241 deletions(-)
```

```text
 M .dockerignore
 M .env.example
 M .gitignore
 M AGENTS.md
 M Dockerfile
 M README.md
 M docker-compose.yml
 M docs/architecture.md
 M docs/evidence-model.md
 M pyproject.toml
 M src/evidence_engine/cli/__init__.py
 M src/evidence_engine/ingest/__init__.py
 M src/evidence_engine/ingest/generic/__init__.py
 M src/evidence_engine/models/__init__.py
 M src/evidence_engine/reports/__init__.py
 M src/evidence_engine/storage/__init__.py
?? docs/adr/0007-catalog-baseline-and-run-transactions.md
?? docs/adr/0008-conservative-first-level-zip-extraction.md
?? docs/adr/0009-locked-python-environments.md
?? docs/adr/0010-adversarial-integrity-boundaries.md
?? docs/adversarial-audit-milestone-1.md
?? src/evidence_engine/cli/evidence.py
?? src/evidence_engine/config.py
?? src/evidence_engine/errors.py
?? src/evidence_engine/ingest/generic/archives.py
?? src/evidence_engine/ingest/generic/hashing.py
?? src/evidence_engine/ingest/generic/paths.py
?? src/evidence_engine/ingest/generic/service.py
?? src/evidence_engine/ingest/generic/verification.py
?? src/evidence_engine/models/entities.py
?? src/evidence_engine/reports/manifest.py
?? src/evidence_engine/storage/database.py
?? tests/conftest.py
?? tests/integration/test_evidence_cli.py
?? tests/test_adversarial_audit.py
?? tests/test_archives.py
?? tests/test_case_paths.py
?? tests/test_foundation.py
?? tests/test_hashing.py
?? uv.lock
```
