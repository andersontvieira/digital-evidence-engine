# ADR 0039 — Controlled ReportLab Adapter Private Coupling

Status: Accepted.

Milestone: 8B2-A.1.1 — Controlled ReportLab Adapter Contract, documentation only.
Base da criação da proposta: 38af18a, branch feat/pdf-toolchain-foundation, árvore limpa.
Contrato pai: [ADR 0038 — Human PDF Export Contract](0038-human-pdf-export-contract.md),
Accepted e inalterado. Slice pai 8B2-A permanece INCOMPLETE. A revisão sintética
8B2-A.1 concluiu: **FEASIBLE ONLY WITH PRIVATE COUPLING — HUMAN ARCHITECTURAL
APPROVAL REQUIRED**. A proposta original não autorizou implementação antes da aceitação.

Revisão arquitetural humana concluída; ADR 0039 Accepted. O acoplamento privado
estreito identificado é risco de manutenção explicitamente aceito para 8B2-A.
A aceitação autoriza somente a superfície enumerada neste ADR; não conclui 8B2-A,
não inicia 8B2-B nem autoriza execução real. Expansão da superfície privada ou
mudança de versão ReportLab exige nova revisão arquitetural e requalificação.
Esta promoção é somente documental, sem retomada da implementação 8B2-A.

## 1. Contexto e problema

O ADR 0038 exige ausência efetiva de Author, Keywords, CreationDate, ModDate e
trailer ID. Na qualificação da API pública do ReportLab 5.0.1, os cinco campos
continuaram presentes. Valores vazios ou determinísticos não satisfazem ausência.
Não é permitido reparar a saída com pypdf ou escolher outro renderer como fallback.

A pergunta deste ADR é sob quais restrições o projeto poderá depender de uma
pequena superfície privada/não documentada dessa release para cumprir o contrato
aceito. Não se redesenha o PDF nem se amplia o escopo da apresentação. Os ADRs
[0036](0036-final-legal-technical-dossier-export-contract.md) e
[0037](0037-deterministic-dossier-assembly.md) também permanecem inalterados.

## 2. Evidência anterior: qualificação da API pública

Os resultados desta seção e das seções 3–4 são evidência sintética anteriormente
estabelecida, não execuções realizadas por esta tarefa documental.

| Ambiente da investigação | Valor |
| --- | --- |
| Python | 3.12.14 |
| ReportLab | 5.0.1 |
| pypdf | 6.19.0 |
| Plataforma | Linux/x86_64 |

Mesmo com `invariant=1`, Author e Keywords vazios e formatter de data vazio, o
probe público emitiu `/Author`, `/Keywords`, `/CreationDate`, `/ModDate` e trailer
`/ID`. Portanto falhou no requisito do ADR 0038. Inspeção da fonte instalada
identificou os seguintes comportamentos específicos do ReportLab 5.0.1:

| Implementação | Comportamento observado |
| --- | --- |
| PDFInfo.format | Emite incondicionalmente Author, Keywords, CreationDate e ModDate. |
| PDFDocument.ID | Retorna ID existente ou gera ID a partir da assinatura interna do documento. |
| PDFDocument.format | Constrói PDFTrailer passando `ID=self.ID()`. |
| PDFTrailer.__init__ | Inclui ID somente quando o valor fornecido não é None. |
| Canvas.__init__ | Constrói diretamente `pdfdoc.PDFDocument(...)`; não foi identificado hook documentado de injeção de document factory. |

## 3. Evidência anterior: protótipo controlado

O protótipo sintético 8B2-A.1 usou três elementos conceituais:

- `ContractInfo(PDFInfo)`: formatter curto que constrói diretamente a allowlist
  Title/Subject/Creator/Producer. Não copia PDFInfo.format para remover linhas.
- `ContractDocument(PDFDocument)`: inicialização herdada, instalação de
  ContractInfo em `info` e override de `ID()` que retorna None. Sem override de
  PDFDocument.format, alteração de PDFTrailer ou mutação de `_ID`/signature.
- Subclasse controlada de Canvas: descriptor intercepta a primeira atribuição a
  `_doc` dentro do Canvas.__init__ original. Descarta o documento padrão recém-criado
  antes de uso dependente pelo Canvas, instala ContractDocument e deixa o restante
  da inicialização original continuar. Rejeita atribuição inesperada/repetida.

