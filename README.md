# digital-evidence-engine

Motor técnico local para preservação, catalogação e rastreabilidade de evidências
digitais, preparado para futura indexação, normalização, pesquisa e correlação.

**Não é software pericial certificado.** Hashes verificam consistência de conteúdo;
não comprovam autoria, autenticidade anterior à aquisição ou admissibilidade.

**Real case evidence must never be committed to this repository.**

## Estado atual

Milestone 2A: Evidence Foundation mais framework de parsing e três artefatos
Instagram/Meta. Não há parsers de Google, Apple ou WhatsApp, normalização de eventos,
timeline, correlação, OCR, IA/ML, dashboard ou integrações externas.

## Arquitetura e preservação

Originais nunca são criados, editados, renomeados, apagados nem recebem mudanças de
permissões pelo motor. Casos ficam fora do repositório. Links, junctions, hard links
e áreas sobrepostas são recusados. Mesmo conteúdo em paths diferentes preserva
ocorrências distintas. Hashes catalogados nunca são substituídos silenciosamente.

O pacote src/evidence_engine separa CLI, ingestão genérica, modelos, persistência
e manifestos. SourceRecord aponta para EvidenceFile ou ArchiveMember, ligado ao
ZIP original, ao SHA-256 e à execução que produziu o registro. OBSERVED, DERIVED,
REPORTED e HYPOTHESIS permanecem conceitos separados. ParsedRecord armazena os
valores extraídos, sem interpretação ou entidades Event. Horários operacionais são UTC;
timestamps de filesystem não são tratados como criação de conteúdo.

O aplicativo não usa rede, telemetria, upload ou APIs externas. Consulte
[arquitetura](docs/architecture.md), [modelo](docs/evidence-model.md),
[ADRs](docs/adr/) e [regras de trabalho](AGENTS.md).

## Instalação reproduzível

Requer Python 3.12+; a baseline validada é Python 3.12. Dependências de execução:
Typer, SQLAlchemy 2.x e Pydantic 2.x. pytest, Ruff e mypy são de desenvolvimento.
uv.lock fixa versões transitivas e hashes, incluindo marcadores Windows/Linux.
uv 0.8.22 sincroniza o ambiente; setuptools e o layout src são mantidos.

PowerShell no Windows 11:

```powershell
py -3.12 -m pip install --user uv==0.8.22
py -3.12 -m uv sync --locked --extra dev --python 3.12
.\.venv\Scripts\dee.exe --help
.\.venv\Scripts\dee.exe version
```

Selecione .venv/Scripts/python.exe no VS Code. No Linux/macOS, com uv 0.8.22
instalado, use `uv sync --locked --extra dev --python 3.12` e ative
`source .venv/bin/activate`. Os comandos abaixo pressupõem o ambiente ativado.
Sem ativação no Windows, use `.\.venv\Scripts\dee.exe`.

Downloads acontecem somente na instalação/build. Para atualizar dependências
deliberadamente, altere pyproject.toml, execute `uv lock --python 3.12`, revise
uv.lock e repita as verificações. Não use --upgrade incidentalmente.
Pillow, imagehash, BeautifulSoup/lxml e python-dateutil seguem adiados até uso concreto.

## Caso e CLI

A raiz deve existir e conter originals/. Ingest cria as outras três áreas se
ausentes, nunca originals/. Todos os diretórios ficam fora do projeto.

```text
/case/
├── originals/   # somente leitura
├── working/     # extrações
├── database/    # evidence.db
└── output/      # manifest.json
```

```sh
dee --help
dee version
dee evidence --help
dee evidence ingest --case-root /case
dee evidence manifest --case-root /case
dee evidence verify --case-root /case
```

CASE_ROOT no ambiente fornece o default; --case-root tem precedência.
A CLI nativa não carrega .env automaticamente. Compose lê .env para os volumes e
define CASE_ROOT=/case dentro do container.

