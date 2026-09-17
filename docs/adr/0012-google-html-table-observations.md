# 0012 — Observações das duas tabelas HTML Google

## Status

Aceito na Milestone 2C.

## Contexto

SubscriberInfo e ChangeHistory exigem leitura de HTML dentro do framework que
até então decodificava JSON. Precisamos conservar a validação de locators e payload,
sem duplicar transações, inventário, idempotência ou entidades de evidência.

## Decisão

Extrair a coordenação existente para parse_catalog com decoder explícito por fluxo:
strict_json para Instagram e table_document para os dois artefatos Google.
Os comandos selecionam registries fixos; não há autodetecção genérica de plataforma.

Usar html.parser da biblioteca padrão: não há necessidade de BeautifulSoup/lxml
para as tabelas restritas suportadas. Nenhuma dependência ou lockfile muda.
O leitor não executa scripts, consulta links nem resolve entidades externas.
UTF-8/BOM, entidades de caracteres HTML e br são decodificados explicitamente;
o restante do texto das células, inclusive whitespace, fica intacto.
Markup, atributos e representação lexical continuam no original e seu SHA-256.

Projetar tabelas em {tables: [{headers: [...], rows: [{header: texto}]}]}.
Locators $/tables/T/rows/R usam índice da tabela no documento e da linha de dados
(ambos base zero; header excluído de R). Campo usa token escapado ~0/~1.
Reabrir os mesmos bytes, aplicar table_document e resolve_locator reproduz os valores.
A projeção é apenas leitura determinística, não normalização de eventos.

Seleção exige filename exato ou sufixo .SubscriberInfo.html/.ChangeHistory.html
(prefixo de conta opaco), path canônico e headers explícitos. SubscriberInfo requer
os oito headers do contrato; ChangeHistory requer Timestamp, IP Address e Change Type,
com Old Value/New Value opcionais. Colunas adicionais são preservadas com warning.
Todas as tabelas compatíveis são processadas, sem deduplicar linhas ou timestamps.

Recusar tabelas aninhadas, spans, headers ambíguos, linhas irregulares e tabelas
sem fechamento explícito; não reparar HTML malformado para fabricar registros.
Tabelas sem header não selecionam parsers. A projeção ignora conteúdo fora das tabelas.
Parsing é limitado a 32 MiB por fonte, 1000 tabelas, 101000 linhas incluindo headers,
256 células por linha, 64 níveis de markup dentro de células e 100000 observações.

Reutilizar o mesmo savepoint por fonte, verificação de hash, validação de payload
e status FAILED/UNSUPPORTED. Nenhuma mudança de schema ou migração.

## Consequências

HTML fora desses dois contratos permanece fora do escopo. O leitor é deliberadamente
restritivo: HTML válido com tabelas complexas ou fechamentos omitidos pode ser recusado.
Timestamp raw não recebe parsing de datas ou conversão de timezone. IP só recebe
validação sintática; código de modelo só é extraído literalmente de Raw User Agents.
Valores de histórico ficam no banco do caso, nunca na saída da CLI ou logs.
Fixtures são inteiramente sintéticos. Variantes novas exigem teste e revisão explícita.