Não houve substituição tardia após `super().__init__()`, migração de estado, cópia
de Canvas.__init__ ou PDFDocument.format, monkeypatch global/MethodType, patch do
vendor, reescrita pypdf, pós-processamento, substituição binária ou regex no PDF.

O protótipo emitiu diretamente duas páginas sintéticas com PDF 1.4 e Lang pt-BR.
Info continha exatamente Title, Subject, Creator e Producer; Author, Keywords,
CreationDate, ModDate e trailer ID estavam ausentes. A inspeção limitada também
observou ausência de XMP/Metadata, Encrypt, JavaScript, OpenAction, URI e embedded
files. Leitura pypdf estrita, extração de texto das duas páginas e verificações
de Root, Info, xref, startxref e EOF usadas pelo probe passaram.

Isso demonstra somente viabilidade do subconjunto metadata/trailer inspecionado.
Não constitui validação completa do perfil PDF. Fontes DejaVu, ToUnicode/subsets,
PDFium e os demais gates completos de 8B2-A não foram qualificados pelo protótipo.

## 4. Evidência anterior: determinismo mínimo e limites

Dez processos Linux independentes renderizaram o mesmo protótipo controlado.
Cada saída teve 1732 bytes e o mesmo SHA-256:

```text
34a2b8d27b57af2b654fdea7c4034308ad078c4c46aaa9191338a652b1f5cd25
```

Esse é exclusivamente o hash do PDF do protótipo sintético, não hash de evidência,
caso, pacote de entrega ou distribuição ReportLab. Testes sequenciais A/B/A com
títulos sintéticos em um processo não mostraram vazamento de metadata/texto;
retornar à entrada original reproduziu os bytes originais.

O resultado sustenta a possibilidade de determinismo desse adaptador mínimo.
Não prova o determinismo completo do ADR 0038: fontes, dependências finais,
renderer final, inventário e perfil documental sintético completo continuam
pendentes de qualificação em 8B2-A e dos gates posteriores de fechamento.

## 5. Decisão aceita e condição de autorização

Com este ADR Accepted após revisão humana, o projeto PODERÁ
usar um adaptador controlado do ReportLab **5.0.1**, fixado por versão e artefato,
dependente somente da superfície enumerada na seção 6 e sujeito a todas as
restrições deste contrato. Enquanto esteve Proposed, não autorizou implementação.

A exceção deliberada se justifica porque a API pública não satisfez as ausências
aceitas, a superfície demonstrada é pequena, a serialização central não é copiada,
os bytes são emitidos diretamente pelo ReportLab sem pós-processamento e o
acoplamento pode ser fixado, verificado e testado com falha fechada. Isso não
autoriza uso arbitrário de internals nem aceita automaticamente a dependência
para todos os demais requisitos de 8B2-A.

## 6. Superfície privada exata permitida após aceitação

| Superfície privada enumerada | Único uso/dependência permitido |
| --- | --- |
| reportlab.pdfgen.canvas.Canvas._doc | Interceptar somente a primeira atribuição dentro de Canvas.__init__ para fornecer o documento contratual, conforme seção 7. |
| reportlab.pdfbase.pdfdoc.PDFDocument.info | Instalar ContractInfo durante a inicialização de ContractDocument. |
| reportlab.pdfbase.pdfdoc.PDFInfo | Classe base do formatter da allowlist fechada de metadata. |
| reportlab.pdfbase.pdfdoc.PDFDocument | Classe base do documento contratual, preservando a implementação herdada. |
| reportlab.pdfbase.pdfdoc.PDFDocument.ID | Override estreito que retorna None. |
| reportlab.pdfbase.pdfdoc.PDFDictionary | Construir o dicionário Info exato da allowlist. |
| reportlab.pdfbase.pdfdoc.PDFString | Codificar somente as strings de metadata permitidas. |
| reportlab.pdfbase.pdfdoc.PDFTrailer.__init__ — comportamento | Depender da omissão de ID quando seu valor é None; não sobrescrever ou alterar essa implementação. |

Canvas._doc é atributo privado; PDFDocument.info é campo interno. As classes
PDFInfo, PDFDocument, PDFDictionary, PDFString e PDFTrailer são acessíveis em
Python, mas não são aceitas aqui como API de extensão pública, documentada e
estável. O override de ID e a omissão por `is not None` dependem de comportamento
interno revisado. Não descrevê-los como hooks públicos suportados.

