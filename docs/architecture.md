# Arquitetura

## Escopo entregue

Milestone 0 estabelece distribuição Python com layout `src`, CLI Typer, testes e
documentação de contratos futuros. Não há acesso a evidências, conexão com banco,
parsers ou lógica de correlação. Importar o pacote e consultar a versão não gera
arquivos nem acessa rede. Não se trata de software pericial certificado.

## Limites dos módulos

| Módulo | Responsabilidade futura |
| --- | --- |
| `cli` | Comandos locais e apresentação; sem lógica de domínio |
| `ingest/generic` | Manifestos, SHA-256 e extração segura |
| `ingest/{instagram,google,apple,whatsapp}` | Adaptadores de formatos e registros de origem |
| `models` | Contratos de domínio, proveniência e validação explícita |
| `storage` | Persistência SQLite via SQLAlchemy 2.x, transações e migrations |
| `correlation` | Relações explicáveis, critérios e suporte documental |
| `search` | Consultas e timeline sobre dados normalizados |
| `media` | Metadados e hashes exatos/perceptuais com semânticas distintas |
| `reports` | Exportação local com referências às fontes e métodos |

Fluxo planejado: originais → manifesto/extratos → registros de origem →
normalização → persistência → pesquisa, correlação e relatórios. Os adaptadores
dependem dos contratos de domínio, nunca o inverso; a CLI coordena os serviços.
Não serão criadas interfaces genéricas antes de existirem consumidores concretos.

## Áreas de um caso

| Caminho conceitual | Acesso | Conteúdo |
| --- | --- | --- |
| `/case/originals` | Somente leitura | Arquivos e containers recebidos |
| `/case/working` | Leitura/escrita | Extrações e derivados reproduzíveis |
| `/case/database` | Leitura/escrita | SQLite, índices e migrations |
| `/case/output` | Leitura/escrita | Relatórios e exportações locais |

Diretórios ficam fora do Git. Volumes devem ser distintos e não sobrepostos, sem
aliases ou links que exponham originais através de um caminho gravável. Compose
impõe leitura apenas no mount de originais; na execução nativa, permissões e
checagens de caminhos ainda serão implementadas na Evidence Foundation.
Os comandos atuais não abrem nenhum desses diretórios.

Extrair nunca será uma operação sobre o container original. A Milestone 1 deverá
rejeitar traversal, caminhos absolutos e links perigosos, limitar expansão/tamanho
e registrar falhas. Nomes, paths e dados ausentes não serão corrigidos silenciosamente.
Não haverá alteração de conteúdo, timestamps ou permissões dos originais pelo motor.

## Persistência e contratos

SQLite é a escolha local, acessada futuramente por SQLAlchemy 2.x. Pydantic 2.x
validará entradas/saídas de contratos sem substituir as restrições do banco.
Não há tabelas ou migrations nesta entrega; o primeiro schema terá baseline
versionada, chaves estrangeiras habilitadas e transações explícitas. Mudanças
posteriores exigem migration, justificativa e testes de atualização.

O modelo conceitual está em [evidence-model.md](evidence-model.md). SHA-256 identifica
conteúdo, enquanto IDs de ocorrência preservam cada aquisição/exportação. Um evento
lógico pode apontar para múltiplos registros de origem; nenhuma consolidação elimina
suporte, valores divergentes ou histórico de transformação.

## Tempo e interpretação

UTC será canônico para correlação apenas quando houver informação suficiente para
conversão. Preservaremos texto original, timezone/offset declarado, UTC e horário
local derivado com a zona escolhida. Valores ausentes, ambíguos e inválidos terão
estado explícito. `zoneinfo` fará conversões IANA; python-dateutil será introduzido
quando necessário para parsing. Em plataformas sem base IANA, como instalações
Windows, será avaliado `tzdata` na milestone temporal, sem dependência prematura.

OBSERVED, DERIVED, REPORTED e HYPOTHESIS distinguem a natureza de cada afirmação.
Derivações terão regra, versão e entradas; relatos terão atribuição; hipóteses
manterão suporte e incerteza. Isso não é uma escala automática de veracidade.

## Dependências e execução

Typer é a única dependência de execução usada agora. pytest, Ruff e mypy são
dependências de desenvolvimento. A stack de persistência/validação/tempo e
Pillow, imagehash, BeautifulSoup/lxml serão adicionadas quando houver uso concreto.
Versões possuem limites principais; não há lockfile nesta fundação, portanto builds
sucessivos podem resolver versões diferentes dentro desses intervalos. Avaliar um
lockfile antes de pipelines reprodutíveis de processamento.

O Dockerfile é de desenvolvimento, instala o pacote editável e executa como
usuário não-root. O Compose monta código somente para leitura e desativa a rede
em execução. Downloads no build servem apenas à instalação de ferramentas. Não
há upload de evidências, telemetria ou integrações externas no aplicativo.

## Verificação

Testes usam somente dados sintéticos e diretórios temporários. Exercitam metadata,
CLI instalada, ausência dos comandos futuros e configuração essencial. O contexto
Docker e os arquivos candidatos ao Git devem ser revisados antes de qualquer commit.
As seis decisões centrais estão registradas em [adr/](adr/).
