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
8B permanece futura e exige escopo separado; não é autorizada pela integração.
Validação real autorizada, com snapshots e relatório exclusivamente fora do Git.
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