Ingest enumera originais em ordem estável, calcula hashes, verifica a baseline,
extrai ZIPs novos e persiste em transação. Cada execução tem UUID e status.
Repetir sem mudanças adiciona somente IngestionRun. Arquivo novo gera ocorrência;
original modificado ou ausente causa erro e rollback de todas as novas evidências
dessa execução. Use verify para obter os paths afetados.
Reingestão também confere tamanho e hash das extrações catalogadas: ausência ou
alteração provoca erro explícito, sem rematerialização automática.

Manifest grava atomicamente output/manifest.json e emite o mesmo JSON em stdout.
Inclui schema_version, engine_version, generated_at, case e files, com membros
dos ZIPs ordenados. Não inclui paths absolutos. **generated_at é o instante de
atualização do catálogo**, não o horário de cada exportação. Mesmo catálogo e
versão do motor geram bytes idênticos, inclusive após reingestão sem mudanças.
Aquisições independentes têm UUIDs/horários próprios e não geram manifestos iguais.

Verify recalcula hashes contra o SQLite, sem reparo ou alteração de baseline:

| Estado | Significado |
| --- | --- |
| OK | Hash coincide |
| MISSING | Original catalogado ausente |
| MODIFIED | Hash diverge |
| UNTRACKED | Arquivo presente ainda não catalogado |

Exit codes: 0 para sucesso (inclusive UNTRACKED isolado), 1 para MISSING/MODIFIED,
2 para erro técnico/configuração ou ingestão recusada. Verify usa o banco, não
importa manifestos externos e não verifica derivados em working.
Verify e a leitura do manifesto abrem SQLite em mode=ro e query_only. Banco ausente
não é criado; journal que exige recovery gera erro, sem recuperação automática.
Catálogos configurados externamente em WAL são recusados para evitar criação de
arquivos compartilhados. A baseline usa DELETE journal mode.

## Parsing Instagram/Meta

**PARSE ≠ NORMALIZE ≠ CORRELATE.** O parser consulta somente fontes já catalogadas,
confere SHA-256 e preserva valores de cada registro. Campos desconhecidos são
mantidos no payload daquele registro com warning; não há reparo de texto, inferência
de destinatário, nome comercial de aparelho ou associação de IP/device entre fontes.

```sh
dee parse --help
dee parse instagram --case-root /case
```

Catálogos novos usam schema v2. Um catálogo v1 existente é recusado pelos comandos
até migração explícita. Faça backup consistente do catálogo antes de migrar:

```sh
dee evidence migrate --case-root /case
```

A migração transacional adiciona somente parser_runs e parsed_records e atualiza
user_version; conserva IDs, hashes e tabelas da Foundation. Não cria caso ausente,
não migra versões desconhecidas e não é acionada automaticamente pelo parsing.
O schema do manifesto de evidências permanece v1, independente do schema SQLite.

Contratos suportados por parsers versão 1.0.0:

| Artefato/path | Estrutura mínima | Parser |
| --- | --- | --- |
| profile_activity.json, inclusive sob prefixo de export | objeto com profile_account_insights: lista de registros | meta.profile_activity |
| recently_deleted_content.json, inclusive sob prefixo de export | objeto com recently_deleted_media: lista de registros | meta.recently_deleted_content |
| messages/inbox/**/message_<número>.json | objeto com messages: lista e title textual ou participants: lista | meta.instagram_messages |

São contratos explícitos testados com fixtures sintéticos, não uma promessa de
compatibilidade com todas as variantes históricas da Meta. Nome correto com outra
estrutura gera UNSUPPORTED e warning auditável; não produz observações. Cada item
deve ser objeto com pelo menos um campo do artefato; item inválido aborta a fonte.
As tabelas de campos e validações ficam em ingest/instagram/parsers.py.

Cada observação aponta a SourceRecord e a um locator como
$/profile_account_insights/12 ou $/messages/17. A conversa é um registro separado
em $, contendo metadata sem repetir a lista de mensagens. Metadata de conversa
presente em arquivos diferentes continua sendo observação de cada fonte.

timestamp_raw guarda o valor JSON original, sem conversão UTC ou timezone inferido.
Vários timestamps candidatos ficam preservados no payload com warning, sem escolher
um deles. Timestamps internos de media ficam no respectivo objeto do payload.
IP recebe apenas classificação sintática; inválidos permanecem raw com warning.
Código de modelo explicitamente presente no user agent recebe anotação com o locator
de origem; não é convertido em nome comercial nem propagado para outro registro.

