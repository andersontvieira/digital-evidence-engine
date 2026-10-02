# Regras do repositório

- Nunca adicionar evidência real ao Git, inclusive em fixtures, logs e exemplos.
  Real case evidence must never be committed to this repository.
- Nunca modificar arquivos originais, seus metadados ou suas permissões. Originais
  devem ser acessados somente para leitura; derivados ficam em diretórios separados.
- Não inventar dados ausentes nem substituir ausência por inferência silenciosa.
- Preservar proveniência até o arquivo/container original e seu SHA-256.
  Deduplicação deve conservar todas as fontes e ocorrências.
- Distinguir explicitamente OBSERVED, DERIVED, REPORTED e HYPOTHESIS.
  Uma hipótese não pode ser promovida a fato sem novo suporte documentado.
- Preservar timestamp e timezone originais. UTC é canônico apenas quando a
  conversão é sustentada por informação suficiente; ambiguidades são explícitas.
- Todo parser deve possuir testes com fixtures inteiramente sintéticos.
- Alterações de schema exigem migration e justificativa. Não substituir bancos
  existentes silenciosamente; documentar estratégia de atualização e validação.
- Alterações relevantes de arquitetura devem gerar ADR em docs/adr/.
- Priorizar código simples, explícito, tipado e auditável. Não implementar
  abstrações, comandos ou parsers sem escopo de uso aprovado.
- Não criar integração externa sem solicitação explícita. Não incluir telemetria,
  upload, APIs remotas, cloud storage ou envio automático de evidências.
- Não apresentar o projeto como software pericial certificado.
- Manter dados de caso fora do repositório. .gitignore é defesa complementar,
  não substitui revisão humana e não protege arquivos já rastreados ou forçados.
- Antes de concluir alterações, executar pytest, Ruff e mypy quando disponíveis,
  revisar git diff e git status e registrar limitações sem alegar testes não feitos.
- Não executar commit ou push sem solicitação explícita.

## Escopo atual

