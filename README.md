# digital-evidence-engine

Motor técnico local para organização, preservação, catalogação, indexação,
normalização, correlação, pesquisa, timeline e rastreabilidade de evidências digitais.

**Não é software pericial certificado.** Não certifica autenticidade, autoria ou
admissibilidade de evidências. Um hash identifica conteúdo; não comprova essas propriedades.

**Real case evidence must never be committed to this repository.**

## Estado atual

Milestone 0: pacote Python importável, CLI mínima, testes e fundação arquitetural.
Somente `dee --help` e `dee version` estão disponíveis. Não há processamento de
evidências, parsers, schema de banco, ingestão, busca, dashboard ou integrações externas.

## Arquitetura e preservação

O pacote usa `src/evidence_engine`: `cli` expõe comandos; `ingest` receberá fontes;
`models` definirá contratos; `storage` persistirá registros; `correlation`, `search`,
`media` e `reports` terão responsabilidades separadas. Nesta etapa, esses últimos
pacotes apenas reservam os limites de responsabilidade.

- Originais são imutáveis e acessados somente para leitura em `/case/originals`.
- `/case/working`, `/case/database` e `/case/output` recebem derivados e resultados.
- Todos os diretórios de caso devem ficar fora deste repositório.
- Registros futuros preservarão a cadeia até a origem e o SHA-256 do original.
- Deduplicação conservará todas as fontes; observação e interpretação serão separadas.
- UTC será canônico para correlação, preservando timestamp e timezone originais.
  Informação ausente ou ambígua permanece explícita.
- O motor opera localmente, sem telemetria, upload, APIs externas ou cloud storage.

Detalhes em [architecture.md](docs/architecture.md),
[evidence-model.md](docs/evidence-model.md) e [ADRs](docs/adr/).

Stack planejada: Python 3.12+, SQLite/SQLAlchemy 2.x, Pydantic 2.x, Typer,
python-dateutil e `zoneinfo`. Somente Typer é dependência de execução nesta milestone.
SQLAlchemy, Pydantic e python-dateutil entram quando persistência, contratos e
normalização forem implementados. Pillow, imagehash, BeautifulSoup/lxml ficam para
as etapas de mídia e parsing. Nenhuma dependência sem uso é instalada antecipadamente.

## Instalação local

Requer Python 3.12+; no Windows 11, use o terminal PowerShell do VS Code:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\dee.exe --help
.\.venv\Scripts\dee.exe version
```

Selecione `.venv/Scripts/python.exe` como interpretador no VS Code. Usar os caminhos
completos dispensa mudar a política de execução do PowerShell. No Linux/macOS:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
dee --help
dee version
```

Também é possível executar `python -m evidence_engine --help` no ambiente instalado.
Instalação e build podem baixar ferramentas; a execução da CLI não usa rede.

## Docker Desktop

Use containers Linux. Para testar somente o bootstrap, nenhum caso é necessário:

```powershell
docker build -t digital-evidence-engine:dev .
docker run --rm --network none digital-evidence-engine:dev dee --help
docker run --rm --network none digital-evidence-engine:dev dee version
```

Para desenvolvimento com Compose, copie `.env.example` para `.env` e substitua os
quatro caminhos por diretórios vazios de desenvolvimento **existentes e externos ao
repositório**, usando caminhos absolutos com `/` no Windows. Não use evidências reais
para validar esta milestone. Os quatro diretórios devem ser distintos e não sobrepostos:
nenhum volume gravável pode apontar para originais ou para um ancestral deles.

```powershell
Copy-Item .env.example .env
# Edite .env e prepare os quatro diretórios externos antes de prosseguir.
docker compose config --quiet
docker compose build
docker compose run --rm dee dee --help
docker compose run --rm dee dee version
docker compose run --rm dee python -m pytest -p no:cacheprovider
docker compose run --rm dee ruff check --no-cache .
docker compose run --rm dee mypy --cache-dir=/tmp/dee-mypy src
```

O container executa como `dee`, sem rede, com o código e `/case/originals` montados
somente para leitura. Os demais volumes de caso são graváveis. Caminhos ausentes
geram erro em vez de criar diretórios silenciosamente. No Linux, ajuste `DEE_UID` e
`DEE_GID` ao usuário local; garanta permissões nos diretórios graváveis. Nunca altere
permissões dos originais para contornar erros. Alterações de dependências ou metadata
do pacote exigem novo build; mudanças em `src` são refletidas pelo bind mount.

## Qualidade

Com o ambiente virtual ativado:

```sh
python -m pytest
ruff check .
ruff format --check .
mypy src
```

No PowerShell sem ativação, use `.\.venv\Scripts\python.exe -m pytest`,
`.\.venv\Scripts\ruff.exe check .` e `.\.venv\Scripts\mypy.exe src`.
Testes exercitam import, versão instalada, entry point, CLI, configuração e decisões
essenciais. Fixtures só podem ser inteiramente sintéticos em `tests/fixtures/`.

O `.gitignore` bloqueia diretórios de caso, bancos, arquivos compactados, formatos
comuns de exportação/mídia e segredos; fixtures sintéticos têm exceção explícita.
Isso não identifica conteúdo sensível automaticamente: revise `git diff` e
`git status`, inclusive arquivos não rastreados. Nunca force a inclusão de evidências.
O `.dockerignore` limita o contexto de build a código e metadata necessários.

## Roadmap

| Milestone | Escopo |
| --- | --- |
| 0 | Bootstrap e arquitetura (esta entrega) |
| 1 | Evidence Foundation: manifesto, SHA-256, EvidenceFile, SourceRecord, extração segura e SQLite |
| 2 | Parsers Instagram / Meta, Google Takeout e Apple |
| 3 | Normalização de events, devices, networks e messages |
| 4 | Search e timeline |
| 5 | Media hashing: SHA-256 e perceptual hashing |
| 6 | Correlation engine |
| 7 | WhatsApp |
| 8 | Reports e dossier exports |

Regras de contribuição e de agentes estão em [AGENTS.md](AGENTS.md).