Métodos herdados podem operar normalmente; isso não autoriza acoplamento privado
adicional. Se a implementação precisar de outro símbolo privado/não documentado,
deve PARAR e solicitar revisão arquitetural humana antes de ampliar a allowlist.
Guardas de tipo/shape também não podem introduzir dependências privadas extras
silenciosamente; a inspeção de fonte durante qualificação não as autoriza.

## 7. Contrato de ciclo de vida do Canvas

A subclasse controlada deve executar o Canvas.__init__ original. O único ponto
de interceptação autorizado é sua primeira atribuição a `_doc`, sincronamente:

1. Permitir que Canvas.__init__ crie seu PDFDocument padrão.
2. Interceptar a atribuição antes de o Canvas prosseguir usando esse documento.
3. Verificar o tipo exato e a forma esperada do objeto atribuído.
4. Descartar imediatamente o documento padrão recém-criado, sem migrar estado.
5. Instalar ContractDocument e deixar a inicialização original continuar.
6. Rejeitar qualquer atribuição inesperada, segunda ou repetida de documento.

É proibido substituir `_doc` depois de retornar de `super().__init__()`, reconstruir
o estado do Canvas ou migrar estado de um documento padrão já utilizado. Não copiar
Canvas.__init__ nem duplicar inicialização de fontes, compressão, criptografia
ou preâmbulo. A revisão observou que etapas posteriores dessa inicialização
dependem do documento nesses pontos; substituição tardia pode perder referências
e estado. Sucesso com página vazia não prova segurança dessa substituição.

## 8. Perfil fixo de produto

O adaptador serve exclusivamente ao perfil de apresentação do ADR 0038. Seus
parâmetros iniciais são explícitos: `invariant=1`, `pdfVersion=(1, 4)`,
`lang="pt-BR"` e `encrypt=None`. Outra configuração só pode ser introduzida se
já contratada pelo ADR 0038 e explicitamente qualificada.

Não se promete compatibilidade com todas as opções do construtor Canvas. Não se
cria Canvas alternativo genérico, wrapper para releases arbitrárias, framework
de renderers, sistema de plugins, interface genérica hipotética ou fallback.

## 9. Contrato de ContractInfo

O formatter deve ser curto e derivado diretamente da allowlist contratual,
construindo PDFDictionary/PDFString, sem copiar PDFInfo.format e apagar campos.
Emitir exatamente estas quatro chaves Info, com os valores do ADR 0038:

| Chave | Valor obrigatório |
| --- | --- |
| Title | H1 exato do documento de origem aprovado. |
| Subject | `Apresentação técnica de artefato aprovado; sem nova análise.` |
| Creator | `Digital Evidence Engine dossier.pdf_export/1.0.0` |
| Producer | `Digital Evidence Engine dossier.pdf_export/1.0.0` |

Author, Keywords, CreationDate e ModDate devem estar ausentes, não vazios ou null.
Nenhuma chave extra é permitida. Esses valores e a regra de ausência não mudam.

## 10. Contrato de ContractDocument e trailer ID

ContractDocument herda PDFDocument e sua inicialização. O comportamento específico
limita-se a instalar ContractInfo durante a inicialização e retornar None em
`ID()`. Não sobrescrever PDFDocument.format nem reescrever PDFTrailer. Não
manipular `_ID`, signature, internals de xref, numeração de objetos ou bytes do
trailer. Necessidade de override de PDFDocument.format exige PARAR e revisar
arquitetura fora deste contrato.

A cadeia revisada é: PDFDocument.format passa `ID=self.ID()`; ContractDocument.ID
retorna None; PDFTrailer.__init__ omite o campo quando recebe None. Resultado
exigido: **ausência de `/ID`**. Não aceitar `/ID null`, `/ID []`, `/ID <>`, bytes
vazios, ID falso determinístico, UUID ou ID derivado de hash. Mudança desse
comportamento reprova a qualificação, sem compensação por reescrita do PDF.

## 11. Pin de versão e artefatos de distribuição

Este contrato vale somente para **ReportLab == 5.0.1**. Não implica compatibilidade
com 5.0.2, 5.1, 6.x, releases anteriores ou builds modificados por distribuições.
Sem presumir compatibilidade por versionamento semântico de superfície privada.