Repetir parsing intacto adiciona zero registros. A identidade é fonte de inventário
+ parser_id + parser_version + locator. Duas exportações iguais continuam separadas;
versões distintas do parser também. Falha desfaz todos os ParsedRecords e SourceRecords
de parsing daquela fonte, registra ParserRun FAILED e permite continuar as demais.
Tentativas falhas/unsupported permanecem auditáveis; sucesso anterior é reutilizado
somente após nova conferência do conteúdo. Não há reparse sofisticado nem reparo.
Falha no commit final tem resultado conferido no catálogo: se houve rollback,
registrar COMMIT_FAILED quando o armazenamento permitir; se já houve persistência,
preservar o resultado e retornar erro operacional para revisão manual.

A saída JSON da CLI contém apenas contagens, incluindo records_parsed (novos) e
records_existing (já processados). Exit 0 inclui warnings/unsupported; exit 1 indica
falhas em fontes, com resultados válidos de outras fontes preservados; exit 2 indica
erro operacional global/configuração/schema. Consulte warnings_json/error_code em
parser_runs para diagnósticos, sem payloads no console.

Limites fixos: 32 MiB por fonte JSON, profundidade 64 e 100000 registros por fonte,
incluindo a conversa. O JSON é carregado em memória dentro desse limite. UTF-8 e BOM
UTF-8 são aceitos; chaves duplicadas, números não finitos e JSON inválido são recusados.
Paths de seleção também precisam ser relativos e canônicos, sem segmentos . ou ..,
backslashes ou prefixos de drive. Catálogos existentes passam por pré-verificação
read-only antes de abertura gravável normal, impedindo recovery de v1 antes da recusa.

## Política de ZIP

Somente o primeiro nível é extraído. ZIP aninhado é membro opaco. Reconhecimento
usa a estrutura ZIP, não só a extensão; .zip inválido provoca erro explícito.

Limites por ZIP, configuráveis no comando ingest:

| Opção | Default |
| --- | --- |
| --max-file-bytes | 536870912 (512 MiB) |
| --max-total-bytes | 2147483648 (2 GiB) |
| --max-members | 10000, incluindo diretórios |
| --max-ratio | 200 |

Exemplo: `dee evidence ingest --case-root /case --max-members 500 --max-ratio 100`.

O inventário inteiro é validado antes da escrita. Recusamos traversal, paths
absolutos/Windows, backslashes, links e arquivos especiais, duplicatas e colisões
de maiúsculas, nomes não portáveis, Unicode inválido/não NFC, criptografia e métodos
diferentes de STORE/DEFLATE. Nomes não são corrigidos silenciosamente. Limites de
bytes também valem durante leitura; CRC e tamanho são conferidos. Sem extractall.
A descompressão mede todo o intervalo comprimido, independentemente do tamanho
declarado, para impedir truncamento com CRC falsificado. Colisões incluem diretórios
implícitos. Metadados ZIP têm limite fixo de 32 MiB por leitura; a contagem real da
central directory é limitada antes da criação dos objetos de membros.

Extrações usam diretório exclusivo por execução e nomes numerados .bin.
member_path/filename originais ficam no banco: nenhum nome do ZIP vira destino.
Diretórios vazios são validados mas não recebem ArchiveMember. Falhas normais
removem somente staging próprio e fazem rollback; originais permanecem intactos.

## Docker Desktop

Use containers Linux. A imagem base está fixada por digest e instala o lockfile.

```powershell
docker build -t digital-evidence-engine:dev .
docker run --rm --network none digital-evidence-engine:dev dee --help
Copy-Item .env.example .env
# Configure quatro diretórios externos existentes em .env.
docker compose config --quiet
docker compose build
docker compose run --rm dee dee evidence ingest
docker compose run --rm dee dee evidence manifest
docker compose run --rm dee dee evidence verify
```

