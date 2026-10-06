# ADR 0040 — PDF Page-Limit Recovery

Status: Accepted.

Milestone: 8B3-E1R2 — PDF Page-Limit Contract Amendment, somente documentação
e arquitetura. A decisão arquitetural desta ADR está aceita; sua implementação
e a requalificação permanecem pendentes. Esta aceitação não altera o código em
produção, não qualifica o novo limite e não autoriza publicação de PDF de caso
real.

## 1. Relação com os contratos anteriores

O [ADR 0038](0038-human-pdf-export-contract.md) permanece como registro histórico
aceito do contrato original de exportação PDF, inclusive da proteção operacional
de 1.000 páginas por PDF que foi qualificada na 8B2. O
[ADR 0039](0039-controlled-reportlab-adapter-private-coupling.md) permanece
inalterado.

Esta ADR complementa e substitui **somente** o orçamento de páginas por PDF do
ADR 0038. Quando a implementação e a requalificação previstas nas seções 7 e 8
forem concluídas, prevalecerá o limite de 2.048 páginas desta ADR. Todas as demais
decisões dos ADRs 0038 e 0039 continuam vigentes.

Neste checkpoint E1R2, o código e o ambiente qualificado continuam limitados a
1.000 páginas. E1R3 deve alterar o código; até E1R4 concluir a requalificação,
o novo limite de 2.048 páginas não constitui qualificação de produção.

## 2. Contexto e diagnóstico aceito

O limite anterior de 1.000 páginas era uma fronteira de proteção operacional
deliberada, por PDF, e não uma invariante do schema do dossiê. Uma carga real
controlada da 8B3 demonstrou um uso legítimo acima dessa fronteira: o relatório
consolidado requer exatamente 1.169 páginas e o dossiê requer exatamente 1.511.
Isso não demonstra defeito na proteção anterior; demonstra que seu envelope não
abrange esta carga legítima.

O diagnóstico 8B3-E1R1 classificou a causa como volume estrutural de conteúdo,
agravado pela projeção do dossiê baseada em tabelas. O conjunto canônico contém
3.904 findings, de `F-001` a `F-3904`, e nenhum finding individual excedeu duas
páginas. O valor histórico de auditoria 999 está obsoleto e não integra esta
decisão.

As medições diagnósticas, sem serialização ou publicação de PDF, foram:

| Documento | Parse | Layout | RSS máximo | Pico tracemalloc |
| --- | ---: | ---: | ---: | ---: |
| Relatório consolidado | 20,37 s | 24,36 s | 182,1 MB | 40,4 MB |
| Dossiê | 33,05 s | 31,81 s | 285,5 MB | 70,8 MB |

Memória e tempo de parse/layout permaneceram dentro dos budgets atuais durante
o diagnóstico. Renderização final, serialização, validação independente, tamanho
dos PDFs e contagem/profundidade de objetos não foram qualificados para esta carga.
Nenhum PDF real foi produzido com base nessas medições.

## 3. Decisão

O orçamento aceito para implementação passa de:

```text
OLD: MAX_PAGES = 1000 per PDF
NEW: MAX_PAGES = 2048 per PDF
```

O limite continua sendo aplicado a cada PDF individualmente e permanece uma
fronteira operacional rígida com falha fechada. A contagem continua incluindo
o TOC:

- a página 2.048 é permitida;
- uma solicitação da página 2.049 é rejeitada antes de sua criação;
- o validador independente rejeita `page_count > 2048`;
- o binding do manifesto rejeita `page_count > 2048`;
- não há truncamento silencioso, renderer alternativo, omissão automática de
  findings ou retry com conteúdo reduzido.

O valor 2.048 cobre o maior documento medido com 537 páginas de margem, cerca de
35,5%. Ele amplia intencionalmente o envelope de recursos e exige requalificação
integral antes do uso em produção.

## 4. Semântica e forma de saída preservadas

A decisão preserva todo o conteúdo canônico, inclusive os 3.904 findings, e não
altera seleção, ordenação ou narrativa. Permanecem inalterados:

- o perfil `pdf-presentation-v1` e o contrato `dossier.pdf_export/1.0.0`;
- exatamente dois PDFs: `human/dossier.pdf` e
  `human/consolidated-report.pdf`;
- os bindings fixos aos dois Markdown capturados do mesmo `directory-v1`;
- a forma de quatro arquivos da saída, o manifesto e `SHA256SUMS.txt`;
- bytes PDF determinísticos no mesmo ambiente contratado;
- PDF 1.4, fontes e política de metadata existentes;
- execução offline, sem rede, recursos externos ou fallback;
- os contratos, schemas e artefatos canônicos das séries C, D1 e D2.

Não se introduzem multi-volume, perfil compacto, seleção de findings ou mudança
na completude do modelo. O mesmo dossiê canônico permanece reutilizável sem
regeneração.

## 5. Demais limites preservados

Somente a contagem máxima de páginas está sob alteração. Continuam exatamente
os demais budgets do ADR 0038:

| Recurso | Limite preservado |
| --- | ---: |
| Fonte completa | 1 GiB e 261 arquivos |
| Cada Markdown fonte / total dos dois | 64 MiB / 128 MiB |
| Cada JSON ou sums administrativo fonte | 64 MiB |
| JSON | profundidade 64, 1.000.000 nós e lexema numérico de 128 caracteres |
| Blocos de apresentação | 200.000 por documento |
| Tabelas | 16 colunas, 100.000 linhas e 1.000.000 células por documento |
| Imagens embutidas / pixels / bytes | zero |
| PDF individual | 64 MiB |
| Soma dos dois PDFs | 128 MiB |
| Objetos PDF | 1.000.000 por PDF |
| Profundidade do grafo PDF | 64 |
| Manifesto / sums novos | 1 MiB cada |
| Saída total | 130 MiB |
| Espaço de endereçamento do worker | 1 GiB |
| Memória do container / swap adicional | 2 GiB / desabilitada |
| Renderização ou validação por fase | 120 s |
| Operação completa | 600 s |
| Scratch | 256 MiB |
| Processos / CPU | pids-limit 64 e 2 CPUs; um worker por vez |
| Captura de stdout / stderr | 64 KiB por stream |

Esta ADR não alega que esses limites já suportam PDFs reais de até 2.048 páginas.
Essa conclusão depende da requalificação da seção 8.

## 6. Alternativas consideradas

**Publicação multi-volume:** tecnicamente viável e potencialmente melhor para
uso humano e particionamento de recursos. Exige novo perfil/versão, conjunto
variável de arquivos, novo contrato de manifesto, regras determinísticas de
divisão e requalificação substancial. Fica adiada, sem rejeição definitiva.

**Apresentação compacta:** conceitualmente viável, mas introduz semântica de
apresentação seletiva e exige novo contrato de produto. Fica adiada.

**Seleção upstream de findings:** incompatível com a semântica D2 do modelo
canônico completo. Não é uma resposta aceitável a um limite operacional de
apresentação.

## 7. Implementação futura 8B3-E1R3

A 8B3-E1R3 deve alterar a constante compartilhada de produção e adicionar testes
inteiramente sintéticos que demonstrem:

- 2.048 páginas aceitas e tentativa da página 2.049 recusada antes da criação;
- a mesma fronteira no validador independente;
- a mesma fronteira no binding do manifesto;
- preservação de falha fechada, sem truncamento, fallback ou saída parcial.

E1R3 não altera perfil, schema, bindings, número de PDFs, fontes canônicas ou
conteúdo real. O novo limite ainda não poderá ser usado para publicação real
após E1R3 isoladamente.

## 8. Requalificação obrigatória 8B3-E1R4

A mudança do budget aceito invalida a qualificação anterior especificamente na
dimensão de fronteira de páginas. Antes de qualquer publicação real, E1R4 deve
requalificar no ambiente canônico Linux/amd64:

- layout grande, serialização e validação independente;
- limite de 64 MiB por PDF e 128 MiB combinados;
- limites de objetos e profundidade do grafo PDF;
- memória de 1 GiB, scratch de 256 MiB e tempos por fase/global;
- duas renderizações A/B byte-idênticas;
- amostragem estrutural e visual por PDFium;
- integridade do pacote, bindings, manifesto e `SHA256SUMS.txt`;
- serviço, staging, publicação sem substituição e fechamento Linux/amd64;
- revisão humana dos resultados exigidos pelo contrato PDF.

Falha em qualquer gate preserva a recusa de publicação. Nenhum PDF real pode ser
considerado qualificado antes do sucesso completo de E1R4.

## 9. Ambiente e `render_environment_id`

A alteração da constante de produção em E1R3 mudará o inventário da implementação.
E1R4 deve gerar e qualificar um novo `render_environment_id` junto com a nova
imagem e o inventário correspondente. Esta etapa documental não altera código,
inventário ou imagem e, portanto, não gera antecipadamente um novo identificador.

## 10. Retentativa real 8B3-E1R5

Somente após E1R3 e E1R4 aprovadas, E1R5 poderá repetir a publicação real controlada
usando o mesmo dossiê canônico, sem regenerar C/D1/D2. A retentativa deve exigir
duas execuções determinísticas, validação independente, binding e evidência
canônicos e preparação para revisão humana final. Continuam proibidos truncamento,
seleção de findings, fallback e mutação das fontes.

## 11. Privacidade, preservação e limites da decisão

Esta decisão usa somente contagens e medições operacionais necessárias para
justificar o envelope. Não registra conteúdo de mensagens privadas, caminhos
absolutos de host, identificadores pessoais ou payloads de evidência. Nenhum
relatório, dossiê, snapshot, reconciliação ou artefato de integridade do operador
é incorporado ou modificado.

Não há alegação de certificação forense, PDF/A, PDF/UA, assinatura, validade
jurídica, completude do caso ou sucesso da publicação real. A decisão arquitetural
está aceita; implementação, requalificação e execução permanecem gates separados.

## 12. Consequência e gate de avanço

O menor ajuste de contrato que preserva conteúdo, bindings, determinismo e forma
de saída é elevar o limite por PDF para 2.048 com requalificação completa. A
implementação E1R3 está autorizada por esta decisão, mas não é realizada por ela.
E1R4 deve concluir antes de E1R5; nenhuma etapa pode transformar medição diagnóstica
em alegação de qualificação.