A versão nominal é insuficiente. A implementação futura 8B2-A deve fixar e
verificar os artefatos exatos da distribuição utilizados pelo build canônico,
por mecanismo de pacote/lock, com hashes no build/lock/inventário qualificado.
Este ADR não inventa hashes de pacotes nem altera dependências, lock ou build.
Os valores concretos pertencem à qualificação de implementação posterior.

## 12. Guardas de símbolos, forma e comportamento

A qualificação e os testes futuros devem verificar a versão exata, existência
das classes Canvas, PDFDocument, PDFInfo e PDFTrailer e dos demais símbolos da
allowlist, além das assinaturas compatíveis dos construtores/métodos usados.
Devem confirmar que Canvas.__init__ ainda faz a primeira atribuição revisada
antes da inicialização dependente, que PDFDocument.format passa `ID=self.ID()`
a PDFTrailer e que None continua omitindo ID.

Hash/fingerprint de fonte em desenvolvimento pode complementar as verificações.
Não se exige subsistema elaborado de anti-tamper em runtime. O hash do artefato
da dependência canônica, junto à qualificação de forma/comportamento, é a
fronteira principal. Guardas de runtime de versão, tipo/atribuição e receita
qualificada devem recusar divergências; não inferir compatibilidade pelo simples
sucesso de uma página vazia ou da importação do módulo.

## 13. Falha fechada do ambiente

Qualquer invariante revisada que falhe impede uso do adaptador, com a categoria
interna/pública correspondente a **DOSSIER_PDF_ENVIRONMENT_UNSUPPORTED** do
ADR 0038. Exemplos: versão inesperada, classe ausente, tipo errado, atribuição
`_doc` inesperada/repetida, sequência de construção alterada, shape/assinatura
incompatível, comportamento ID/trailer diferente ou divergência de artefato/hash
na verificação do ambiente canônico.

Não adivinhar compatibilidade, fazer recuperação, monkeypatch, trocar renderer,
reescrever PDF ou continuar com validação reduzida. A divergência reprova a
qualificação ou a verificação de ambiente aplicável; não produz sucesso parcial.
Preservar erros sanitizados e a ordem de falhas do ADR 0038.

## 14. Técnicas proibidas e ausência de pós-processamento

São proibidos:

- Monkeypatch global, inclusive `reportlab.pdfgen.canvas.pdfdoc.PDFDocument = ...`
  ou substituição equivalente de módulo/classe; alterações globais temporárias.
- Monkeypatch de instância com MethodType, atribuição de lambda a ID, mutação
  de `__class__`, `_ID` ou signature.
- Edição de site-packages, patch de wheel, fork local ou ReportLab modificado
  incorporado ao projeto.
- Cópia de PDFDocument.format, cópia substancial de Canvas.__init__ e reconstrução
  da inicialização dependente do Canvas.
- Reescrita com pypdf/PdfWriter, repair, patch binário, substituição por regex,
  exclusão de metadata ou de trailer depois de gerar o PDF.

Necessidade futura de qualquer dessas técnicas exige revisão arquitetural, não
exceção local. pypdf permanece validador independente somente leitura. Os bytes
validados, hasheados e posteriormente empacotados devem ser os bytes emitidos
diretamente pelo caminho qualificado do renderer.

## 15. Propriedade da serialização central

ReportLab continua responsável por registro de objetos, xref, PDFDocument.format,
PDFTrailer.format, serialização de páginas/streams e SaveToFile/GetPDFData.
O adaptador não se torna um serializador PDF parcial. Precisar assumir qualquer
dessas responsabilidades exige PARAR e revisar arquitetura. A operação normal
herdada desses métodos não amplia a superfície privada da seção 6.

## 16. Estado global, threads e isolamento

Não há alegação de thread safety geral do ReportLab ou do adaptador. A revisão
observou atividade normal do cache global de fontes do ReportLab. Isso não
autoriza o adaptador a substituir símbolos, alterar rl_config, trocar configuração
global de renderer ou introduzir mutação global temporária.

Preservar o modelo do ADR 0038: um documento/worker por vez, execução isolada e
sequencial no ambiente canônico Linux/amd64, dependências fixas, runtime offline,
sem mounts de caso, worker não root e recursos limitados. Não há garantia nova
de render paralelo nem ampliação de permissões, mounts ou budgets.

## 17. Fronteira futura de módulo e revisão de imports