Container não-root, sem rede; código e originals são montados somente para leitura.
Compose não cria paths ausentes silenciosamente. Use paths absolutos com / no
Windows. No Linux ajuste DEE_UID/DEE_GID e permissões das áreas graváveis, sem
alterar originais. Áreas não podem sobrepor originais nem seus ancestrais, inclusive
na topologia de mounts do host. Mudanças de dependências/metadata exigem rebuild.

## Testes e qualidade

```sh
python -m pytest
ruff check .
ruff format --check .
mypy src
```

Ou no container:

```sh
docker compose run --rm dee python -m pytest -p no:cacheprovider
docker compose run --rm dee ruff check --no-cache .
docker compose run --rm dee ruff format --check --no-cache .
docker compose run --rm dee mypy --cache-dir=/tmp/dee-mypy src
```

Fixtures são gerados em diretórios temporários com nomes synthetic-* e conteúdo
artificial. A suíte cobre imutabilidade, hashes, proveniência, rollback, CLI e
ZIPs adversariais. Nenhum export real é necessário.

Crie um caso sintético fora do repositório com Python 3.12:

```python
from pathlib import Path
import tempfile
import zipfile

root = Path(tempfile.mkdtemp(prefix="synthetic-dee-"))
(root / "originals").mkdir()
(root / "originals/synthetic-document.txt").write_bytes(b"synthetic document")
with zipfile.ZipFile(root / "originals/synthetic-export.zip", "w") as archive:
    archive.writestr("synthetic-folder/synthetic-member.txt", b"synthetic member")
print(root)
```

Use o caminho impresso nos três comandos CLI. Repetir ingest retorna files_added=0.
Alterar **apenas esse arquivo sintético** depois da ingestão produz MODIFIED;
removê-lo produz MISSING; criar outro produz UNTRACKED.

## Limitações

- Sem ZIP recursivo, criptografado ou compressão além de STORE/DEFLATE.
- Limites são por ZIP, sem quota de disco global ou timeout. O teto de 32 MiB dos
  metadados e o limite de entradas não constituem quota total de memória/CPU.
- MIME é application/zip quando identificado; demais formatos ficam ausentes.
- Checagens de links/metadados não substituem isolamento contra processos hostis
  alterando simultaneamente arquivos, paths ou mounts. Originais devem estar estáveis.
- Leituras podem atualizar atime conforme o filesystem. Use mount read-only/noatime
  para preservar metadados do host; o motor não chama operações de alteração desses
  metadados nos originais.
- Filesystem e SQLite não compartilham transação: crash pode deixar run RUNNING e
  staging órfão. Arquivos são sincronizados antes do commit; diretórios também são
  sincronizados no runtime POSIX. Isso não garante atomicidade em falha de energia
  nem durabilidade de diretórios no Windows nativo. Commit de resultado incerto
  preserva staging e exige inspeção manual; não há limpeza de runs anteriores.
- Verify cobre originais; reingestão detecta extrações removidas/alteradas e falha,
  sem restaurá-las. A conferência adiciona uma leitura dos derivados por ingestão.
- case_root no banco é a localização inicial operacional. Paths relativos permitem
  mover as quatro áreas do caso; manifestos não exportam esse path absoluto.
- Alterações não são aceitas como novas versões automaticamente; use aquisição
  separada até existir uma política explícita de revisão.

.gitignore e .dockerignore complementam a revisão de diff/status; não detectam
conteúdo sensível automaticamente nem protegem inclusões forçadas.
As decisões da revisão adversarial estão na [ADR 0010](docs/adr/0010-adversarial-integrity-boundaries.md).

## Roadmap

| Milestone | Escopo |
| --- | --- |
| 0 | Bootstrap e arquitetura — concluído |
| 1 | Evidence Foundation — concluída |
| 2A | Framework + três artefatos Instagram/Meta — esta entrega |
| 2 futura | Ampliação de formatos, Google Takeout e Apple |
| 3 | Normalização de events, devices, networks e messages |
| 4 | Search e timeline |
| 5 | Media hashing: SHA-256 e perceptual hashing |
| 6 | Correlation engine |
| 7 | WhatsApp |
| 8 | Reports e dossier exports |