Milestone 8A4 concluída: source-media linkage read-only sob ADR 0034: referência aprovada,
exact member path no mesmo container, bytes verificados; sem fuzzy ou inferência
de action semantics. Não resolve message attachments sem referência explícita.
Milestone 8A4.1 concluída sob ADR 0035: report.data_snapshot/1.1.0 e
report.consolidated/1.1.0 integram source_media.provenance_link/1.0.0.
Preservar compatibilidade dos contratos 1.0.0 e ADRs históricos 0031–0034.
Renderer consome somente JSONs de snapshot; não abre CASE_ROOT, DB, originals ou working.
Preservar schema v5; sem novas inferências ou prosa gerada por LLM.
Message attachments permanecem SOURCE_LIMITATION. WhatsApp condicional/não acionado.
Milestone 8B0 concluída sob ADR 0036: Final Legal-Technical Dossier & Export Contract,
somente documentação/arquitetura. Contrato de implementação 8B1.0 concluído sob
ADR 0037 Accepted. Implementação 8B1-A–G concluída e validada sinteticamente em
Docker/Linux Python 3.12.14 e Windows nativo Python 3.12.11. CLI disponível:
`dee dossier assemble --selection ... --output-dir ...`. Pacote directory-v1 com
cinco arquivos gerados determinísticos; paridade byte a byte e publicação real
sem substituição validadas nas duas plataformas. Gates e skips no ADR 0037, seção 20.
8B2.0 e 8B2-A.1.1 concluídas: ADRs 0038/0039 permanecem Accepted. 8B2-A concluída,
com revisão técnica humana aprovada: fundação e adaptador controlado ReportLab 5.0.1
implementados e qualificados somente na superfície privada enumerada no ADR 0039.
Divergência de versão/shape falha fechada; upgrades exigem revisão/requalificação.
Sem monkeypatch, pós-processamento ou modificação do vendor. Toolchain Linux/amd64,
seis fontes DejaVu, ToUnicode/subsets, PDFium para validação visual de desenvolvimento,
materiais de licença e inventário canônico qualificados/preservados tecnicamente.
Gates e hashes: [docs/pdf-toolchain-qualification.md](docs/pdf-toolchain-qualification.md).
8B2-B COMPLETE — HUMAN REVIEW APPROVED, implementada e qualificada sinteticamente:
`render_dossier_pdf(data: bytes) -> bytes` consome somente Markdown fornecido,
preserva as 14 seções e valida texto/layout/TOC/links internos independentemente.
8B2-C COMPLETE — HUMAN REVIEW APPROVED: `render_consolidated_report_pdf(data: bytes) -> bytes`
apresenta os bytes de technical/canonical/consolidated-report.md como
human/consolidated-report.pdf, sem regenerar narrativa. Compartilha layout com B,
preservando seus bytes/pixels; perfil fechado de 20 H2, 20 entradas TOC e 21 destinos/outlines.
8B2-D COMPLETE — HUMAN REVIEW APPROVED: pdf_package captura/verifica directory-v1
read-only, vincula os dois Markdown capturados a PDFs já produzidos e gera bytes
determinísticos de dossier.pdf_export_manifest/1.0.0 e SHA256SUMS. Expectativas
derivadas dos bytes capturados; page_count vem da validação PDF independente,
sem rendering no binding. Recheck de árvore/identidade/tamanho/hash antes/depois;
sem promessa de snapshot atômico. Não reinterpreta snapshots nem decodifica mídia.
8B2-E COMPLETE — HUMAN REVIEW APPROVED: supervisor/worker híbridos, captura D no worker,
protocolo fechado com ACK, 120 s por render/validação e 600 s globais; worker com
RLIMIT_AS de 1 GiB. CLI: `dee dossier pdf --input-package ... --output-dir ...`.
Staging/scratch próprios; quatro arquivos publicados por um renameat2 NOREPLACE,
sem replace/merge/copy fallback ou I/O após publicação confirmada. Serviço não
reentrante no mesmo processo; concorrência CLI usa processos separados.
Qualificação positiva em container Linux/amd64 sobre bind Linux/WSL ext4; host
Windows pode hospedar o container, sem exportação PDF nativa Windows. O bind
Windows 9p/drvfs testado retornou EINVAL e não é alvo qualificado nessa configuração;
não generalizar para todo 9p. Revisões de código, estrutura, qualificação automatizada,
implantação, integridade e visual: PASS. Gates, hashes dos artefatos sintéticos e
inventário em docs/pdf-toolchain-qualification.md.
8B2-F COMPLETE — HUMAN REVIEW APPROVED: qualificação exclusivamente por testes sintéticos
de apresentação extrema, sem mudança de produção. Cobertos limite contratual de
16 colunas/17 RESOURCE_LIMIT, escapes existentes, token ASCII de 1024 caracteres,
paginação no limiar, H3 longo, linha lógica 696 pt válida/708 pt recusada, budgets
N/N-1, determinismo e PDFium de todas as 22 páginas F. Oito colunas permanece
cobertura histórica de C, não teto semântico. 8B2-G NOT STARTED; 8B3 FUTURE.
Sem descoberta de casos ou acesso real.
Arquitetura PDF prevê saída separada pdf-presentation-v1, sem mutar directory-v1.
Render canônico Linux/amd64 fixado, não render nativo multiplataforma.
Probes da fundação e PDFs de dossiê/relatório exclusivamente sintéticos gerados/validados. Sem alegação de
PDF/A, PDF/UA, assinatura ou certificação. 8B3 permanece futura e exclusivamente
responsável pela execução real controlada. Nenhum caso real acessado em 8B2-A/B/C/D/E
ou usado no fechamento 8B1. A montagem consome apenas artefatos aprovados já gerados
e explicitamente selecionados; sem CASE_ROOT, DB, originals/working, parsing, correlação, novos
findings ou rede/cloud/API/LLM. Só CANONICAL_TECHNICAL origina narrativa técnica humana.
Relatório selecionado deve coincidir byte a byte com o modelo/renderer puro dos
snapshots compatíveis selecionados. Completude é interna ao pacote selecionado,
não de todas as janelas possíveis do caso. Sem máximo semântico de janelas;
budgets operacionais falham como RESOURCE_LIMIT. Projeção humana device/network
não usa nem reparte supports.total global. JSON estrito limitado por bytes,
hooks e travessia estrutural; sem autorização de parser JSON próprio/genérico ou
dependência nova pelo ADR 0037.
Originais e legacy excluídos do pacote v1. Visuais são anexos contextuais JPEG/PNG explícitos,
sem criar relações com eventos/findings. WhatsApp fica fora do dataset representado,
salvo futura aquisição/parser/análise separadamente aprovados. PDF pertence à 8B2;
ZIP/archive exige escopo próprio. A fundação 8B2-A segue ADRs 0038/0039;
sua conclusão não autoriza 8B3 ou acesso real.
Dados de caso continuam fora do Git.
Validação real das etapas anteriores autorizada, com snapshots e relatório
exclusivamente fora do Git; essa autorização não inicia a validação real 8B3.
Sem WhatsApp, persistência ou inferência automática de identidade/autoria.
Preservar OBSERVED, DERIVED, REPORTED e HYPOTHESIS e a provenance existente.
Proibir conclusões automáticas de identity, authorship, session, causality
ou questões jurídicas. Dados reais permanecem fora do Git.
Preservar as camadas existentes, inclusive pHash e candidates exatos persistidos.
Compatibilidade Foundation Windows (W1) concluída: identidade e estabilidade por
plataforma conforme ADR 0027; preservar checks path/handle e SHA-256/tamanho.
Schema continua v5, sem migration, runs, views, índices ou cache para queries.
Sem identity, session, score, confidence, authorship, pHash linking,
persistência de overlap ou correlação conclusiva.
Consulte README.md e docs/architecture.md. Escrita em v1/v2/v3/v4 exige migração explícita
para v5; verify/manifest podem inspecionar v2/v3/v4 sem migrar.

Use `uv sync --locked --extra dev --python 3.12` com uv 0.8.22. Não atualize o
lockfile incidentalmente. Hashes catalogados não podem ser substituídos para
acomodar originais alterados. Falhas de ingestão devem preservar a baseline e
registrar a execução com rollback dos novos registros.
