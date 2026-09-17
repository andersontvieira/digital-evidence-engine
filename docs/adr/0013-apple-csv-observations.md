# ADR 0013 — Observações CSV Apple com projeção técnica explícita

Status: aceita.

## Contexto

Três artefatos Apple autorizados usam CSV, com identificadores textuais, células
multilinha e campos comerciais fora do escopo investigativo aprovado. A Foundation
e o serviço de parsing já preservam hashes, locators e atomicidade por fonte.

## Decisão

Adicionar `csv_document` à camada de parsing, usando somente csv da biblioteca
padrão. A projeção determinística é `{headers: [...], rows: [{header: texto}]}`.
Não remover whitespace, converter valores, preencher ausências ou normalizar horários.
Locators `$/rows/N` usam índice lógico base zero; campos usam escaping JSON Pointer.
Limitar tamanho, linhas e colunas; rejeitar headers duplicados/vazios, NUL, largura
incompatível e erros de UTF-8/leitura estrita, sem recuperar registros parciais.

Registrar somente `apple.device_inventory`, `apple.sign_on_activity` e
`apple.media_device_activity`, versão 1.0.0, selecionados por path literal e headers.
A variante explícita de diretório de mídia com/sem `Apple Media Services/` é aceita;
não há busca por sufixo ou filename genérico. Inventário exige Device Name, Device
IMEI, Device Serial Number, Device Model Name e ambos os campos Last Heartbeat.
Sign-on exige todos os sete headers; mídia exige os sete headers técnicos mínimos.

Payloads são subconjuntos fiéis do registro CSV: 18 campos de inventário, sete de
sign-on e 12 técnicos de mídia. Campos extras continuam somente na fonte original.
`timestamp_raw` usa respectivamente Last Heartbeat Timestamp, Logged In Date e
Event Time, com annotation de papel e locator; demais timestamps ficam raw no payload.
IP sintaticamente inválido permanece observado com warning. Ausência e o marcador
`Not Available` não são equivalentes no payload e não recebem preenchimento.

Reutilizar `parse_catalog` com decoder explícito, mantendo conferência SHA-256,
rollback por fonte, ParserRun auditável e identidade fonte/parser/versão/locator.
Não alterar schema, dependências, parsers Instagram/Google ou converter observações
em entidades normalizadas. Não correlacionar identificadores nem inferir fatos.

## Consequências

Linhas iguais são ocorrências distintas. Projeção técnica reduz dados no payload,
mas a cadeia até o ZIP original e seu hash conserva acesso às colunas excluídas.
Variantes de path/schema fora desses contratos são ignoradas ou UNSUPPORTED.
O limite de campo padrão de csv no runtime validado é 128 KiB. Validação sintática
não atribui autoria, dispositivo comercial, localização, sucesso de login ou UTC.
O snapshot não permite concluir ausência histórica de dispositivos.
