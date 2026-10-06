# ADR 0041 — Real-Workload PDF Deadline Recovery

Status: Accepted.

Milestone: 8B3-E1R5R2 — Operational Deadline Architecture Amendment, somente
documentação e arquitetura. A revisão humana aceita os budgets de 180 segundos
por fase temporizada e 900 segundos por operação completa. Esta ADR autoriza a
implementação E1R5R3, mas não altera código, não qualifica os novos budgets e não
autoriza nova execução real de E1R5.

## 1. Relação com os contratos anteriores

O [ADR 0038](0038-human-pdf-export-contract.md), o
[ADR 0039](0039-controlled-reportlab-adapter-private-coupling.md) e o
[ADR 0040](0040-pdf-page-limit-recovery.md) permanecem registros históricos
aceitos e inalterados. Em especial, o ADR 0040 continua válido para o limite de
2.048 páginas e para a qualificação E1R4 que o estabeleceu.

Esta ADR complementa esses contratos e substitui **somente**, após implementação
e requalificação, os budgets operacionais de tempo:

```text
PHASE_SECONDS: 120 -> 180
GLOBAL_SECONDS: 600 -> 900
```

Até E1R5R3 implementar a decisão e E1R5R4 concluir sua requalificação, os valores
qualificados em produção continuam sendo 120 e 600 segundos. A aceitação desta
ADR não pode ser tratada como qualificação técnica.

## 2. Evidência vinculante

A decisão vincula-se aos seguintes artefatos externos ao Git:

| Evidência | Bytes | SHA-256 |
| --- | ---: | --- |
| `integrity/8B3-E1R5-real-pdf-retry.json` | 5.478 | `fe6e3db806abb08f6a5749bde9b2c0da7142efa7ad242294f5e3110741e06de5` |
| `integrity/8B3-E1R5R1-resource-limit-diagnostic.json` | 19.001 | `5b8ee5c9c8144f40a41a62d785c72b765ceaaf81129d757809903f86d0757e6f` |

O ADR 0040 vinculado permanece com SHA-256
`df5df40dbef093ca1c475901990a62ccd8be6ae586079215177dceba035c7ea0`.
Os artefatos E1R5 e E1R5R1 não são modificados por esta decisão.

## 3. Causa-raiz aceita

A primeira retentativa E1R5 falhou fechada com
`DOSSIER_PDF_RESOURCE_LIMIT`, sem publicação parcial. A localização E1R5R1
isolou a origem como:

```text
SUPERVISOR_PHASE_TIMEOUT
phase = VALIDATE_DOSSIER
```

A sequência observada foi:

- entrada em `VALIDATE_DOSSIER`: 84,253886 s;
- deadline da fase: 204,253886 s;
- check de timeout do supervisor: 204,254657 s;
- deadline global: 600,000105 s;
- evento `FAIL` do worker: ausente;
- erro seguro do worker: ausente;
- término do worker pelo supervisor: `SIGKILL`, sinal 9.

O worker não comunicou outro `RESOURCE_LIMIT`. Scratch permaneceu em zero, os
canais IPC permaneceram abaixo de seus limites e a renderização do dossiê havia
terminado normalmente. O timeout de fase, e não memória, páginas, bytes, objetos,
profundidade, scratch, IPC ou deadline global, causou a falha.

## 4. Medição aceita da carga real

A medição direcionada E1R5R1 foi classificada como
`DIAGNOSTIC ONLY — NOT PRODUCTION QUALIFICATION`. Ela usou o mesmo ambiente,
fontes, algoritmos e limites não temporais qualificados, sem publicação e sem
gravar o PDF como saída operacional.

O dossiê canônico medido apresentou:

| Métrica | Valor |
| --- | ---: |
| Markdown fonte | 3.114.373 bytes |
| Páginas | 1.511 |
| PDF | 11.171.628 bytes |
| Objetos | 3.064 |
| RSS máximo | 243.040.256 bytes |
| Pico do cgroup | 237.760.512 bytes |

O PDF diagnóstico teve SHA-256
`8a3d4ba186be64260e5975bb0234cab924ac59512eff2703ec70016772409bf4`.

Os tempos medidos foram:

| Etapa | Tempo |
| --- | ---: |
| `RENDER_DOSSIER` | 19,265119 s |
| `VALIDATE_DOSSIER` | 121,697776 s |
| Verificação do ambiente | 0,648123 s |
| Parse de Markdown | 5,211194 s |
| Registro de fontes | 0,064245 s |
| Primeiro layout | 4,635128 s |
| Segundo layout | 4,779336 s |
| Pintura do PDF | 3,843313 s |
| Validação independente medida internamente | 121,697814 s |