Preferir um módulo estreito, por exemplo
`src/evidence_engine/dossier/pdf_reportlab_adapter.py`, ou nome equivalente
coerente com o repositório. Responsabilidades exclusivas: construir o documento/
Canvas contratual, impor guardas de versão/shape e expor adaptador tipado estreito
ao futuro renderer. O nome sugerido não obriga criar esse arquivo nesta tarefa.

O módulo não possui parsing Markdown, validação de caso/pacote, semântica final
do dossiê, lógica de findings, política de TOC, publicação, CLI, descoberta de
pacotes fonte, DB, rede, OCR ou interpretação de imagens. Não disseminar imports
privados de ReportLab por módulos alheios. Testes devem enumerar os símbolos
privados utilizados e conferir sua allowlist. A montagem 8B1 não ganha dependência
do adaptador PDF nem imports desses internals.

## 18. Matriz obrigatória de testes futuros inteiramente sintéticos

Estes testes são requisitos para a futura aceitação da implementação 8B2-A,
não testes adicionados/executados nem resultados alegados por este ADR.

| Área | Evidência exigida |
| --- | --- |
| Baseline pública | ReportLab padrão 5.0.1 ainda emite os quatro campos proibidos e ID, demonstrando o motivo do adaptador. |
| Info contratual | Exatamente Title/Subject/Creator/Producer com os valores aceitos; Author/Keywords/CreationDate/ModDate ausentes. |
| Trailer e perfil | ID efetivamente ausente; PDF 1.4 e Catalog Lang pt-BR. |
| Estrutura e texto | Leitura pypdf estrita; Root/Info resolvidos; sanidade de xref/startxref/EOF; extração básica de texto preservada. Não substituir a validação completa do ADR 0038 por strict=True. |
| Determinismo mínimo | Dez ou mais renders independentes byte-idênticos; sequência A/B/A sem vazamento de metadata/texto e com reprodução dos bytes originais. |
| Versão e artefato | Versão inesperada e divergência de artefato/hash recusadas pelo gate canônico com ENVIRONMENT_UNSUPPORTED. |
| Ciclo de vida | Interceptação da primeira atribuição antes do uso dependente; atribuição inesperada/repetida e tipo de documento inesperado falham fechados. |
| Símbolos e shape | Classe ausente, assinatura/sequência alterada ou mudança ID/trailer reprovam guardas com ENVIRONMENT_UNSUPPORTED. |
| Integridade do vendor | Ausência de monkeypatch global e de mutação da fonte instalada. |
| Serialização direta | Sem pypdf writer/rewrite/repair, pós-processamento ou patch de bytes; sem override/cópia de PDFDocument.format ou cópia substancial de Canvas.__init__. |
| Imports e isolamento | Acoplamento enumerável restrito à seção 6 e ao módulo estreito; montagem 8B1 independente de PDF. |

Os nomes abreviados ENVIRONMENT_UNSUPPORTED na matriz correspondem à categoria
completa DOSSIER_PDF_ENVIRONMENT_UNSUPPORTED. Essa matriz complementa todos os
gates aplicáveis do ADR 0038, sem reduzi-los aos casos do protótipo.

## 19. Política de upgrade e requalificação

Qualquer mudança de ReportLab exige checkpoint deliberado: revisão de versão e
artefato exatos novos, licença, forma da fonte, todos os testes deste adaptador,
metadata/trailer, determinismo, texto/fontes exigidos pelo contrato 8B2 ativo e
gates completos de qualificação PDF relevantes naquele momento. Aprovação humana
e requalificação explícitas precedem aceitação da nova release; o pin deste
contrato não se estende automaticamente a ela.

Não aceitar atualização incidental por refresh de lock não relacionado. Expansão
da superfície privada exige revisão arquitetural humana separada da mera troca
de versão. Falha não pode ser acomodada por fallback ou relaxamento dos testes.

## 20. Relação com ADR 0038 e marcos seguintes

ADR 0038 permanece Accepted e inalterado. Este ADR especifica somente o mecanismo
de implementação aceito para satisfazer uma fronteira existente
de metadata/trailer. Não altera pdf-presentation-v1, fronteira dos documentos de
origem, allowlist/ausências, PDF 1.4, fontes, ToUnicode, outlines, TOC, layout,
proibições de segurança, papéis de pypdf/PDFium, ambiente Linux/amd64, determinismo,
budgets, integridade de pacote, CLI, sequência 8B2 ou fronteira real 8B3.