A carga permaneceu confortavelmente abaixo de todos os limites não temporais.

## 5. Decisão

Ficam aceitos para implementação os seguintes budgets:

```text
OLD: PHASE_SECONDS = 120
NEW: PHASE_SECONDS = 180

OLD: GLOBAL_SECONDS = 600
NEW: GLOBAL_SECONDS = 900
```

Ambos continuam finitos, rígidos e fail-closed. O deadline de fase continua
aplicável somente a `RENDER_CONSOLIDATED`, `VALIDATE_CONSOLIDATED`,
`RENDER_DOSSIER` e `VALIDATE_DOSSIER`, inclusive quando as validações ocorrem
aninhadas em `BIND` e `VERIFY_STAGING`. Um deadline de fase nunca pode ampliar
ou renovar o deadline global absoluto.

Esta decisão altera somente budgets operacionais de tempo. Não altera conteúdo,
schema, perfil, renderer, validador, bindings, formato de saída, algoritmo de
publicação ou qualquer outro limite de recursos.

## 6. Justificativa para 180 segundos por fase

A demanda real observada de `VALIDATE_DOSSIER` foi 121,697776 segundos. O menor
valor inteiro que permitiria essa amostra única é 122 segundos. Esse valor é
tecnicamente suficiente para a medição observada, mas deixa somente 0,302224
segundo de margem e não constitui um envelope operacional determinístico
adequado a variações normais de execução no ambiente qualificado.

O valor escolhido, 180 segundos, acrescenta 58,302224 segundos de margem sobre
a medição, aproximadamente 47,91%. Ele permanece limitado e conserva recusa
automática de uma fase que ultrapasse o budget. Não há autorização para retry
ilimitado, deadline adaptativo ou extensão baseada no conteúdo.

## 7. Justificativa para 900 segundos globais

O contrato anterior mantinha a relação:

```text
600 / 120 = 5
```

Preservar essa mesma relação após a alteração de fase produz:

```text
180 * 5 = 900
```

Portanto, 900 segundos é uma extensão finita e derivada da relação operacional
já aceita, e não a remoção arbitrária do watchdog.

Cada PDF é validado independentemente três vezes: após a renderização inicial,
durante `BIND` e durante `VERIFY_STAGING`. A projeção inferior conhecida é:

```text
84.253886
+ 121.697776
+ 2 * (40.247372 + 121.697776)
= 529.841958 seconds
```

O budget de 900 segundos deixa 370,158042 segundos de margem, aproximadamente
69,86% da projeção conhecida, para o restante de `BIND`, staging, rechecks e
publicação. Isso não demonstra que a operação real termina abaixo de 900 segundos;
essa propriedade deve ser requalificada de ponta a ponta em E1R5R4.

## 8. Limites e arquitetura preservados

Permanecem exatamente inalterados:

| Recurso ou propriedade | Contrato preservado |
| --- | --- |
| Páginas | no máximo 2.048 por PDF |
| PDF individual | no máximo 64 MiB |
| Dois PDFs combinados | no máximo 128 MiB |
| Saída total | no máximo 130 MiB |
| Objetos PDF | no máximo 1.000.000 por PDF |
| Profundidade do grafo | no máximo 64 |
| Espaço de endereçamento do worker | 1 GiB |
| Memória do container | 2 GiB, sem swap adicional |
| Scratch | 256 MiB |
| Processos e CPU | 64 PIDs e 2 CPUs |
| Canais stdout/stderr/eventos/ACK | 64 KiB por canal, conforme o contrato existente |
| Publicação | exatamente quatro arquivos, Linux no-replace |
| Fonte | montagem somente leitura e rechecks existentes |
| Renderização | determinística no ambiente Linux/amd64 qualificado |
| Schemas e perfil | inalterados |

As três validações independentes por PDF permanecem obrigatórias. Esta ADR não
autoriza removê-las, combiná-las ou ignorá-las. Não autoriza otimização do
renderer ou do validador, mudança de algoritmo, truncamento, seleção de findings,
fallback ou saída parcial.

## 9. Interpretação da E1R4

A E1R4 permanece válida para o que estabeleceu: fronteira de 2.048 páginas,
identidade do ambiente, determinismo sintético, envelopes sintéticos de recursos
e enforcement fail-closed.

E1R5 e E1R5R1 demonstraram posteriormente que a fixture sintética de grande
número de páginas não representava a complexidade de CPU/tempo da validação do
dossiê canônico real. A classificação correta é:

```text
REAL-WORKLOAD RESOURCE ENVELOPE GAP
```

Isso não torna a E1R4 falsa, inválida, corrompida ou executada incorretamente. A
dimensão temporal requer nova qualificação depois da implementação desta ADR.

## 10. Alternativas rejeitadas ou adiadas

**`PHASE_SECONDS = 122`: rejeitada.** Embora cubra a única medição, deixa margem
operacional insuficiente para um envelope determinístico qualificado.

**`PHASE_SECONDS = 180` e `GLOBAL_SECONDS = 600`: rejeitada.** A projeção inferior
já consome 529,841958 segundos antes do overhead restante, deixando somente
70,158042 segundos e expondo o fluxo a outra correção sequencial de budget.

**Remover validação duplicada: adiada.** Alteraria materialmente a arquitetura de
confiança e integridade e excede o menor recovery necessário.

**Otimizar o validador agora: adiada.** Pode ser desejável futuramente, mas não é
necessária para restaurar o workflow real dentro de limites finitos.

**Desabilitar deadlines: rejeitada.** Execução limitada e fail-closed é obrigatória.

**Elevar memória, páginas, bytes, objetos, profundidade ou scratch: rejeitada.**
E1R5R1 não identificou esses limites como causa.

## 11. Implementação autorizada: E1R5R3

E1R5R3 deve implementar a menor alteração de produção possível em
`src/evidence_engine/dossier/pdf_service.py`:

```python
PHASE_SECONDS = 180
GLOBAL_SECONDS = 900
```

Nenhuma alteração de produção adicional deve ser feita salvo se a inspeção
demonstrar outra fonte compartilhada indispensável ao mesmo contrato. Os testes
sintéticos devem provar no mínimo:

- aceitação dentro da fronteira exata de 180 segundos;
- timeout acima da fronteira de fase;
- aceitação dentro da fronteira global de 900 segundos;
- timeout acima da fronteira global;
- uso da mesma política de 180 segundos pelas validações aninhadas;
- impossibilidade de uma fase ampliar o deadline global absoluto de 900 segundos;
- impossibilidade de eventos repetidos ou atrasados renovarem deadlines;
- preservação de cleanup, ausência de publicação parcial e falha fechada.

Testes existentes com thresholds reduzidos por monkeypatch podem continuar úteis,
mas testes dos valores de produção devem estabelecer explicitamente 180 e 900.
E1R5R3 não autoriza PDF real nem retentativa E1R5.

## 12. Requalificação obrigatória: E1R5R4

Depois da implementação revisada e congelada, E1R5R4 deve executar no mínimo:

- regeneração do inventário do ambiente de renderização;
- novo `render_environment_id` e nova imagem candidata Linux/amd64;
- Ruff, verificação de formato e mypy;
- testes das fronteiras temporais;
- suite PDF completa;
- regressão completa do repositório;
- publicação sintética determinística G1 A/B;
- qualificação temporal da carga real sem aceitá-la como publicação E1R5;
- diagnóstico real supervisionado de ponta a ponta que prove duração inferior a
  900 segundos;
- confirmação de todos os demais limites de recursos;
- revisão humana do resultado.

Uma alteração das constantes de produção muda o inventário. A qualificação não
pode reutilizar silenciosamente o `render_environment_id` anterior.

## 13. Gate para nova retentativa E1R5

A retentativa canônica E1R5 permanece bloqueada. Ela somente pode recomeçar após:

1. esta arquitetura aceita;
2. implementação E1R5R3 revisada;
3. implementação congelada;
4. inventário regenerado;
5. nova imagem qualificada;
6. requalificação temporal E1R5R4 aprovada por revisão humana.

Somente então poderão ocorrer novamente as duas publicações reais determinísticas.
Nenhuma saída diagnóstica desta série pode ser promovida a publicação canônica.

## 14. Privacidade, preservação e consequência

Esta ADR registra somente métricas operacionais e hashes necessários à decisão.
Não contém mensagens privadas, payloads brutos, caminhos absolutos de host ou
identificadores pessoais. Nenhum artefato real, fonte, PDF, relatório, evidência
E1R5/E1R5R1 ou metadata de origem é incorporado ou modificado.

A consequência aceita é autorizar exclusivamente E1R5R3 a implementar os budgets
de 180 e 900 segundos. Requalificação, PDF real, publicação canônica, commit e
push permanecem etapas separadas e não são autorizados por esta execução.