| Marco | Estado e condição de avanço |
| --- | --- |
| 8B2-A | INCOMPLETE. Qualificação pública falhou. 8B2-A.1 demonstrou viabilidade técnica somente com acoplamento privado. ADR 0039 Accepted permite futura retomada sob sua superfície enumerada; esta promoção não retoma implementação/qualificação. |
| 8B2-B | Não iniciado nem autorizado por este ADR. Apesar da aceitação de 0039, depende do fechamento e revisão humana de 8B2-A. |
| 8B3 | Futura etapa de execução real controlada; não acionada nem autorizada pela proposta ou aceitação deste adaptador. |

Após a aceitação de 0039, 8B2-A ainda deve concluir qualificação de
dependências/licenças/fontes, ToUnicode, determinismo de subsets, outlines,
PDFium, receita Docker canônica, inventário de render, fundação de gramática/
modelo fechado, limites de recursos, testes direcionados, regressão 8B1, gates
completos pytest/Ruff/mypy e revisão humana final antes de considerar 8B2-B.

## 21. Consequências, privacidade e limites de alegação

Benefício: geração direta do formato metadata/trailer aceito, sem pós-processamento
e sem assumir a serialização PDF. Custo: dependência deliberada de detalhes não
documentados, com manutenção de pin exato, testes e requalificação a cada upgrade.
O acoplamento privado não demonstra autenticidade probatória nem melhora por si
só a cadeia de custódia. O determinismo limitado observado não encerra os gates
do ambiente final, fontes e perfil completo.

Evidência deste ADR e futuros gates de implementação são inteiramente sintéticos.
Não se autoriza acesso a CASE_ROOT, DB, originals, working, artefatos reais de
qualquer caso, dossiês/relatórios/snapshots reais, mídias reais ou hashes de caso.
8B3 continua sendo a fronteira futura de execução real controlada. Não incluir
dados reais, identificadores de caso ou caminhos absolutos de host neste ADR.

Não apresentar adaptador ou produto como software pericial certificado, renderer
PDF certificado, software forense validado, laudo pericial ou cadeia de custódia
certificada. Não alegar PDF/A, PDF/UA, assinatura digital, certificado ou validação
jurídica. Nenhuma dessas propriedades decorre do protótipo ou desta proposta.

## 22. Validação documental da proposta e da promoção

Na criação original, somente ADR 0039 foi criado como Proposed, sem modificar
AGENTS, README, architecture, ADRs existentes, produto, testes, fixtures, schema,
dependências, lockfiles ou build/Dockerfiles. A tarefa foi documental, sem
implementação, instalação, geração de PDF, acesso real, stage, commit ou push.

Na promoção posterior à revisão humana, ADR 0039 passou a Accepted; AGENTS.md,
README.md e docs/architecture.md foram atualizados somente para registrar a
aceitação e o roadmap atual. Sem alteração de produto, testes, fixtures, schema,
dependências, lockfile, Dockerfile, Compose, fontes ou inventário de render.
Nenhum adaptador foi implementado, dependência instalada ou PDF gerado/validado;
não houve acesso real nem retomada de 8B2-A. Os resultados das seções 2–4 permanecem
evidência sintética histórica, não gates atuais de produto.

Gates documentais: git diff --check, git status --short, git diff --stat e leitura
explícita do ADR novo, pois ainda não rastreado não aparece no diff comum. Revisão
de privacidade deve confirmar ausência de dados/artefatos reais, paths absolutos
de host, hashes de pacotes inventados, alegações de certificação ou de conclusão
8B2-A/início 8B2-B. O único hash registrado é o protótipo sintético identificado
na seção 4. Sem pytest, Ruff ou mypy em ambas as etapas documentais; os gates funcionais
anteriormente aceitos de 8B1-G não são reexecutados nem apresentados como gates PDF.
Sem stage, commit ou push.

## 23. Gate final de aceitação humana

Revisão arquitetural humana concluída: **PASS FOR ACCEPTANCE**; ADR 0039
**Accepted**. O risco de manutenção do acoplamento privado enumerado foi
explicitamente aceito. A criação original da proposta não autorizou implementação
antes desta decisão.

A decisão autoriza somente a superfície exata enumerada. Expandi-la exige nova
revisão arquitetural humana; mudar a versão ReportLab exige revisão e
requalificação. A aceitação não conclui 8B2-A, não inicia 8B2-B e não autoriza
8B3/execução real. Esta promoção documental não implementa o adaptador.
